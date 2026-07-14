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

forward = sys.argv[sys.argv.index('-L') + 1]
port = int(forward.split(':', 3)[1])
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', port))
listener.listen(16)
listener.settimeout(0.5)
running = True

def stop(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
while running:
    try:
        connection, _ = listener.accept()
        connection.close()
    except socket.timeout:
        pass
listener.close()
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

    def test_http_failures_do_not_kill_or_replace_ssh(self) -> None:
        lease = self.client.acquire("cloud", "gateway", 8317)
        try:
            before = self.client.status()
            with mock.patch("cloudx_local.cloud_cli.endpoint_status", return_value=None):
                self.assertIsNone(probe_endpoint(self.config, lease.port, "key"))
            after = self.client.status()
            self.assertEqual(after["sshPid"], before["sshPid"])
            self.assertEqual(after["generation"], before["generation"])
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
        finally:
            lease.release()


if __name__ == "__main__":
    unittest.main()
