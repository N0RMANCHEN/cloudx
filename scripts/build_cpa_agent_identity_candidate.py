#!/usr/bin/env python3
"""Build the exact side-by-side CLIProxyAPI Agent Identity candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "third_party/cliproxyapi/agent-identity-manifest.json"
RESULT_SCHEMA = "cloudx.cliproxy-agent-identity-build.v1"
PROTECTED_OUTPUTS = {
    pathlib.Path("/usr/local/bin/cli-proxy-api"),
    pathlib.Path.home() / ".local/bin/cli-proxy-api",
}


class CandidateBuildRejected(RuntimeError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: pathlib.Path = MANIFEST_PATH) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildRejected("Agent Identity manifest is unavailable") from exc
    required = {
        "upstreamRepository",
        "upstreamTag",
        "upstreamCommit",
        "patch",
        "patchSha256",
        "goVersion",
        "goos",
        "goarch",
        "version",
        "commitLabel",
        "buildDate",
        "candidateSha256",
        "candidateSize",
        "capabilities",
        "capabilityProbePath",
        "capabilityProbeHeader",
        "preservesFastServiceTier",
    }
    if document.get("schema") != "cloudx.cliproxy-agent-identity.v1" or not required.issubset(document):
        raise CandidateBuildRejected("Agent Identity manifest is invalid")
    if document["capabilities"] != ["codex-agent-identity-v1"]:
        raise CandidateBuildRejected("Agent Identity capability contract is invalid")
    return document


def run(
    argv: Sequence[str],
    *,
    cwd: pathlib.Path,
    env: Dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=str(cwd),
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise CandidateBuildRejected("Agent Identity candidate command failed") from exc


def git_output(source: pathlib.Path, *args: str) -> str:
    return run(["git", *args], cwd=source).stdout.strip()


def verified_patch(manifest: Dict[str, Any]) -> pathlib.Path:
    base = MANIFEST_PATH.parent.resolve()
    path = (base / str(manifest["patch"])).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise CandidateBuildRejected("Agent Identity patch escapes its package") from exc
    if not path.is_file() or path.is_symlink():
        raise CandidateBuildRejected("Agent Identity patch is unavailable")
    if sha256_file(path) != manifest["patchSha256"]:
        raise CandidateBuildRejected("Agent Identity patch digest does not match")
    return path


def verify_source(source: pathlib.Path, manifest: Dict[str, Any]) -> None:
    if not source.is_absolute() or not source.is_dir() or source.is_symlink():
        raise CandidateBuildRejected("CPA source must be an absolute regular directory")
    if git_output(source, "rev-parse", "HEAD") != manifest["upstreamCommit"]:
        raise CandidateBuildRejected("CPA source commit does not match the pinned target")
    if git_output(source, "status", "--porcelain", "--untracked-files=all"):
        raise CandidateBuildRejected("CPA source checkout must be clean")
    go_mod = source / "go.mod"
    if not go_mod.is_file() or go_mod.is_symlink():
        raise CandidateBuildRejected("CPA source go.mod is unavailable")
    if "go %s" % manifest["goVersion"] not in go_mod.read_text(encoding="utf-8").splitlines():
        raise CandidateBuildRejected("CPA source Go version does not match")


def verify_output(output: pathlib.Path) -> None:
    if not output.is_absolute():
        raise CandidateBuildRejected("CPA candidate output must be absolute")
    output = output.resolve(strict=False)
    if output in {path.resolve(strict=False) for path in PROTECTED_OUTPUTS}:
        raise CandidateBuildRejected("CPA build cannot replace an active binary")
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise CandidateBuildRejected("CPA candidate binaries cannot enter the Cloudx repository")
    if output.exists() or output.is_symlink():
        raise CandidateBuildRejected("CPA candidate output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise CandidateBuildRejected("CPA candidate output directory is unavailable")


def plan_document(manifest: Dict[str, Any], output: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": "planned",
        "upstreamCommit": manifest["upstreamCommit"],
        "patchSha256": manifest["patchSha256"],
        "goVersion": manifest["goVersion"],
        "goos": manifest["goos"],
        "goarch": manifest["goarch"],
        "version": manifest["version"],
        "capabilities": list(manifest["capabilities"]),
        "outputName": output.name,
        "installs": False,
        "activates": False,
        "restarts": False,
    }


def test_commands(go_binary: str) -> list[list[str]]:
    return [
        [
            go_binary,
            "test",
            "./internal/runtime/executor",
            "-run",
            "CodexAgentIdentity",
            "-count=1",
        ],
        [go_binary, "test", "./internal/api", "-run", "Healthz", "-count=1"],
        [
            go_binary,
            "test",
            "./internal/translator/codex/openai/responses",
            "-run",
            "FastServiceTier",
            "-count=1",
        ],
    ]


def build_candidate(
    source: pathlib.Path,
    output: pathlib.Path,
    go_binary: str,
    manifest: Dict[str, Any],
    patch: pathlib.Path,
) -> Dict[str, Any]:
    verify_output(output)
    go_version = run([go_binary, "version"], cwd=source).stdout
    if "go%s" % manifest["goVersion"] not in go_version:
        raise CandidateBuildRejected("active Go toolchain does not match the pinned version")

    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-agent-identity-build-") as temporary:
        work = pathlib.Path(temporary) / "source"
        shutil.copytree(source, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        run(["git", "apply", "--check", str(patch)], cwd=work)
        run(["git", "apply", str(patch)], cwd=work)
        for command in test_commands(go_binary):
            run(command, cwd=work, env=os.environ.copy())

        build_env = os.environ.copy()
        build_env.update(
            {
                "CGO_ENABLED": "0",
                "GOOS": str(manifest["goos"]),
                "GOARCH": str(manifest["goarch"]),
            }
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".%s." % output.name,
            suffix=".candidate",
            dir=str(output.parent),
        )
        os.close(descriptor)
        temporary_output = pathlib.Path(temporary_name)
        try:
            ldflags = " ".join(
                [
                    "-s",
                    "-w",
                    "-X main.Version=%s" % manifest["version"],
                    "-X main.Commit=%s" % manifest["commitLabel"],
                    "-X main.BuildDate=%s" % manifest["buildDate"],
                ]
            )
            run(
                [
                    go_binary,
                    "build",
                    "-buildvcs=false",
                    "-trimpath",
                    "-ldflags",
                    ldflags,
                    "-o",
                    str(temporary_output),
                    "./cmd/server",
                ],
                cwd=work,
                env=build_env,
            )
            temporary_output.chmod(0o755)
            digest = sha256_file(temporary_output)
            size = temporary_output.stat().st_size
            if digest != manifest["candidateSha256"] or size != manifest["candidateSize"]:
                raise CandidateBuildRejected("CPA candidate bytes do not match the pinned build")
            with temporary_output.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_output, output)
            directory = os.open(str(output.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary_output.exists():
                temporary_output.unlink()

    document = plan_document(manifest, output)
    document.update(
        {
            "status": "built",
            "sha256": manifest["candidateSha256"],
            "size": manifest["candidateSize"],
            "focusedTestCommands": len(test_commands(go_binary)),
        }
    )
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    source = args.source.expanduser().resolve()
    output = args.output.expanduser()
    if not output.is_absolute():
        raise CandidateBuildRejected("CPA candidate output must be absolute")
    patch = verified_patch(manifest)
    verify_source(source, manifest)
    document = (
        build_candidate(source, output, args.go, manifest, patch)
        if args.build
        else plan_document(manifest, output)
    )
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateBuildRejected as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "status": "rejected", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(2)
