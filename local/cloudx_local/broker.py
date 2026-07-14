from __future__ import annotations

import fcntl
import json
import os
import pathlib
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from .config import LocalConfig
from .files import atomic_json, ensure_private_directory


MAX_CONTROL_BYTES = 64 * 1024
START_TIMEOUT_SECONDS = 20.0
BACKEND_WAIT_SECONDS = 20.0


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def choose_public_listener() -> socket.socket:
    for _ in range(200):
        port = 20000 + secrets.randbelow(10000)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
            listener.settimeout(1.0)
            return listener
        except OSError:
            listener.close()
    raise RuntimeError("could not allocate a Cloudx tunnel broker port")


def choose_backend_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


class TcpRelay:
    """Keep a stable local listener while the SSH backend may restart."""

    def __init__(self) -> None:
        self.listener = choose_public_listener()
        self.public_port = int(self.listener.getsockname()[1])
        self.backend_port: Optional[int] = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._accept_loop, name="cloudx-tunnel-relay", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def set_backend(self, port: Optional[int]) -> None:
        with self.lock:
            self.backend_port = port

    def current_backend(self) -> Optional[int]:
        with self.lock:
            return self.backend_port

    def _accept_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _connect_backend(self) -> Optional[socket.socket]:
        deadline = time.monotonic() + BACKEND_WAIT_SECONDS
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            port = self.current_backend()
            if port:
                try:
                    return socket.create_connection(("127.0.0.1", port), timeout=1.0)
                except OSError:
                    pass
            self.stop_event.wait(0.2)
        return None

    @staticmethod
    def _pump(source: socket.socket, target: socket.socket) -> None:
        try:
            while True:
                data = source.recv(64 * 1024)
                if not data:
                    break
                target.sendall(data)
        except OSError:
            pass
        finally:
            try:
                target.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def _handle(self, client: socket.socket) -> None:
        backend = self._connect_backend()
        if backend is None:
            client.close()
            return
        client.settimeout(None)
        backend.settimeout(None)
        outward = threading.Thread(target=self._pump, args=(client, backend), daemon=True)
        outward.start()
        self._pump(backend, client)
        outward.join(timeout=1.0)
        client.close()
        backend.close()

    def close(self) -> None:
        self.stop_event.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self.thread.join(timeout=3.0)


@dataclass(frozen=True)
class TunnelSpec:
    ssh_host: str
    forward_host: str
    forward_port: int


class BrokerServer:
    def __init__(self, config: LocalConfig) -> None:
        self.config = config
        self.directory = config.broker_dir
        self.socket_path = self.directory / "control.sock"
        self.lock_path = self.directory / "broker.lock"
        self.state_path = self.directory / "broker.json"
        self.lock_handle: Optional[Any] = None
        self.control: Optional[socket.socket] = None
        self.relay: Optional[TcpRelay] = None
        self.ssh_process: Optional[subprocess.Popen] = None
        self.spec: Optional[TunnelSpec] = None
        self.leases: Dict[str, Dict[str, Any]] = {}
        self.last_release = time.monotonic()
        self.generation = 0
        self.stop_requested = False
        self.next_restart_at = 0.0
        self.restart_delay = 1.0

    def _acquire_singleton(self) -> None:
        ensure_private_directory(self.directory)
        self.lock_handle = self.lock_path.open("a+")
        os.chmod(self.lock_path, 0o600)
        try:
            fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Cloudx tunnel broker is already running") from exc

    def _open_control(self) -> None:
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        control.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        control.listen(16)
        control.settimeout(1.0)
        self.control = control

    def _ssh_argv(self, spec: TunnelSpec, backend_port: int) -> Sequence[str]:
        forward = "127.0.0.1:%d:%s:%d" % (backend_port, spec.forward_host, spec.forward_port)
        return [
            self.config.ssh_binary,
            "-N",
            "-L",
            forward,
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "TCPKeepAlive=yes",
            "-o",
            "ControlMaster=no",
            spec.ssh_host,
        ]

    def _start_ssh(self) -> None:
        if self.spec is None:
            raise RuntimeError("tunnel specification is missing")
        if self.relay is None:
            self.relay = TcpRelay()
            self.relay.start()
        backend_port = choose_backend_port()
        self.relay.set_backend(None)
        try:
            process = subprocess.Popen(
                self._ssh_argv(self.spec, backend_port),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=None,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("ssh executable was not found: %s" % self.config.ssh_binary) from exc
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("SSH tunnel exited during startup with code %d" % process.returncode)
            try:
                with socket.create_connection(("127.0.0.1", backend_port), timeout=0.25):
                    self.ssh_process = process
                    self.relay.set_backend(backend_port)
                    self.generation += 1
                    self.restart_delay = 1.0
                    self.next_restart_at = 0.0
                    self._write_state()
                    return
            except OSError:
                time.sleep(0.1)
        process.terminate()
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError("SSH tunnel did not become ready within 20 seconds")

    def _stop_ssh(self) -> None:
        process = self.ssh_process
        self.ssh_process = None
        if self.relay is not None:
            self.relay.set_backend(None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)

    def _ensure_ssh(self) -> None:
        if self.ssh_process is not None and self.ssh_process.poll() is None:
            return
        self.ssh_process = None
        if self.relay is not None:
            self.relay.set_backend(None)
        self._start_ssh()

    def _write_state(self) -> None:
        atomic_json(
            self.state_path,
            {
                "schema": "cloudx.tunnel-broker.v1",
                "pid": os.getpid(),
                "publicPort": self.relay.public_port if self.relay else None,
                "sshPid": self.ssh_process.pid if self.ssh_process and self.ssh_process.poll() is None else None,
                "generation": self.generation,
                "leases": len(self.leases),
                "sshHost": self.spec.ssh_host if self.spec else None,
                "forwardHost": self.spec.forward_host if self.spec else None,
                "forwardPort": self.spec.forward_port if self.spec else None,
            },
        )

    def _reap_leases(self) -> None:
        stale = [lease_id for lease_id, lease in self.leases.items() if not pid_alive(int(lease.get("ownerPid", 0)))]
        for lease_id in stale:
            self.leases.pop(lease_id, None)
        if stale and not self.leases:
            self.last_release = time.monotonic()
        if stale:
            self._write_state()

    def _maintain_tunnel(self) -> None:
        if self.ssh_process is not None and self.ssh_process.poll() is not None:
            self.ssh_process = None
            if self.relay is not None:
                self.relay.set_backend(None)
            self.next_restart_at = time.monotonic() + self.restart_delay
            self.restart_delay = min(20.0, self.restart_delay * 2.0)
            self._write_state()
        if self.leases and self.ssh_process is None and time.monotonic() >= self.next_restart_at:
            try:
                self._start_ssh()
            except RuntimeError:
                self.next_restart_at = time.monotonic() + self.restart_delay
                self.restart_delay = min(20.0, self.restart_delay * 2.0)

    def _response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        command = request.get("command")
        if command == "ping":
            return {"ok": True, "pid": os.getpid()}
        if command == "status":
            return {
                "ok": True,
                "running": True,
                "pid": os.getpid(),
                "publicPort": self.relay.public_port if self.relay else None,
                "sshPid": self.ssh_process.pid if self.ssh_process and self.ssh_process.poll() is None else None,
                "generation": self.generation,
                "leases": len(self.leases),
            }
        if command == "acquire":
            lease_id = str(request.get("leaseId") or "")
            owner_pid = int(request.get("ownerPid") or 0)
            ssh_host = str(request.get("sshHost") or "").strip()
            forward_host = str(request.get("forwardHost") or "").strip()
            forward_port = int(request.get("forwardPort") or 0)
            try:
                uuid.UUID(lease_id)
            except (ValueError, AttributeError):
                raise RuntimeError("invalid tunnel lease identifier")
            if not pid_alive(owner_pid):
                raise RuntimeError("tunnel lease owner is not running")
            if not ssh_host or not forward_host or not 1 <= forward_port <= 65535:
                raise RuntimeError("invalid tunnel specification")
            requested = TunnelSpec(ssh_host, forward_host, forward_port)
            if self.spec is not None and requested != self.spec and self.leases:
                raise RuntimeError("active tunnel leases use a different remote endpoint")
            if requested != self.spec:
                self._stop_ssh()
                self.spec = requested
            self._ensure_ssh()
            self.leases[lease_id] = {"ownerPid": owner_pid, "acquiredAt": time.time()}
            self._write_state()
            return {
                "ok": True,
                "leaseId": lease_id,
                "publicPort": self.relay.public_port if self.relay else None,
                "generation": self.generation,
            }
        if command == "release":
            lease_id = str(request.get("leaseId") or "")
            self.leases.pop(lease_id, None)
            if not self.leases:
                self.last_release = time.monotonic()
            self._write_state()
            return {"ok": True, "leases": len(self.leases)}
        if command == "shutdown":
            if self.leases:
                raise RuntimeError("cannot stop the tunnel broker while leases are active")
            self.stop_requested = True
            return {"ok": True}
        raise RuntimeError("unsupported tunnel broker command")

    def _serve_connection(self, connection: socket.socket) -> None:
        raw = bytearray()
        connection.settimeout(5.0)
        try:
            while len(raw) <= MAX_CONTROL_BYTES:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                raw.extend(chunk)
                if b"\n" in chunk:
                    break
            if len(raw) > MAX_CONTROL_BYTES:
                raise RuntimeError("tunnel broker request is too large")
            request = json.loads(bytes(raw).decode("utf-8"))
            if not isinstance(request, dict):
                raise RuntimeError("tunnel broker request must be an object")
            response = self._response(request)
        except (ValueError, OSError, RuntimeError) as exc:
            response = {"ok": False, "error": str(exc)}
        try:
            connection.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
        except OSError:
            pass
        finally:
            connection.close()

    def serve(self) -> int:
        self._acquire_singleton()
        self._open_control()
        self._write_state()
        try:
            while not self.stop_requested:
                self._reap_leases()
                self._maintain_tunnel()
                if not self.leases and time.monotonic() - self.last_release >= self.config.broker_idle_seconds:
                    break
                try:
                    assert self.control is not None
                    connection, _ = self.control.accept()
                except socket.timeout:
                    continue
                self._serve_connection(connection)
        finally:
            self._stop_ssh()
            if self.relay is not None:
                self.relay.close()
            if self.control is not None:
                self.control.close()
            try:
                self.socket_path.unlink()
            except FileNotFoundError:
                pass
            try:
                self.state_path.unlink()
            except FileNotFoundError:
                pass
            if self.lock_handle is not None:
                fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_UN)
                self.lock_handle.close()
        return 0


def request(socket_path: pathlib.Path, document: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        client.sendall((json.dumps(document, separators=(",", ":")) + "\n").encode("utf-8"))
        raw = bytearray()
        while len(raw) <= MAX_CONTROL_BYTES:
            chunk = client.recv(4096)
            if not chunk:
                break
            raw.extend(chunk)
            if b"\n" in chunk:
                break
    finally:
        client.close()
    value = json.loads(bytes(raw).decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("tunnel broker returned a non-object response")
    if not value.get("ok"):
        raise RuntimeError(str(value.get("error") or "tunnel broker request failed"))
    return value


def launcher_command() -> Sequence[str]:
    configured = os.environ.get("CLOUDX_LOCAL_ARTIFACT")
    target = pathlib.Path(configured or os.path.realpath(sys.argv[0]))
    return [sys.executable, str(target), "_broker", "serve"]


class BrokerClient:
    def __init__(self, config: LocalConfig) -> None:
        self.config = config
        self.socket_path = config.broker_dir / "control.sock"
        self.start_lock_path = config.broker_dir / "start.lock"

    def _ping(self) -> bool:
        try:
            request(self.socket_path, {"command": "ping"}, timeout=0.5)
            return True
        except (OSError, ValueError, RuntimeError):
            return False

    def ensure_started(self) -> None:
        if self._ping():
            return
        ensure_private_directory(self.config.broker_dir)
        with self.start_lock_path.open("a+") as lock:
            os.chmod(self.start_lock_path, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if self._ping():
                return
            log_path = self.config.broker_dir / "broker.log"
            with log_path.open("ab", buffering=0) as log:
                os.chmod(log_path, 0o600)
                environment = dict(os.environ)
                for name in (
                    "OPENAI_API_KEY",
                    "OPENAI_BASE_URL",
                    "OPENAI_API_BASE",
                    "CODEX_HOME",
                    "CODEXX_ACTIVE_ACCOUNT",
                    "CODEXX_ACTIVE_HOME",
                    "CODEXX_ACTIVE_PINNED",
                ):
                    environment.pop(name, None)
                environment["CLOUDX_USER_HOME"] = str(self.config.home)
                process = subprocess.Popen(
                    launcher_command(),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                    env=environment,
                )
            deadline = time.monotonic() + START_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if self._ping():
                    return
                if process.poll() is not None:
                    raise RuntimeError("Cloudx tunnel broker exited during startup")
                time.sleep(0.1)
            raise RuntimeError("Cloudx tunnel broker did not start within 20 seconds")

    def acquire(self, ssh_host: str, forward_host: str, forward_port: int) -> "TunnelLease":
        self.ensure_started()
        lease_id = str(uuid.uuid4())
        response = request(
            self.socket_path,
            {
                "command": "acquire",
                "leaseId": lease_id,
                "ownerPid": os.getpid(),
                "sshHost": ssh_host,
                "forwardHost": forward_host,
                "forwardPort": forward_port,
            },
            timeout=START_TIMEOUT_SECONDS + 5.0,
        )
        port = int(response.get("publicPort") or 0)
        if not 1 <= port <= 65535:
            raise RuntimeError("tunnel broker returned an invalid local port")
        return TunnelLease(self, lease_id, port, int(response.get("generation") or 0))

    def status(self) -> Dict[str, Any]:
        if not self._ping():
            return {"ok": True, "running": False, "leases": 0}
        return request(self.socket_path, {"command": "status"})


class TunnelLease:
    def __init__(self, client: BrokerClient, lease_id: str, port: int, generation: int) -> None:
        self.client = client
        self.lease_id = lease_id
        self.port = port
        self.generation = generation
        self.released = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        try:
            request(self.client.socket_path, {"command": "release", "leaseId": self.lease_id})
        except (OSError, ValueError, RuntimeError):
            pass

    def __enter__(self) -> "TunnelLease":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments != ["serve"]:
        raise RuntimeError("unsupported tunnel broker invocation")
    return BrokerServer(LocalConfig.load()).serve()


def control_main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments not in (["status"], ["shutdown"]):
        raise RuntimeError("unsupported tunnel broker control invocation")
    client = BrokerClient(LocalConfig.load())
    if arguments == ["status"]:
        print(json.dumps(client.status(), sort_keys=True))
        return 0
    if not client._ping():
        return 0
    print(json.dumps(request(client.socket_path, {"command": "shutdown"}), sort_keys=True))
    return 0
