#!/usr/bin/env python3
"""Synchronize the GitHub release workflow key and prove it with a non-publishing canary."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import pwd
import re
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Set


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_release_trust_recovery as trust  # noqa: E402


PLAN_SCHEMA = "cloudx.release-workflow-key-plan.v1"
RESULT_SCHEMA = "cloudx.release-workflow-key.v1"
EXPECTED_REPOSITORY = "N0RMANCHEN/cloudx"
BRANCH = "main"
WORKFLOW = "release.yml"
ENVIRONMENT = "release"
SECRET_NAME = "CLOUDX_RELEASE_SIGNING_KEY"
MAX_KEY_BYTES = 32 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
RUN_DISCOVERY_SECONDS = 60.0
RUN_COMPLETION_SECONDS = 900.0
POLL_SECONDS = 5.0
DEFAULT_LOCK = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/cloudx-release/workflow-key.lock"
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class WorkflowKeyRejected(RuntimeError):
    pass


def confirmation(version: str) -> str:
    return "SYNCHRONIZE CLOUDX RELEASE WORKFLOW KEY %s" % version


def _version(root: pathlib.Path) -> str:
    try:
        value = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise WorkflowKeyRejected("repository VERSION is unavailable") from exc
    if not VERSION_RE.fullmatch(value):
        raise WorkflowKeyRejected("repository VERSION is invalid")
    return value


def _run(
    command: Sequence[str],
    *,
    cwd: pathlib.Path = ROOT,
    input_bytes: Optional[bytes] = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowKeyRejected("required release workflow command is unavailable") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise WorkflowKeyRejected("release workflow command output exceeded the limit")
    return completed


def _require_success(completed: subprocess.CompletedProcess[bytes], label: str) -> bytes:
    if completed.returncode != 0:
        raise WorkflowKeyRejected("%s failed" % label)
    return completed.stdout


@contextmanager
def _transaction_lock() -> Iterator[None]:
    directory = DEFAULT_LOCK.parent
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = directory.lstat()
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowKeyRejected("release workflow key state directory is unsafe")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise WorkflowKeyRejected("release workflow key state directory must be owner mode 0700")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(DEFAULT_LOCK, flags, 0o600)
    except OSError as exc:
        raise WorkflowKeyRejected("release workflow key lock is unavailable") from exc
    try:
        lock_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(lock_metadata.st_mode) or lock_metadata.st_uid != os.geteuid():
            raise WorkflowKeyRejected("release workflow key lock ownership is invalid")
        if stat.S_IMODE(lock_metadata.st_mode) != 0o600:
            raise WorkflowKeyRejected("release workflow key lock must be owner mode 0600")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _git_clean(root: pathlib.Path) -> None:
    completed = _run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
    )
    if completed.returncode != 0:
        raise WorkflowKeyRejected("repository Git status is unavailable")
    if completed.stdout.strip():
        raise WorkflowKeyRejected("repository must be clean before workflow-key synchronization")


def _head_commit(root: pathlib.Path) -> str:
    raw = _require_success(_run(["git", "rev-parse", "HEAD"], cwd=root), "HEAD lookup")
    value = raw.decode("ascii", errors="replace").strip()
    if not COMMIT_RE.fullmatch(value):
        raise WorkflowKeyRejected("repository HEAD is invalid")
    return value


def _origin_repository(root: pathlib.Path) -> str:
    raw = _require_success(
        _run(["git", "remote", "get-url", "origin"], cwd=root),
        "origin lookup",
    ).decode("utf-8", errors="replace").strip()
    patterns = (
        r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
    )
    repository = None
    for pattern in patterns:
        matched = re.fullmatch(pattern, raw)
        if matched:
            repository = matched.group(1)
            break
    if repository != EXPECTED_REPOSITORY:
        raise WorkflowKeyRejected("origin does not identify the approved Cloudx repository")
    return repository


def _remote_head(root: pathlib.Path) -> str:
    raw = _require_success(
        _run(["git", "ls-remote", "origin", "refs/heads/%s" % BRANCH], cwd=root),
        "remote main lookup",
    ).decode("ascii", errors="replace").strip()
    fields = raw.split()
    if len(fields) != 2 or fields[1] != "refs/heads/%s" % BRANCH or not COMMIT_RE.fullmatch(fields[0]):
        raise WorkflowKeyRejected("remote main is unavailable")
    return fields[0]


def _safe_key_bytes(path: pathlib.Path, root: pathlib.Path) -> bytes:
    if not path.is_absolute():
        raise WorkflowKeyRejected("private key path must be absolute")
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise WorkflowKeyRejected("private key path must remain outside the repository")
    try:
        parent_metadata = path.parent.lstat()
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowKeyRejected("release workflow private key is unavailable") from exc
    if path.parent.is_symlink() or not stat.S_ISDIR(parent_metadata.st_mode):
        raise WorkflowKeyRejected("release workflow private key directory is unsafe")
    if parent_metadata.st_uid != os.geteuid() or stat.S_IMODE(parent_metadata.st_mode) != 0o700:
        raise WorkflowKeyRejected("release workflow private key directory must be owner mode 0700")
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise WorkflowKeyRejected("release workflow private key must be a regular non-symlink file")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise WorkflowKeyRejected("release workflow private key must be owner mode 0600")
    if metadata.st_size <= 0 or metadata.st_size > MAX_KEY_BYTES:
        raise WorkflowKeyRejected("release workflow private key size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise WorkflowKeyRejected("release workflow private key is unsafe") from exc
    try:
        opened = os.fstat(descriptor)
        if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
            raise WorkflowKeyRejected("release workflow private key changed during validation")
        chunks = []
        remaining = MAX_KEY_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_KEY_BYTES:
        raise WorkflowKeyRejected("release workflow private key size is invalid")
    return raw


def _key_fingerprint(path: pathlib.Path, root: pathlib.Path) -> str:
    derived = _require_success(
        _run(["ssh-keygen", "-y", "-f", str(path)], cwd=root),
        "private-key public derivation",
    ).decode("ascii", errors="replace").split()
    if len(derived) < 2 or derived[0] != "ssh-ed25519":
        raise WorkflowKeyRejected("release workflow key is not Ed25519")
    allowed = ("cloudx-release %s %s\n" % (derived[0], derived[1])).encode("ascii")
    try:
        roots = trust._signer_bytes(root)
        current = trust._fingerprint(roots)
        candidate = trust._fingerprint(allowed)
    except trust.RecoveryRejected as exc:
        raise WorkflowKeyRejected("release public trust roots are invalid") from exc
    if candidate != current or allowed != roots:
        raise WorkflowKeyRejected("release workflow private key does not match the committed trust root")
    return candidate


def _workflow_contract(root: pathlib.Path) -> None:
    path = root / ".github/workflows" / WORKFLOW
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise WorkflowKeyRejected("release workflow is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or len(raw) > 256 * 1024:
        raise WorkflowKeyRejected("release workflow is unsafe or oversized")
    text = raw.decode("utf-8")
    required = (
        "workflow_dispatch:",
        "environment: release",
        "secrets.CLOUDX_RELEASE_SIGNING_KEY",
        "./verify.sh",
        "scripts/create_release.py",
        "scripts/create_stable_index.py",
        "scripts/verify_release.py",
        "scripts/publish_release_refs.py",
    )
    if any(value not in text for value in required):
        raise WorkflowKeyRejected("release workflow contract is incomplete")
    if text.count("if: startsWith(github.ref, 'refs/tags/v')") < 2:
        raise WorkflowKeyRejected("release workflow does not isolate publication to tags")


def _gh_auth(repository: str) -> None:
    _require_success(
        _run(["gh", "auth", "status", "--hostname", "github.com"]),
        "GitHub authentication",
    )
    name = _require_success(
        _run([
            "gh",
            "api",
            "repos/%s/environments/%s" % (repository, ENVIRONMENT),
            "--jq",
            ".name",
        ]),
        "GitHub release environment lookup",
    ).decode("utf-8", errors="replace").strip()
    if name != ENVIRONMENT:
        raise WorkflowKeyRejected("GitHub release environment is unavailable")


def _json_output(completed: subprocess.CompletedProcess[bytes], label: str) -> Any:
    raw = _require_success(completed, label)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowKeyRejected("%s returned invalid JSON" % label) from exc


def _environment_secret_present(repository: str) -> bool:
    document = _json_output(
        _run([
            "gh",
            "secret",
            "list",
            "--repo",
            repository,
            "--env",
            ENVIRONMENT,
            "--json",
            "name,updatedAt",
        ]),
        "GitHub environment secret inventory",
    )
    if not isinstance(document, list):
        raise WorkflowKeyRejected("GitHub environment secret inventory is invalid")
    matches = [item for item in document if isinstance(item, dict) and item.get("name") == SECRET_NAME]
    if len(matches) > 1:
        raise WorkflowKeyRejected("GitHub release workflow secret inventory is ambiguous")
    return len(matches) == 1


def _release_refs(version: str, root: pathlib.Path) -> Dict[str, str]:
    names = (
        "refs/heads/release/stable",
        "refs/heads/release-artifacts/v%s" % version,
        "refs/tags/v%s" % version,
    )
    raw = _require_success(
        _run(["git", "ls-remote", "--refs", "origin", *names], cwd=root),
        "release reference inventory",
    ).decode("ascii", errors="replace")
    values: Dict[str, str] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[1] not in names or not COMMIT_RE.fullmatch(fields[0]):
            raise WorkflowKeyRejected("release reference inventory is invalid")
        values[fields[1]] = fields[0]
    return values


def _run_inventory(repository: str) -> Sequence[Mapping[str, Any]]:
    document = _json_output(
        _run([
            "gh",
            "run",
            "list",
            "--repo",
            repository,
            "--workflow",
            WORKFLOW,
            "--event",
            "workflow_dispatch",
            "--branch",
            BRANCH,
            "--limit",
            "30",
            "--json",
            "databaseId,event,headBranch,headSha,status,conclusion",
        ]),
        "release workflow run inventory",
    )
    if not isinstance(document, list):
        raise WorkflowKeyRejected("release workflow run inventory is invalid")
    return [item for item in document if isinstance(item, dict)]


def _dispatch_run(repository: str, head: str, before: Set[int]) -> int:
    _require_success(
        _run([
            "gh",
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            repository,
            "--ref",
            BRANCH,
        ]),
        "release workflow dispatch",
    )
    deadline = time.monotonic() + RUN_DISCOVERY_SECONDS
    while time.monotonic() < deadline:
        for item in _run_inventory(repository):
            run_id = item.get("databaseId")
            if (
                isinstance(run_id, int)
                and run_id not in before
                and item.get("event") == "workflow_dispatch"
                and item.get("headBranch") == BRANCH
                and item.get("headSha") == head
            ):
                return run_id
        time.sleep(POLL_SECONDS)
    raise WorkflowKeyRejected("release workflow canary run was not discovered after secret update")


def _wait_run(repository: str, run_id: int, head: str) -> None:
    deadline = time.monotonic() + RUN_COMPLETION_SECONDS
    while time.monotonic() < deadline:
        document = _json_output(
            _run([
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                repository,
                "--json",
                "databaseId,event,headBranch,headSha,status,conclusion",
            ]),
            "release workflow canary status",
        )
        if (
            not isinstance(document, dict)
            or document.get("databaseId") != run_id
            or document.get("event") != "workflow_dispatch"
            or document.get("headBranch") != BRANCH
            or document.get("headSha") != head
        ):
            raise WorkflowKeyRejected("release workflow canary identity changed")
        if document.get("status") == "completed":
            if document.get("conclusion") != "success":
                raise WorkflowKeyRejected(
                    "workflow key was updated but the signing canary failed; do not create a release tag"
                )
            return
        time.sleep(POLL_SECONDS)
    raise WorkflowKeyRejected(
        "workflow key was updated but the signing canary did not complete; do not create a release tag"
    )


def plan(version: str, key_configured: bool) -> Dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "status": "confirmation-required",
        "version": version,
        "repository": EXPECTED_REPOSITORY,
        "branch": BRANCH,
        "workflow": WORKFLOW,
        "environment": ENVIRONMENT,
        "secret": SECRET_NAME,
        "privateKeyConfigured": key_configured,
        "confirmation": confirmation(version),
        "automaticAction": False,
        "preconditions": [
            "clean_pushed_main",
            "private_key_matches_committed_public_root",
            "github_cli_authenticated",
            "release_environment_exists",
            "workflow_dispatch_is_non_publishing",
            "release_refs_absent_or_unchanged",
        ],
        "authorization": {
            "environmentSecretWrite": False,
            "workflowDispatch": False,
            "tagCreate": False,
            "artifactPublication": False,
            "stableMove": False,
            "endpointStage": False,
            "endpointActivation": False,
            "serviceRestart": False,
        },
    }


def _synchronize(root: pathlib.Path, version: str, private_key: pathlib.Path) -> Dict[str, Any]:
    if version != _version(root):
        raise WorkflowKeyRejected("requested version must equal repository VERSION")
    _git_clean(root)
    repository = _origin_repository(root)
    head = _head_commit(root)
    if _remote_head(root) != head:
        raise WorkflowKeyRejected("repository HEAD must be pushed to origin/main before secret synchronization")
    key_bytes = _safe_key_bytes(private_key, root)
    fingerprint = _key_fingerprint(private_key, root)
    _workflow_contract(root)
    _gh_auth(repository)
    secret_existed = _environment_secret_present(repository)
    refs_before = _release_refs(version, root)
    artifact_ref = "refs/heads/release-artifacts/v%s" % version
    tag_ref = "refs/tags/v%s" % version
    if artifact_ref in refs_before or tag_ref in refs_before:
        raise WorkflowKeyRejected("the requested release tag or artifact ref already exists")
    before_runs = {
        item["databaseId"]
        for item in _run_inventory(repository)
        if isinstance(item.get("databaseId"), int)
    }

    completed = _run(
        [
            "gh",
            "secret",
            "set",
            SECRET_NAME,
            "--repo",
            repository,
            "--env",
            ENVIRONMENT,
        ],
        input_bytes=key_bytes,
    )
    if completed.returncode != 0:
        raise WorkflowKeyRejected(
            "workflow secret update did not return success; inspect its metadata and do not create a release tag"
        )
    try:
        if not _environment_secret_present(repository):
            raise WorkflowKeyRejected("environment secret metadata is unavailable")
        run_id = _dispatch_run(repository, head, before_runs)
        _wait_run(repository, run_id, head)
        if _release_refs(version, root) != refs_before:
            raise WorkflowKeyRejected("the non-publishing canary changed release refs")
    except WorkflowKeyRejected as exc:
        if str(exc).startswith("workflow key was updated"):
            raise
        raise WorkflowKeyRejected(
            "workflow key was updated but signing-canary verification failed; do not create a release tag"
        ) from exc
    return {
        "schema": RESULT_SCHEMA,
        "status": "canary-accepted",
        "version": version,
        "repository": repository,
        "branch": BRANCH,
        "workflow": WORKFLOW,
        "environment": ENVIRONMENT,
        "secret": SECRET_NAME,
        "headCommit": head,
        "signerFingerprint": fingerprint,
        "secretExistedBefore": secret_existed,
        "environmentSecretUpdated": True,
        "workflowDispatched": True,
        "runId": run_id,
        "signedReleaseVerified": True,
        "releaseRefsUnchanged": True,
        "tagCreated": False,
        "artifactRefPublished": False,
        "stableMoved": False,
        "endpointStaged": False,
        "endpointActivated": False,
        "serviceRestarted": False,
    }


def synchronize(root: pathlib.Path, version: str, private_key: pathlib.Path) -> Dict[str, Any]:
    with _transaction_lock():
        return _synchronize(root, version, private_key)


def main(argv: Optional[Sequence[str]] = None, root: pathlib.Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=_version(root))
    parser.add_argument("--private-key", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if not VERSION_RE.fullmatch(args.version) or args.version != _version(root):
            raise WorkflowKeyRejected("requested version must equal repository VERSION")
        if not args.apply:
            result = plan(args.version, args.private_key is not None)
        else:
            if args.confirm != confirmation(args.version):
                raise WorkflowKeyRejected("release workflow key confirmation does not match")
            if args.private_key is None:
                raise WorkflowKeyRejected("--private-key is required for workflow-key synchronization")
            result = synchronize(root, args.version, args.private_key)
    except WorkflowKeyRejected as exc:
        print("release-workflow-key: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
