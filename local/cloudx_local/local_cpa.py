from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Sequence

from . import import_ui
from .config import LocalConfig


def legacy_command(config: LocalConfig) -> pathlib.Path:
    return config.home / ".local/bin/codexx-legacy"


def import_local(config: LocalConfig, source: str, extra: Sequence[str]) -> int:
    human = import_ui.human_output()
    command = legacy_command(config)
    if not command.is_file() and not command.is_symlink():
        reason = "local CPA import compatibility is unavailable; install codexx-legacy or use a named account import"
        if human:
            import_ui.render(import_ui.failure_report(import_ui.LOCAL_CPA_DESTINATION, reason), stream=sys.stderr)
            return 1
        raise RuntimeError(reason)
    arguments = [str(command), "import", source, *extra]
    try:
        if not human:
            completed = subprocess.run(arguments, check=False)
            return int(completed.returncode)
        completed = subprocess.run(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        reason = "local CPA migration adapter could not be started: %s" % (exc.strerror or str(exc))
        if human:
            import_ui.render(import_ui.failure_report(import_ui.LOCAL_CPA_DESTINATION, reason), stream=sys.stderr)
            return 1
        raise RuntimeError(reason) from exc
    if completed.returncode == 0:
        import_ui.render(import_ui.legacy_success_report(completed.stdout))
    else:
        import_ui.render(
            import_ui.legacy_failure_report(completed.returncode, completed.stdout, completed.stderr),
            stream=sys.stderr,
        )
    return int(completed.returncode)
