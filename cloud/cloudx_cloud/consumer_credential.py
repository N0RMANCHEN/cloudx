from __future__ import annotations

import hashlib
import json
import pkgutil
from typing import Any, Dict

from .public_metadata import validate_public_document


RESOURCE = "data/contracts/phi-cloud-consumer-credential.v1.json"
SCHEMA = "cloudx.phi-cloud-consumer-credential.v1"
SHA256 = "bfe39440d0296ef5b4a3d7bb674fac632badfb869fee0fc8fc101f7447cc1d5b"


def read_policy() -> Dict[str, Any]:
    raw = pkgutil.get_data("cloudx_cloud", RESOURCE)
    if raw is None:
        raise RuntimeError("Phi cloud consumer credential policy is missing")
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError("Phi cloud consumer credential policy digest is invalid")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Phi cloud consumer credential policy is invalid") from exc
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise RuntimeError("Phi cloud consumer credential policy schema is unsupported")
    return validate_public_document(document, SCHEMA)
