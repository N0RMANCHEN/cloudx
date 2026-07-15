from __future__ import annotations

import pkgutil
from typing import Tuple


TEMPLATES: Tuple[str, ...] = (
    "cloudx-account-state.service",
    "cloudx-account-state.timer",
    "cloudx-cpa-health.service",
    "cloudx-cpa-health.timer",
    "cloudx-health.service",
    "cloudx-health.timer",
)


def read_template(name: str) -> str:
    if name not in TEMPLATES:
        raise ValueError("unknown Cloudx systemd template")
    data = pkgutil.get_data("cloudx_cloud", "data/systemd/%s" % name)
    if not data:
        raise RuntimeError("Cloudx systemd template is missing")
    return data.decode("utf-8")
