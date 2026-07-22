from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional, Sequence

from . import broker, cloud_cli, codexx_cli
from . import updater
from .config import LocalConfig
from .version import PROTOCOL_MAX, PROTOCOL_MIN, VERSION


def _schedule_update_check() -> None:
    try:
        updater.maybe_schedule_check(LocalConfig.load())
    except (OSError, RuntimeError):
        pass


def _maybe_schedule_update_check(arguments: Sequence[str]) -> None:
    if arguments[:1] == ["upgrade"] or arguments[:2] == ["cloud", "upgrade"]:
        return
    _schedule_update_check()


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    program = pathlib.Path(sys.argv[0]).name
    if program == "codexx":
        _maybe_schedule_update_check(arguments)
        return codexx_cli.main(arguments)
    if program == "cloud":
        _maybe_schedule_update_check(arguments)
        return cloud_cli.main(arguments)
    if program == "cloudx-update":
        return updater.main(arguments)
    if arguments[:1] == ["_broker"]:
        return broker.main(arguments[1:])
    if arguments[:1] == ["_broker-control"]:
        return broker.control_main(arguments[1:])
    if arguments == ["self-check"]:
        print(json.dumps({
            "schema": "cloudx.self-check.v1",
            "component": "local",
            "version": VERSION,
            "protocol": {"min": PROTOCOL_MIN, "max": PROTOCOL_MAX},
            "status": "ok",
        }, sort_keys=True, separators=(",", ":")))
        return 0
    if not arguments:
        raise RuntimeError("invoke this artifact as codexx, cloud, or cloudx-update")
    command = arguments.pop(0)
    if command == "codexx":
        _maybe_schedule_update_check(arguments)
        return codexx_cli.main(arguments)
    if command == "cloud":
        _maybe_schedule_update_check(arguments)
        return cloud_cli.main(arguments)
    if command in ("update", "cloudx-update"):
        return updater.main(arguments)
    raise RuntimeError("unknown local component entrypoint: %s" % command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("cloudx: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
