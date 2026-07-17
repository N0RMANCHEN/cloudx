# HTTP Importer Stop-Gate Readiness

## Scope

This is a read-only re-evaluation of the migration-only HTTP importer stop gate. It validates an existing root-only rollback snapshot and refreshes sanitized traffic, caller, transaction, adapter, consumer, and dependency evidence. It did not invoke an import, read credential contents, stop or disable a service, reload systemd, change a listener, mutate auth state, alter a release selector, or write production state.

## Rollback Snapshot

The existing root-only snapshot `20260716T075313Z` contains the importer runtime, systemd unit and drop-ins, failure receipts, token metadata, restore plan, and a complete SHA-256 manifest. Every manifest entry verifies.

Read-only comparisons against the live host confirm:

- runtime file hashes still match the archived final manifest
- unit and drop-in hashes still match the archived final manifest
- the two sanitized failure receipts still match the archived final manifest and no raw input exists
- token metadata still matches the archived snapshot without reading token contents
- the service retains its accepted identity, PID, zero restart count, listener, and active/enabled state

## Traffic Refresh

Three `GET /v1/accounts` requests occurred after the earlier accepted baseline:

| Request | Attribution |
|---|---|
| `13:18:21` returned `200` | short-lived operator SSH inspection after an explicit administrative-key read |
| `13:26:39` returned `401` | the first request in an operator compatibility validation sequence |
| `13:26:44` returned `200` | the follow-up request after the administrative credential read |

The two request windows align with operator SSH sessions and credential-read commands. No background unit, timer, cron entry, installed active HTTP client, or active Phi executable references port `8780`, `/v1/accounts`, or `/v1/imports`. The only installed filename match remains the retained pre-SSH rollback client.

Using `13:26:44` CST as the refreshed accepted traffic baseline, the final read-only check found zero later requests, zero established connections, zero import-lock holders, zero active HTTP callers, and zero unattributed requests.

## Machine Decision

`docs/archive/2026-07-17-http-importer-stop-gate-evidence.json` evaluates to:

- status: `preconditions-satisfied`
- preconditions satisfied: `true`
- blockers: none
- automatic action: `false`
- service-stop authorization: `false`
- required authorization: `separate-operator-confirmation`

The decision is bound to evidence digest `sha256:293a771af237fb55901267d1a37f86e994f7bd5b0a52d604dd3452a3535522ad`.

## Decision

The technical stop preconditions are ready, but `codex-import.service` remains enabled, active, and listening. Stopping or disabling it is still a distinct operator-confirmed maintenance transaction. That transaction must preserve the validated rollback snapshot, close only port `8780`, repeat signed SSH import and formal-health checks, validate Phi consumers plus gateway/model canaries, and atomically restore the importer if any acceptance check fails.

Removing the legacy runtime package, administrative keys, unit files, exporter, or rollback archive remains outside this gate.
