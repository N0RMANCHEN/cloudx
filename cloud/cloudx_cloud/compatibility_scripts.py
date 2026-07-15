from __future__ import annotations

import pkgutil
from typing import Tuple


SCRIPTS: Tuple[str, ...] = ("codex-gateway-import",)


def read_compatibility_script(name: str) -> str:
    if name not in SCRIPTS:
        raise ValueError("unknown Cloudx compatibility script")
    data = pkgutil.get_data("cloudx_cloud", "data/compat/%s" % name)
    if not data:
        raise RuntimeError("Cloudx compatibility script is missing")
    return data.decode("utf-8")
