#!/usr/bin/env python3
"""Build an exact, side-by-side CLIProxyAPI policy candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "third_party/cliproxyapi/policy-manifest.json"
RESULT_SCHEMA = "cloudx.cliproxy-policy-build.v1"
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
        raise CandidateBuildRejected("CPA policy manifest is unavailable") from exc
    if document.get("schema") != "cloudx.cliproxy-policy.v1":
        raise CandidateBuildRejected("CPA policy manifest schema is invalid")
    targets = document.get("targets")
    if not isinstance(targets, dict) or set(targets) != {"local", "cloud"}:
        raise CandidateBuildRejected("CPA policy manifest targets are invalid")
    return document


def target_config(target: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    value = manifest["targets"].get(target)
    required = {
        "upstreamCommit",
        "patch",
        "patchSha256",
        "supplementalPatches",
        "goVersion",
        "goos",
        "goarch",
        "version",
        "commitLabel",
        "buildDate",
        "candidateSha256",
        "candidateSize",
    }
    if not isinstance(value, dict) or not required.issubset(value):
        raise CandidateBuildRejected("CPA policy target is incomplete")
    capabilities = value.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
        raise CandidateBuildRejected("CPA policy target capabilities are invalid")
    return value


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
        raise CandidateBuildRejected("CPA candidate command failed") from exc


def git_output(source: pathlib.Path, *args: str) -> str:
    return run(["git", *args], cwd=source).stdout.strip()


def verified_patch(config: Dict[str, Any]) -> pathlib.Path:
    base = MANIFEST_PATH.parent.resolve()
    patch = (base / str(config["patch"])).resolve()
    try:
        patch.relative_to(base)
    except ValueError as exc:
        raise CandidateBuildRejected("CPA policy patch escapes its package") from exc
    if not patch.is_file() or patch.is_symlink():
        raise CandidateBuildRejected("CPA policy patch is unavailable")
    if sha256_file(patch) != config["patchSha256"]:
        raise CandidateBuildRejected("CPA policy patch digest does not match")
    return patch


def verified_patches(config: Dict[str, Any]) -> List[pathlib.Path]:
    result = [verified_patch(config)]
    supplemental = config.get("supplementalPatches")
    if not isinstance(supplemental, list):
        raise CandidateBuildRejected("CPA supplemental patch list is invalid")
    base = MANIFEST_PATH.parent.resolve()
    for item in supplemental:
        if (
            not isinstance(item, dict)
            or not {"path", "sha256"}.issubset(item)
            or not set(item).issubset({"path", "sha256", "includePaths"})
        ):
            raise CandidateBuildRejected("CPA supplemental patch entry is invalid")
        includes = item.get("includePaths", [])
        if not isinstance(includes, list) or any(
            not isinstance(value, str)
            or not value
            or value.startswith("/")
            or ".." in pathlib.PurePosixPath(value).parts
            for value in includes
        ):
            raise CandidateBuildRejected("CPA supplemental patch include paths are invalid")
        patch = (base / str(item["path"])).resolve()
        try:
            patch.relative_to(base)
        except ValueError as exc:
            raise CandidateBuildRejected("CPA supplemental patch escapes its package") from exc
        if not patch.is_file() or patch.is_symlink():
            raise CandidateBuildRejected("CPA supplemental patch is unavailable")
        if sha256_file(patch) != item["sha256"]:
            raise CandidateBuildRejected("CPA supplemental patch digest does not match")
        result.append(patch)
    return result


def patch_include_paths(config: Dict[str, Any], index: int) -> List[str]:
    if index == 0:
        return []
    return list(config["supplementalPatches"][index - 1].get("includePaths", []))


def verify_source(source: pathlib.Path, config: Dict[str, Any]) -> None:
    if not source.is_absolute() or not source.is_dir() or source.is_symlink():
        raise CandidateBuildRejected("CPA source must be an absolute regular directory")
    if git_output(source, "rev-parse", "HEAD") != config["upstreamCommit"]:
        raise CandidateBuildRejected("CPA source commit does not match the pinned target")
    if git_output(source, "status", "--porcelain", "--untracked-files=all"):
        raise CandidateBuildRejected("CPA source checkout must be clean")
    go_mod = source / "go.mod"
    if not go_mod.is_file() or go_mod.is_symlink():
        raise CandidateBuildRejected("CPA source go.mod is unavailable")
    expected = "go %s" % config["goVersion"]
    if expected not in go_mod.read_text(encoding="utf-8").splitlines():
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


def plan_document(target: str, config: Dict[str, Any], output: pathlib.Path) -> Dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": "planned",
        "target": target,
        "upstreamCommit": config["upstreamCommit"],
        "patchSha256": config["patchSha256"],
        "supplementalPatchSha256s": [item["sha256"] for item in config["supplementalPatches"]],
        "goVersion": config["goVersion"],
        "goos": config["goos"],
        "goarch": config["goarch"],
        "version": config["version"],
        "capabilities": list(config.get("capabilities", [])),
        "outputName": output.name,
        "installs": False,
        "activates": False,
        "restarts": False,
    }


def test_commands(target: str, config: Dict[str, Any]) -> List[List[str]]:
    commands = [
        [
            "go",
            "test",
            "./internal/api",
            "./sdk/api/handlers",
            "./sdk/cliproxy/auth",
            "-run",
            "Cloudx",
            "-count=1",
        ],
    ]
    if target == "local":
        commands.append(
            [
                "go",
                "test",
                "./internal/translator/codex/openai/responses",
                "-run",
                "FastServiceTier",
                "-count=1",
            ]
        )
    if "codex-agent-identity-v1" in config.get("capabilities", []):
        commands.extend([
            [
                "go",
                "test",
                "./internal/runtime/executor",
                "-run",
                "CodexAgentIdentity",
                "-count=1",
            ],
            ["go", "test", "./internal/api", "-run", "Healthz", "-count=1"],
            [
                "go",
                "test",
                "./internal/translator/codex/openai/responses",
                "-run",
                "FastServiceTier",
                "-count=1",
            ],
        ])
    return commands


def build_candidate(
    target: str,
    source: pathlib.Path,
    output: pathlib.Path,
    go_binary: str,
    config: Dict[str, Any],
    patches: Sequence[pathlib.Path],
) -> Dict[str, Any]:
    verify_output(output)
    go_version = run([go_binary, "version"], cwd=source).stdout
    if "go%s" % config["goVersion"] not in go_version:
        raise CandidateBuildRejected("active Go toolchain does not match the pinned version")

    with tempfile.TemporaryDirectory(prefix="cloudx-cpa-build-") as temporary:
        work = pathlib.Path(temporary) / "source"
        shutil.copytree(source, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for index, patch in enumerate(patches):
            include_arguments = [
                argument
                for path in patch_include_paths(config, index)
                for argument in ("--include", path)
            ]
            run(["git", "apply", *include_arguments, "--check", str(patch)], cwd=work)
            run(["git", "apply", *include_arguments, str(patch)], cwd=work)

        format_packages = ["./internal/api", "./sdk/api/handlers", "./sdk/cliproxy/auth"]
        if target == "local":
            format_packages.append("./internal/translator/codex/openai/responses")
        if "codex-agent-identity-v1" in config.get("capabilities", []):
            format_packages.extend([
                "./internal/runtime/executor",
                "./internal/translator/codex/openai/responses",
            ])
        run([go_binary, "fmt", *format_packages], cwd=work)

        for command in test_commands(target, config):
            command[0] = go_binary
            run(command, cwd=work, env=os.environ.copy())

        build_env = os.environ.copy()
        build_env.update(
            {
                "CGO_ENABLED": "0",
                "GOOS": str(config["goos"]),
                "GOARCH": str(config["goarch"]),
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
                    "-X main.Version=%s" % config["version"],
                    "-X main.Commit=%s" % config["commitLabel"],
                    "-X main.BuildDate=%s" % config["buildDate"],
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
            candidate_digest = sha256_file(temporary_output)
            candidate_size = temporary_output.stat().st_size
            if (
                candidate_digest != config["candidateSha256"]
                or candidate_size != config["candidateSize"]
            ):
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

    document = plan_document(target, config, output)
    document.update(
        {
            "status": "built",
            "sha256": config["candidateSha256"],
            "size": config["candidateSize"],
            "focusedTestCommands": len(test_commands(target, config)),
        }
    )
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "cloud"), required=True)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    config = target_config(args.target, manifest)
    source = args.source.expanduser().resolve()
    output = args.output.expanduser()
    if not output.is_absolute():
        raise CandidateBuildRejected("CPA candidate output must be absolute")
    patches = verified_patches(config)
    verify_source(source, config)
    if args.build:
        document = build_candidate(args.target, source, output, args.go, config, patches)
    else:
        document = plan_document(args.target, config, output)
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateBuildRejected as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "status": "rejected", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(2)
