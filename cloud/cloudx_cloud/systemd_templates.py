from __future__ import annotations

import pkgutil
from typing import Tuple


TEMPLATES: Tuple[str, ...] = (
    "cloudx-account-state.service",
    "cloudx-account-state.timer",
    "cloudx-cpa-failure.path",
    "cloudx-cpa-failure.service",
    "cloudx-cpa-health.service",
    "cloudx-cpa-health.timer",
    "cloudx-health.service",
    "cloudx-health.timer",
    "cloudx-legacy-health-bridge.env.example",
    "cloudx-legacy-health-bridge-canary.service",
    "cloudx-legacy-health-bridge.service",
    "cloudx-legacy-health-bridge.timer",
)


def read_template(name: str) -> str:
    if name not in TEMPLATES:
        raise ValueError("unknown Cloudx systemd template")
    data = pkgutil.get_data("cloudx_cloud", "data/systemd/%s" % name)
    if not data:
        raise RuntimeError("Cloudx systemd template is missing")
    return data.decode("utf-8")
