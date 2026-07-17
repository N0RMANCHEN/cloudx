from __future__ import annotations

import hashlib
import json
import pkgutil
from typing import Any, Dict

from .public_metadata import validate_public_document


RESOURCE = "data/contracts/phi-mesh-compatibility-profile.v1.json"
SCHEMA = "cloudx.phi-mesh-compatibility-profile.v1"
SHA256 = "e5877a7f2588198b82bfc6dc55dfd18c851a77487c59ab67fad6629a56dca2c3"


def read_profile() -> Dict[str, Any]:
    raw = pkgutil.get_data("cloudx_cloud", RESOURCE)
    if raw is None:
        raise RuntimeError("Phi Mesh compatibility profile is missing")
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Phi Mesh compatibility profile digest is invalid")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Phi Mesh compatibility profile is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise RuntimeError("Phi Mesh compatibility profile schema is unsupported")
    return validate_public_document(document, SCHEMA)
