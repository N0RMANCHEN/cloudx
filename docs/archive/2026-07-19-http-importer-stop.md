# Legacy HTTP importer stop

Date: 2026-07-19

## Boundary

The continuing M5 authorization exercised the exact transaction confirmation:

```text
STOP AND DISABLE codex-import.service WITH AUTOMATIC RESTORE
```

This authorized stopping and disabling only `codex-import.service`. It did not authorize runtime, unit, token, failure-receipt, rollback-snapshot, legacy-exporter, gateway, Phi, Cloudx release, credential, archive, CPA, network, or local-process removal/change.

## Fresh Stop Gate

A new read-only audit verified:

- importer PID `133756`, restart count `0`, active/enabled, unique listener `100.90.97.113:8780`, zero established connections
- no HTTP request after the attributed `2026-07-17T05:26:44Z` final request
- zero active HTTP callers, zero hard unit dependencies, zero import-lock holders, zero raw failure inputs
- active SSH adapter SHA-256 `5830d8228b3bd7b1e46ec3276464dfc441f250da3da990a65c7b5eb3123dd539`, zero HTTP references, and byte identity with signed Cloudx output
- formal health `importStatus=ready`, healthy gateway, installed formal Phi goal-watchdog, active Phi health consumer timer, and retained legacy exporter unit
- rollback snapshot `/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z` passed its complete SHA-256 manifest
- live importer runtime, systemd files, failure receipts, token metadata, and SSH adapter remained byte/metadata-identical to the retained rollback snapshot

Sanitized evidence captured at `2026-07-19T10:38:40Z` evaluated identically in local source and active signed Cloudx `0.1.21`:

```text
status=preconditions-satisfied
blockers=[]
evidenceDigest=sha256:8b29a28bc6f3f1109d26e95344de041f951e1a17e134319c5d8748c6bcdc3104
```

## Accepted Stop

The rollback-protected transaction returned `cloudx.http-importer-stop.v1` with `status=stopped`:

- `codex-import.service`: loaded, inactive/dead, disabled, PID `0`, restart count `0`
- port `8780`: listener count `0`, established count `0`
- generated-fixture SSH import dry-run: accepted
- formal Cloudx health: accepted with `importStatus=ready`
- Phi formal-health consumer: accepted
- authenticated gateway/model canary: accepted
- gateway process and Cloudx selectors: unchanged
- policy5 remains active as PID `1719083`, restart count `0`
- Cloudx remains `0.1.21/0.1.20`
- local CPA remains PID `61859`; a real official-Codex-through-local-CPA canary passed with 56 established local connections still present

Retained recovery boundary:

- `/opt/codex-gateway/codexx_app` and `/opt/codex-gateway/cloud_import_api.py`
- importer unit and drop-ins
- token metadata and sanitized failure receipts
- rollback snapshot and restore plan
- legacy exporter

No service other than the legacy importer was stopped or disabled, and no service was restarted.

## Next Gate

The old HTTP importer retirement item is accepted as a reversible stop, not deletion. Confirm remaining legacy sessions/tunnels/package dependencies before any codex-plus or runtime quarantine. `legacy_bridge` removal remains a separate N/N-1 release decision.
