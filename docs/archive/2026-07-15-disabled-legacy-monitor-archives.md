# Disabled Legacy Monitor Archives

## Scope

This batch archives two already disabled and inactive legacy timer paths after signed Cloudx `0.1.10` native CPA health completed accepted observation. It does not remove installed rollback files, stop or restart a service, mutate credentials, change gateway/network policy, or retire the active HTTP importer.

## Disabled State

`codex-quota-monitor.timer` was disabled and inactive before this action. Its final recorded trigger remained `2026-07-15 18:01:31 CST`; its service was inactive with a successful last result.

`codex-import-phi-repair.timer` was disabled and inactive, had no recorded trigger, and its service had never started. `/run/lock/codex-import-phi-repair.lock` existed but no import, quota, or repair lock holder was active.

## Root-Only Archive

The archive root is:

`/var/lib/cloudx/legacy-service-archives/20260715T131538Z`

The root is mode `0700`, owned by root. Every contained file is mode `0600`, owned by root. It contains:

- quota-monitor service and timer units
- import-repair service and timer units
- the import-repair wrapper
- the inactive repair lock file
- quota-monitor source and state tar archives
- a sanitized import-failure archive
- source hashes, systemd cat/show/status evidence, journal evidence, and retirement state

No gateway key, mail password, raw credential directory, or release private key was copied into this archive. The installed unit files, scripts, and state remain in place as rollback inputs.

## Resolved Raw Input Remediation

Archive review found two legacy `resolved/*.input` files: one was 2,442 bytes with sensitive fields and one was a 41-byte non-single-JSON input. The disabled repair runtime reads only `private/*.input`; resolved inputs are not executable repair work.

The original bytes and the pre-remediation failure archive were moved into:

`/var/lib/cloudx/secret-recovery/import-resolved-20260715T131953Z`

This recovery root is mode `0700`, owned by root; all files are mode `0600`, owned by root. Its manifest contains only paths, sizes, modes, ownership, and SHA-256 values, not raw content.

After migration:

- live failure-tree `.input` files: `0`
- ordinary legacy-archive `.input` members: `0`
- companion resolved diagnostic receipts remain in place
- import-repair timer/service remain disabled and inactive
- no import or quota lock is held

The active importer retained PID `133756`, restart count `0`; cloud CLIProxyAPI retained PID `977036`, restart count `0`; local CLIProxyAPI retained PID `38189`. A fresh `cloud import` SSH dry-run accepted one sanitized synthetic record with no errors and no write.

## Remaining HTTP Importer Gate

The old HTTP importer remains enabled and active on port `8780`. It handled ten successful requests in the preceding 24-hour window, and `/opt/codex-gateway/cloud_import_api.py` still imports `codexx_app.cloud_import_server`. `cloudx-health-contract.service` also retains ordering against `codex-import.service`, and a compatibility `codex-gateway-import` script still targets the HTTP endpoint.

The HTTP importer and `/opt/codex-gateway/codexx_app` therefore remain production and rollback dependencies. They are not retired by this archive batch; importer consumer migration and a separate explicit stop/rollback transaction remain required.
