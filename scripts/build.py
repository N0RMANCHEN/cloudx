#!/usr/bin/env python3
"""Build independent, deterministic local and cloud zipapps."""

from __future__ import annotations

import argparse
import pathlib
import tempfile
import zipfile
from typing import Iterable, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def source_files(source: pathlib.Path) -> Iterable[pathlib.Path]:
    for path in sorted(source.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            yield path


def build_component(component: str, destination: pathlib.Path, version: str) -> pathlib.Path:
    source = ROOT / component
    if not (source / "__main__.py").is_file():
        raise RuntimeError("%s component has no __main__.py" % component)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ("cloudx-%s-%s.pyz" % (component, version))
    with target.open("wb") as raw:
        raw.write(b"#!/usr/bin/env python3\n")
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in source_files(source):
                name = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(name, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
                archive.writestr(info, path.read_bytes())
    target.chmod(0o755)
    return target


def build_all(destination: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path]:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return (
        build_component("local", destination, version),
        build_component("cloud", destination, version),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="build in a temporary directory")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "dist")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="cloudx-build-") as value:
            artifacts = build_all(pathlib.Path(value))
            print("build: ok (%s)" % ", ".join(path.name for path in artifacts))
    else:
        artifacts = build_all(args.output)
        for artifact in artifacts:
            print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
