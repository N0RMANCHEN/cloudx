from __future__ import annotations

import hashlib
import json
import pkgutil
from typing import Any, Dict

from .public_metadata import validate_public_document


RESOURCE = "data/contracts/phi-cloud-consumer-traffic-policy.v1.json"
SCHEMA = "cloudx.phi-cloud-consumer-traffic-policy.v1"
SHA256 = "128dde9f5b76375d1d72f1542a33d76f53ff5a2361fcc065a4dff367f9f1790a"


def read_policy() -> Dict[str, Any]:
    raw = pkgutil.get_data("cloudx_cloud", RESOURCE)
    if raw is None:
        raise RuntimeError("Phi cloud consumer traffic policy is missing")
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Phi cloud consumer traffic policy digest is invalid")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Phi cloud consumer traffic policy is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise RuntimeError("Phi cloud consumer traffic policy schema is unsupported")
    return validate_public_document(document, SCHEMA)
