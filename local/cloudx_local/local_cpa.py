from __future__ import annotations

import json
import pathlib
import sys
from typing import Sequence, Tuple

from . import import_ui, local_cpa_import
from .config import LocalConfig


def _options(extra: Sequence[str]) -> Tuple[bool, bool, bool, str]:
    force = True
    dry_run = False
    json_output = False
    name_prefix = "codexx-import"
    index = 0
    while index < len(extra):
        token = extra[index]
        if token == "--force":
            force = True
            index += 1
            continue
        if token == "--dry-run":
            dry_run = True
            index += 1
            continue
        if token == "--json":
            json_output = True
            index += 1
            continue
        if token == "--name-prefix":
            if index + 1 >= len(extra):
                raise local_cpa_import.LocalImportError("invalid_arguments", "--name-prefix requires a value")
            name_prefix = extra[index + 1].strip() or name_prefix
            index += 2
            continue
        if token.startswith("--name-prefix="):
            name_prefix = token.split("=", 1)[1].strip() or name_prefix
            index += 1
            continue
        raise local_cpa_import.LocalImportError("invalid_arguments", "unknown local import option: %s" % token)
    return force, dry_run, json_output, name_prefix


def _raw_counts(document: dict) -> None:
    counts = document["counts"]
    for label, name in (
        ("discovered", "discovered"),
        ("skipped", "skipped"),
        ("parsed", "parsed"),
        ("duplicates", "duplicates"),
        ("unchanged", "unchanged"),
        ("imported", "written"),
        ("verified", "verified"),
    ):
        print("%s: %d" % (label, counts[name]))


def import_local(config: LocalConfig, source: str, extra: Sequence[str]) -> int:
    try:
        force, dry_run, json_output, name_prefix = _options(extra)
        if source == "-":
            if getattr(sys.stdin, "isatty", lambda: False)():
                raise local_cpa_import.LocalImportError(
                    "source_missing", "stdin source requires redirected input"
                )
            result = local_cpa_import.import_text(
                config,
                sys.stdin.read(local_cpa_import.MAX_SOURCE_BYTES + 1),
                force=force,
                dry_run=dry_run,
                name_prefix=name_prefix,
            )
        else:
            result = local_cpa_import.import_path(
                config,
                pathlib.Path(source),
                force=force,
                dry_run=dry_run,
                name_prefix=name_prefix,
            )
        document = result.document()
    except local_cpa_import.LocalImportError as exc:
        reason = import_ui.sanitize_reason(str(exc))
        dry_run = "--dry-run" in extra
        json_output = "--json" in extra
        document = local_cpa_import.failure_document(exc.code, reason, dry_run)
        if json_output:
            print(json.dumps(document, sort_keys=True, separators=(",", ":")))
        elif import_ui.human_output():
            import_ui.render(import_ui.failure_report(import_ui.LOCAL_CPA_DESTINATION, reason, exc.code), stream=sys.stderr)
        else:
            print("codexx import: %s: %s" % (exc.code, reason), file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    elif import_ui.human_output():
        import_ui.render(import_ui.local_report(document))
    else:
        _raw_counts(document)
    return 0
