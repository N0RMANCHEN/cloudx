from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Sequence, Tuple

from .broker import BrokerClient
from .config import LocalConfig
from .profile import cloud_codex_environment
from .remote import RemoteClient


MAX_IMPORT_BYTES = 16 * 1024 * 1024
IMPORT_SUFFIXES = {"", ".json", ".jsonl", ".ndjson", ".txt", ".md", ".log", ".data"}
IGNORED_DIRECTORIES = {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__"}


def endpoint_status(port: int, api_key: str, timeout: float) -> Optional[int]:
    request = urllib.request.Request(
        "http://127.0.0.1:%d/v1/models" % port,
        headers={"Authorization": "Bearer %s" % api_key, "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (OSError, urllib.error.URLError, TimeoutError):
        return None


def probe_endpoint(config: LocalConfig, port: int, api_key: str) -> Optional[int]:
    status: Optional[int] = None
    for attempt in range(config.endpoint_attempts):
        status = endpoint_status(port, api_key, config.endpoint_timeout_seconds)
        if status is not None:
            return status
        if attempt + 1 < config.endpoint_attempts:
            time.sleep(1.0)
    return status


def check_connection(config: LocalConfig) -> int:
    remote = RemoteClient(config)
    endpoint = remote.resolve_endpoint()
    broker = BrokerClient(config)
    with broker.acquire(config.ssh_host, endpoint.forward_host, endpoint.forward_port) as lease:
        status = probe_endpoint(config, lease.port, endpoint.api_key)
        broker_status = broker.status()
        print("cloud remote: %s" % endpoint.mode)
        print(
            "tunnel broker: ok (pid=%s, ssh=%s, leases=%s, generation=%s)"
            % (
                broker_status.get("pid", "-"),
                broker_status.get("sshPid", "-"),
                broker_status.get("leases", "-"),
                broker_status.get("generation", "-"),
            )
        )
        if status is None:
            print("cloud gateway: no HTTP response; broker kept the SSH tunnel unchanged", file=sys.stderr)
            return 1
        print("cloud gateway: HTTP %d" % status)
        if 200 <= status < 300:
            return 0
        if status >= 500:
            print("cloud gateway returned a server response; this is not a tunnel disconnect", file=sys.stderr)
        return 1


def run_codex(config: LocalConfig, codex_args: Sequence[str]) -> int:
    endpoint = RemoteClient(config).resolve_endpoint()
    broker = BrokerClient(config)
    with broker.acquire(config.ssh_host, endpoint.forward_host, endpoint.forward_port) as lease:
        environment = cloud_codex_environment(config, endpoint.api_key, lease.port)
        base_url = "http://127.0.0.1:%d/v1" % lease.port
        command = [config.codex_binary, "-c", 'openai_base_url="%s"' % base_url, *codex_args]
        try:
            return int(subprocess.run(command, env=environment, check=False).returncode)
        except FileNotFoundError as exc:
            raise RuntimeError("official Codex executable was not found: %s" % config.codex_binary) from exc


def _read_file(path: pathlib.Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("import source must be a regular file")
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise RuntimeError("import source exceeds 16 MiB")
    raw = path.read_bytes()
    if len(raw) > MAX_IMPORT_BYTES:
        raise RuntimeError("import source exceeds 16 MiB")
    return raw


def _decode_import_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("directory import files must be UTF-8 or UTF-16 text")


def import_source(source: str) -> bytes:
    if source == "-":
        raw = sys.stdin.buffer.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            raise RuntimeError("import source exceeds 16 MiB")
        if not raw:
            raise RuntimeError("import source is empty")
        return raw
    path = pathlib.Path(source).expanduser()
    if path.is_file() and not path.is_symlink():
        return _read_file(path)
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError("import source does not exist or is not a regular path")
    files = []
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        relative = candidate.relative_to(path)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if candidate.suffix.casefold() not in IMPORT_SUFFIXES:
            continue
        content = _decode_import_text(_read_file(candidate))
        files.append({"name": relative.as_posix(), "content": content})
    if not files:
        raise RuntimeError("directory contains no supported import files")
    raw = json.dumps({"schema": "cloudx.import-source.v1", "files": files}, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_IMPORT_BYTES:
        raise RuntimeError("directory import envelope exceeds 16 MiB")
    return raw


def run_import(config: LocalConfig, source: str, dry_run: bool, force: bool) -> int:
    raw = import_source(source)
    document = RemoteClient(config).import_payload(raw, dry_run=dry_run, force=force)
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0 if document.get("status") == "accepted" else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cloud")
    sub = root.add_subparsers(dest="command", required=True)
    codex = sub.add_parser("codex")
    codex.add_argument("--check", action="store_true")
    codex.add_argument("codex_args", nargs=argparse.REMAINDER)
    import_parser = sub.add_parser("import")
    import_parser.add_argument("source")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--force", action="store_true")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    config = LocalConfig.load()
    if args.command == "codex":
        codex_args = list(args.codex_args)
        if codex_args[:1] == ["--"]:
            codex_args = codex_args[1:]
        if args.check:
            if codex_args:
                raise RuntimeError("cloud codex --check does not accept Codex arguments")
            return check_connection(config)
        return run_codex(config, codex_args)
    if args.command == "import":
        return run_import(config, args.source, args.dry_run, args.force)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("cloud: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
