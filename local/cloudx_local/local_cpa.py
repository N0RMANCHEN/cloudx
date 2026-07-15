from __future__ import annotations

import pathlib
import subprocess
from typing import Sequence

from .config import LocalConfig


def legacy_command(config: LocalConfig) -> pathlib.Path:
    return config.home / ".local/bin/codexx-legacy"


def import_local(config: LocalConfig, source: str, extra: Sequence[str]) -> int:
    command = legacy_command(config)
    if not command.is_file() and not command.is_symlink():
        raise RuntimeError(
            "local CPA import compatibility is unavailable; install codexx-legacy or use a named account import"
        )
    completed = subprocess.run([str(command), "import", source, *extra], check=False)
    return int(completed.returncode)
