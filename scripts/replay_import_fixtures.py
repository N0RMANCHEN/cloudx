#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

from cloudx_cloud.importer import import_records  # noqa: E402


def _record(suffix: str) -> Dict[str, Any]:
    return {
        "type": "codex",
        "email": "%s@fixture.invalid" % suffix,
        "access_token": "fixture.access.%s" % suffix,
        "refresh_token": "fixture.refresh.%s" % suffix,
        "id_token": "fixture.id.%s" % suffix,
        "account_id": "fixture-account-%s" % suffix,
    }


def _normalized(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "codex",
        "disabled": False,
        "websockets": False,
        "access_token": record["access_token"],
        "refresh_token": record["refresh_token"],
        "id_token": record["id_token"],
        "account_id": record["account_id"],
        "email": record["email"],
    }


def _source(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")


def fixture_matrix() -> Sequence[Tuple[str, bytes, Sequence[Dict[str, Any]]]]:
    one = _record("one")
    two = _record("two")
    flat = _source(one)
    return (
        ("flat", flat, (one,)),
        ("accounts", _source({"accounts": [one, two]}), (one, two)),
        ("payload-accounts", _source({"payload": {"accounts": [one]}}), (one,)),
        ("result-accounts", _source({"result": {"accounts": [two]}}), (two,)),
        ("sub2api", _source({"name": one["email"], "credentials": one}), (one,)),
        (
            "bundle",
            _source({"type": "codexx-cliproxy-auth-bundle", "files": [{"data": one}, {"data": two}]}),
            (one, two),
        ),
        ("concatenated-json", flat + _source(two), (one, two)),
        (
            "directory-envelope",
            _source({
                "schema": "cloudx.import-source.v1",
                "files": [
                    {"name": "one.json", "content": flat.decode("utf-8")},
                    {"name": "two.json", "content": _source(two).decode("utf-8")},
                ],
            }),
            (one, two),
        ),
    )


def _filename(record: Dict[str, Any]) -> str:
    tokens = (record["access_token"], record["refresh_token"], record["id_token"])
    digest = hashlib.sha256("\0".join(tokens).encode("utf-8")).hexdigest()[:24]
    return "codex-%s.json" % digest


def _expected(records: Iterable[Dict[str, Any]]) -> Dict[str, bytes]:
    expected: Dict[str, bytes] = {}
    for record in records:
        normalized = _normalized(record)
        expected[_filename(normalized)] = (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return expected


def _existing_files(path: pathlib.Path) -> Dict[str, bytes]:
    return {
        candidate.name: candidate.read_bytes()
        for candidate in sorted(path.glob("*.json"))
        if candidate.is_file() and not candidate.is_symlink()
    }


def replay(shadow_root: pathlib.Path, retain: bool = False) -> Dict[str, Any]:
    expanded = shadow_root.expanduser()
    if expanded.is_symlink():
        raise RuntimeError("shadow fixture root must not be a symlink")
    resolved = expanded.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise RuntimeError("shadow fixture root must be a directory")
    work = pathlib.Path(tempfile.mkdtemp(prefix=".cloudx-import-fixtures-", dir=str(resolved)))
    fixtures = fixture_matrix()
    try:
        for name, raw, records in fixtures:
            auth_dir = work / name / "auth"
            lock_path = work / name / "run/import.lock"
            first = import_records(raw, auth_dir, lock_path, dry_run=False, force=False)
            expected = _expected(records)
            if first.status != "accepted" or first.written != len(expected) or first.skipped != 0:
                raise RuntimeError("fixture %s did not write the expected record count" % name)
            if _existing_files(auth_dir) != expected:
                raise RuntimeError("fixture %s normalized output does not match" % name)
            second = import_records(raw, auth_dir, lock_path, dry_run=False, force=False)
            if second.status != "accepted" or second.written != 0 or second.skipped != len(expected):
                raise RuntimeError("fixture %s is not idempotent" % name)
            if any(candidate.is_file() and raw in candidate.read_bytes() for candidate in work.rglob("*")):
                raise RuntimeError("fixture %s raw source was retained" % name)
        result = {
            "schema": "cloudx.import-fixture-check.v1",
            "status": "ok",
            "fixtures": len(fixtures),
            "normalizedTransactions": len(fixtures),
            "idempotentReplays": len(fixtures),
            "rawSourcesRetained": False,
            "retained": retain,
        }
        if retain:
            result["evidencePath"] = str(work)
        return result
    finally:
        if not retain:
            shutil.rmtree(work, ignore_errors=True)


def _confirmed_root(path: pathlib.Path, confirmation: str) -> pathlib.Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise RuntimeError("shadow fixture root must not be a symlink")
    resolved = expanded.resolve()
    if confirmation != str(resolved):
        raise RuntimeError("shadow fixture root confirmation does not match the resolved path")
    if resolved == pathlib.Path("/"):
        raise RuntimeError("refusing to use a production or system directory for fixture replay")
    forbidden_roots = (
        pathlib.Path("/etc"),
        pathlib.Path("/opt"),
        pathlib.Path("/var/lib/codex-gateway/cliproxy-auth"),
        pathlib.Path("/var/lib/codex-gateway/cliproxy-auth-archive"),
    )
    if any(resolved == root or root in resolved.parents for root in forbidden_roots):
        raise RuntimeError("refusing to use a production or system directory for fixture replay")
    return resolved


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Replay fake import fixtures through the canonical Cloudx importer")
    root.add_argument("--shadow-root", type=pathlib.Path)
    root.add_argument("--confirm-shadow-root", default="")
    root.add_argument("--retain", action="store_true")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.shadow_root is None:
            if args.retain:
                raise RuntimeError("--retain requires an explicitly confirmed shadow root")
            with tempfile.TemporaryDirectory(prefix="cloudx-import-fixture-root-") as value:
                result = replay(pathlib.Path(value), retain=False)
        else:
            result = replay(_confirmed_root(args.shadow_root, args.confirm_shadow_root), retain=args.retain)
    except (OSError, RuntimeError, ValueError) as exc:
        print("replay_import_fixtures.py: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
