from __future__ import annotations

import json
import os
import pathlib
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local.broker import BrokerClient, BrokerServer, request  # noqa: E402
from cloudx_local.cloud_cli import probe_endpoint  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402


FAKE_SSH = """#!/usr/bin/env python3
import signal
import socket
import sys
import threading

forward = sys.argv[sys.argv.index('-L') + 1]
port = int(forward.split(':', 3)[1])
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', port))
listener.listen(16)
listener.settimeout(0.1)
running = True
connections = []

def stop(signum, frame):
    global running
    running = False

def handle(connection):
    connection.settimeout(0.1)
    connections.append(connection)
    try:
        while running:
            try:
                data = connection.recv(65536)
            except socket.timeout:
                continue
            if not data:
                break
            connection.sendall(data)
    except OSError:
        pass
    finally:
        connection.close()

signal.signal(signal.SIGTERM, stop)
while running:
    try:
        connection, _ = listener.accept()
        threading.Thread(target=handle, args=(connection,), daemon=True).start()
    except socket.timeout:
        pass
listener.close()
for connection in connections:
    try:
        connection.close()
    except OSError:
        pass
"""


class BrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        home = pathlib.Path(self.temp.name)
        fake_ssh = home / "fake-ssh"
        fake_ssh.write_text(FAKE_SSH, encoding="utf-8")
        fake_ssh.chmod(0o755)
        self.config = LocalConfig(
            home=home,
            config_path=home / "config.json",
            state_dir=home / "state",
            data_dir=home / "data",
            cache_dir=home / "cache",
            accounts_dir=home / "accounts",
            codex_binary="codex",
            ssh_binary=str(fake_ssh),
            ssh_host="cloud",
            remote_helper="cloudx-remote",
            legacy_forward_host="gateway",
            legacy_forward_port=8317,
            legacy_api_key_command="legacy-key",
            broker_idle_seconds=3600,
            endpoint_timeout_seconds=2.0,
            endpoint_attempts=1,
            release_repository="repo",
        )
        self.server = BrokerServer(self.config)
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not (self.config.broker_dir / "control.sock").exists():
            time.sleep(0.05)
        self.client = BrokerClient(self.config)

    def tearDown(self) -> None:
        try:
            status = self.client.status()
            if status.get("leases") == 0 and status.get("running"):
                request(self.config.broker_dir / "control.sock", {"command": "shutdown"})
        except Exception:
            pass
        self.thread.join(timeout=5.0)
        self.temp.cleanup()

    def test_shared_leases_have_one_owner_and_stable_port(self) -> None:
        first = self.client.acquire("cloud", "gateway", 8317)
        second = self.client.acquire("cloud", "gateway", 8317)
        try:
            status = self.client.status()
            self.assertEqual(status["leases"], 2)
            self.assertEqual(first.port, second.port)
            self.assertIsNotNone(status["sshPid"])
        finally:
            first.release()
            second.release()

    def test_shell_owned_lease_survives_client_return_until_explicit_release(self) -> None:
        response = self.client.acquire_for_owner("cloud", "gateway", 8317, os.getpid())
        lease_id = str(response["leaseId"])
        self.assertEqual(self.client.status()["leases"], 1)
        self.client.release(lease_id)
        self.assertEqual(self.client.status()["leases"], 0)

    def test_http_failures_do_not_kill_or_replace_ssh(self) -> None:
        lease = self.client.acquire("cloud", "gateway", 8317)
        try:
            before = self.client.status()
            with mock.patch("cloudx_local.cloud_cli.endpoint_status", return_value=None):
                self.assertIsNone(probe_endpoint(self.config, lease.port, "key"))
            after = self.client.status()
            self.assertEqual(after["sshPid"], before["sshPid"])
            self.assertEqual(after["generation"], before["generation"])
            self.assertEqual(after["publicPort"], before["publicPort"])
            self.assertEqual(after["lastReconnectMilliseconds"], before["lastReconnectMilliseconds"])
        finally:
            lease.release()

    def test_real_ssh_exit_restarts_backend_without_changing_public_port(self) -> None:
        lease = self.client.acquire("cloud", "gateway", 8317)
        try:
            before = self.client.status()
            os.kill(int(before["sshPid"]), signal.SIGTERM)
            down_deadline = time.monotonic() + 3.0
            while time.monotonic() < down_deadline:
                if self.client.status().get("sshPid") is None:
                    break
                time.sleep(0.05)
            with socket.create_connection(("127.0.0.1", lease.port), timeout=1.0):
                pass
            deadline = time.monotonic() + 8.0
            after = before
            while time.monotonic() < deadline:
                after = self.client.status()
                if after.get("generation", 0) > before["generation"] and after.get("sshPid"):
                    break
                time.sleep(0.2)
            self.assertGreater(after["generation"], before["generation"])
            self.assertNotEqual(after["sshPid"], before["sshPid"])
            self.assertEqual(lease.port, after["publicPort"])
            self.assertIsInstance(after["lastReconnectMilliseconds"], int)
        finally:
            lease.release()

    def test_child_exit_with_concurrent_streams_records_reconnect_timing(self) -> None:
        lease = self.client.acquire("cloud", "gateway", 8317)
        active = []
        try:
            before = self.client.status()
            self.assertNotEqual(lease.port, 18317)
            for index in range(4):
                stream = socket.create_connection(("127.0.0.1", lease.port), timeout=2.0)
                stream.settimeout(3.0)
                payload = ("active-%d" % index).encode("ascii")
                stream.sendall(payload)
                self.assertEqual(stream.recv(len(payload)), payload)
                active.append(stream)

            os.kill(int(before["sshPid"]), signal.SIGTERM)
            down_deadline = time.monotonic() + 3.0
            down_observed = False
            while time.monotonic() < down_deadline:
                if self.client.status().get("sshPid") is None:
                    down_observed = True
                    break
                time.sleep(0.05)
            self.assertTrue(down_observed)

            results = {}
            durations = {}

            def exchange(index: int) -> None:
                payload = ("waiting-%d" % index).encode("ascii")
                started = time.monotonic()
                try:
                    with socket.create_connection(("127.0.0.1", lease.port), timeout=2.0) as stream:
                        stream.settimeout(10.0)
                        stream.sendall(payload)
                        results[index] = stream.recv(len(payload))
                finally:
                    durations[index] = time.monotonic() - started

            waiting = [threading.Thread(target=exchange, args=(index,)) for index in range(4)]
            for thread in waiting:
                thread.start()
            for thread in waiting:
                thread.join(timeout=12.0)
                self.assertFalse(thread.is_alive())

            after = self.client.status()
            self.assertEqual(results, {index: ("waiting-%d" % index).encode("ascii") for index in range(4)})
            self.assertEqual(len(durations), 4)
            self.assertLess(max(durations.values()), 8.0)
            self.assertGreater(after["generation"], before["generation"])
            self.assertNotEqual(after["sshPid"], before["sshPid"])
            self.assertEqual(after["publicPort"], lease.port)
            self.assertGreater(after["lastReconnectMilliseconds"], 0)
            self.assertLess(after["lastReconnectMilliseconds"], 8000)
        finally:
            for stream in active:
                stream.close()
            lease.release()


if __name__ == "__main__":
    unittest.main()
