from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any


def ensure_private_directory(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def atomic_write(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    ensure_private_directory(path.parent)
    descriptor, temp_name = tempfile.mkstemp(prefix=".cloudx-", dir=str(path.parent))
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_json(path: pathlib.Path, value: Any, mode: int = 0o600) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"), mode=mode)
