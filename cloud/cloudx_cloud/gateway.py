from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GatewayProbe:
    status: str
    http_status: Optional[int]
    detail: str


def read_credential(path: pathlib.Path) -> str:
    stat = path.stat()
    if stat.st_mode & 0o077:
        raise RuntimeError("client credential file permissions must be 0600 or stricter")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("client credential is empty")
    if value.startswith("{"):
        data = json.loads(value)
        if not isinstance(data, dict) or not isinstance(data.get("apiKey"), str):
            raise RuntimeError("client credential JSON is invalid")
        value = data["apiKey"].strip()
    if not value:
        raise RuntimeError("client credential is empty")
    return value


def probe_gateway(url: str, credential_file: Optional[pathlib.Path] = None, timeout: float = 2.0) -> GatewayProbe:
    headers = {"Accept": "application/json"}
    if credential_file and credential_file.is_file():
        try:
            headers["Authorization"] = "Bearer %s" % read_credential(credential_file)
        except (OSError, ValueError, RuntimeError):
            return GatewayProbe("degraded", None, "credential_invalid")
    request = urllib.request.Request(url.rstrip("/") + "/v1/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return GatewayProbe("unavailable", None, "network")
    if 200 <= code < 300:
        return GatewayProbe("healthy", code, "ok")
    if code in (401, 403):
        return GatewayProbe("degraded", code, "authentication")
    if 400 <= code < 500:
        return GatewayProbe("degraded", code, "client_response")
    return GatewayProbe("unavailable", code, "server_response")
