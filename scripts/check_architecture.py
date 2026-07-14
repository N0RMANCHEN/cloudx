#!/usr/bin/env python3
"""Small architecture gate for the Cloudx ownership and safety boundaries."""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Iterable, List


ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config/governance/architecture_rules.json"


def iter_watched(roots: Iterable[str], suffixes: Iterable[str]) -> Iterable[pathlib.Path]:
    allowed = set(suffixes)
    for name in roots:
        base = ROOT / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in allowed:
                yield path


def relative(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check() -> List[str]:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    errors: List[str] = []

    for name in rules["required_paths"]:
        if not (ROOT / name).exists():
            errors.append("missing required path: %s" % name)

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for path in (ROOT / "local/cloudx_local/version.py", ROOT / "cloud/cloudx_cloud/version.py"):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if 'VERSION = "%s"' % version not in text:
            errors.append("endpoint version does not match VERSION: %s" % relative(path))

    frozen = rules.get("frozen_files", {})
    default_limit = int(rules["max_watched_lines"])
    for path in iter_watched(rules["watched_roots"], rules["watched_suffixes"]):
        name = relative(path)
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        limit = int(frozen.get(name, default_limit))
        if line_count > limit:
            errors.append("%s has %d lines; limit is %d" % (name, line_count, limit))

    python_files = list(ROOT.glob("local/**/*.py"))
    for path in python_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(?:from|import)\s+cloud(?:\.|\s|$)", text, re.MULTILINE):
            errors.append("local endpoint imports cloud implementation: %s" % relative(path))

    python_files = list(ROOT.glob("cloud/**/*.py"))
    for path in python_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(?:from|import)\s+local(?:\.|\s|$)", text, re.MULTILINE):
            errors.append("cloud endpoint imports local implementation: %s" % relative(path))

    runtime_roots = [ROOT / "local", ROOT / "cloud", ROOT / "scripts"]
    for base in runtime_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".service", ".timer"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for fragment in rules["forbidden_runtime_fragments"]:
                if fragment in text:
                    errors.append("forbidden runtime fragment %r in %s" % (fragment, relative(path)))
            if re.search(r"^\s*(?:from|import)\s+phi(?:\.|\s|$)", text, re.MULTILINE):
                errors.append("Cloudx runtime depends on Phi: %s" % relative(path))

    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print("architecture: %s" % error, file=sys.stderr)
        return 1
    print("architecture: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
