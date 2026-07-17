from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, Optional, TextIO, Tuple


PHI_CONSUMER_CREDENTIAL_SCHEMA = "cloudx.phi-cloud-consumer-credential.v1"
_PHI_CONSUMER_CREDENTIAL_SCHEMA_ID = "cloudx.phi-cloud-consumer-credential.v1.schema.json"
CLOUDX_RELEASE_MANIFEST_SCHEMA = "cloudx.release-manifest.v1"
_CLOUDX_RELEASE_MANIFEST_SCHEMA_ID = "cloudx.release-manifest.v1.schema.json"
_FORBIDDEN_KEYS = {
    "approval",
    "approvalid",
    "approvaldevice",
    "approvals",
    "artifact",
    "artifactid",
    "artifactmetadata",
    "artifacts",
    "content",
    "contextrequest",
    "contextrequests",
    "cwd",
    "device",
    "deviceid",
    "devices",
    "executionlease",
    "executionleaseid",
    "files",
    "lease",
    "leaseid",
    "leases",
    "localaction",
    "localactions",
    "localpath",
    "metadata",
    "origindevice",
    "origindeviceid",
    "path",
    "paths",
    "payload",
    "session",
    "sessionid",
    "sessions",
    "sourcepath",
    "targetdevice",
    "targetdeviceid",
    "targetpath",
    "task",
    "taskid",
    "tasks",
    "transfer",
    "transfercontent",
    "transferid",
    "transfers",
    "workspace",
    "workspacepath",
    "writerlease",
    "writerleaseid",
    "workingdirectory",
}
_FORBIDDEN_ASSIGNMENT = re.compile(
    r"(?i)\b(?:"
    r"approval(?:Id|Device)?|artifact(?:Id|Metadata)?|contextRequest|device(?:Id)?|"
    r"executionLease(?:Id)?|lease(?:Id)?|localAction|localPath|originDevice(?:Id)?|"
    r"session(?:Id)?|sourcePath|targetDevice(?:Id)?|targetPath|task(?:Id)?|"
    r"transfer(?:Id|Content)?|workspacePath|writerLease(?:Id)?"
    r")\b\s*[:=]"
)
_LOCAL_USER_PATH = re.compile(r"(?i)(?:^|[\s\"'=])(?:file://)?(?:/Users/|/home/)[^\s\"']*")
_ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'=])/(?:[^/\s\"']+/)+[^\s\"']*")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PublicMetadataRejected(RuntimeError):
    pass


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _credential_policy(document: Dict[str, Any]) -> bool:
    if document.get("schema") == PHI_CONSUMER_CREDENTIAL_SCHEMA:
        return True
    return str(document.get("$id") or "").endswith(_PHI_CONSUMER_CREDENTIAL_SCHEMA_ID)


def _release_manifest(document: Dict[str, Any]) -> bool:
    if document.get("schema") == CLOUDX_RELEASE_MANIFEST_SCHEMA:
        return True
    return str(document.get("$id") or "").endswith(_CLOUDX_RELEASE_MANIFEST_SCHEMA_ID)


def _allowed_negative_representation(
    root: Dict[str, Any],
    path: Tuple[str, ...],
    key: str,
    value: Any,
) -> bool:
    if not _credential_policy(root) or key not in {"device", "task", "session"}:
        return False
    if path == ("representation",):
        return value is False
    if path == ("properties", "representation", "properties"):
        return isinstance(value, dict) and value == {"const": False}
    return False


def _allowed_cloudx_release_artifacts(root: Dict[str, Any], path: Tuple[str, ...], key: str) -> bool:
    if key != "artifacts" or not _release_manifest(root):
        return False
    return path in ((), ("properties",))


def _walk(root: Dict[str, Any], value: Any, path: Tuple[str, ...]) -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = _normalized(raw_key)
            if (
                key in _FORBIDDEN_KEYS
                and not _allowed_negative_representation(root, path, key, item)
                and not _allowed_cloudx_release_artifacts(root, path, key)
            ):
                raise PublicMetadataRejected("public output contains prohibited Phi metadata")
            _walk(root, item, path + (key,))
        return
    if isinstance(value, list):
        for item in value:
            _walk(root, item, path)
        return
    if isinstance(value, str) and (_FORBIDDEN_ASSIGNMENT.search(value) or _LOCAL_USER_PATH.search(value)):
        raise PublicMetadataRejected("public output contains prohibited Phi metadata")


def validate_public_document(document: Dict[str, Any], surface: str = "public document") -> Dict[str, Any]:
    del surface
    if not isinstance(document, dict):
        raise PublicMetadataRejected("public output must be an object")
    _walk(document, document, ())
    return document


def validate_public_text(value: str, surface: str = "public text") -> str:
    del surface
    if _FORBIDDEN_ASSIGNMENT.search(value) or _LOCAL_USER_PATH.search(value):
        raise PublicMetadataRejected("public output contains prohibited Phi metadata")
    return value


def sanitize_public_error(error: object) -> str:
    message = _CONTROL.sub("", str(error or "")).strip()
    message = " ".join(message.split())
    if _FORBIDDEN_ASSIGNMENT.search(message) or _LOCAL_USER_PATH.search(message) or _ABSOLUTE_PATH.search(message):
        return "request failed without exposing prohibited Phi metadata"
    if len(message) > 300:
        message = message[:297].rstrip() + "..."
    return message or "request failed without a reported reason"


def emit_json(document: Dict[str, Any], *, ensure_ascii: bool = True, sort_keys: bool = True) -> None:
    validate_public_document(document)
    print(json.dumps(document, ensure_ascii=ensure_ascii, sort_keys=sort_keys, separators=(",", ":")))


def emit_text(value: str) -> None:
    sys.stdout.write(validate_public_text(value))


def emit_error(label: str, error: object, stream: Optional[TextIO] = None) -> None:
    target = stream if stream is not None else sys.stderr
    print("%s: %s" % (label, sanitize_public_error(error)), file=target)
