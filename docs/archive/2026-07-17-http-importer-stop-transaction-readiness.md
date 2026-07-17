# HTTP Importer Stop Transaction Readiness

## Scope

This batch prepares the separately confirmed transaction that can stop and disable the migration-only HTTP importer after the existing stop gate passes. It changes repository source, contracts, tests, Roadmap, and documentation only. It does not publish or stage `0.1.15`, stop/disable/restart a service, close a listener, change a selector, write auth state, remove a runtime/unit/key/receipt/snapshot, restart the gateway or Phi, or retire the legacy exporter.

## Current Read-Only Runtime Evidence

The real importer is `codex-import.service`; `codex-gateway-import.service` is not the production unit. After the source canaries:

- `codex-import.service` remained loaded/enabled/active/running at PID `133756`, restart count zero
- port `8780` remained listening
- `cliproxy.service` remained enabled/active/running at PID `977036`, restart count zero
- Cloudx selectors remained `0.1.13/0.1.12`

No stop, disable, restart, or listener change occurred.

The existing root-only rollback snapshot remains `/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z`. Its `SHA256SUMS` covers the runtime archive, systemd archive, sanitized failure-receipt archive, token metadata, restore plan, snapshot record, and supporting evidence.

## Read-Only Plan

Running:

```text
python3 scripts/stop_http_importer.py --release-version 0.1.15
```

returns `cloudx.http-importer-stop-plan.v1` with:

```text
confirmation=STOP AND DISABLE codex-import.service WITH AUTOMATIC RESTORE
evidenceRequired=true
maximumEvidenceAgeSeconds=300
automaticAction=false
```

All eleven authorization fields are false. The plan reads no evidence and opens no SSH connection.

## Confirmed Apply Contract

Only the exact confirmation may permit the transaction to:

1. read one bounded non-symlink evidence file and require its exact `sha256:` digest
2. require blocker-free `preconditions-satisfied` evidence captured no more than five minutes earlier
3. send those same bytes to `/opt/cloudx/releases/<version>/cloudx-cloud.pyz http-importer-stop-gate` and require a byte-equivalent signed decision
4. verify every entry in the declared root-only rollback `SHA256SUMS`, including runtime, systemd, failures, token metadata, restore plan, and snapshot record
5. require the importer loaded/enabled/active/running, exactly one port-`8780` listener, and zero established connections
6. record the gateway PID/restart count and exact current/previous selector targets
7. run only `systemctl disable --now codex-import.service`
8. require the importer inactive/disabled, PID zero, port `8780` closed, and zero established connections
9. repeat a real SSH `cloudx-remote import --dry-run` using generated fixture credentials without writing an account
10. require live formal health, the existing Phi formal-health consumer state, and an authenticated gateway model-list handshake
11. require gateway and selector continuity to remain identical

Success retains importer runtime, unit/drop-ins, token metadata, failure receipts, rollback snapshot, and legacy exporter. It does not remove external infrastructure or activate a Cloudx release.

## Failure Recovery

The code marks the stop as attempted before invoking systemd. Therefore a command that partially disables or stops the unit but returns failure still enters recovery. Any listener, SSH import, formal-health, Phi, gateway/model, or continuity failure runs `systemctl enable --now codex-import.service` and waits for active/running/enabled state plus the port-`8780` listener. Restore failure or gateway/selector drift is reported as incomplete recovery rather than a successful stop.

## Read-Only Canary Result

While the importer remained active, the exact post-stop canary commands were exercised read-only:

- actual SSH `cloudx-remote import --dry-run`: accepted
- live `cloudx.health.v1` with import ready: accepted
- installed Phi formal-health timer/service state: accepted
- authenticated gateway model handshake: healthy

The follow-up process check confirmed both importer and gateway PIDs/restart counters unchanged.

## Remaining Authorization

The archived `2026-07-17` evidence is intentionally older than the five-minute apply limit. A real stop therefore requires a freshly captured sanitized evidence file, its exact digest, signed `0.1.15` staging, the existing snapshot, and a separately approved maintenance window. The Roadmap retirement checkbox remains open; this batch authorizes and performs no production stop.

## Verification

Focused tests cover offline planning, exact confirmation before file/network access, host/snapshot restrictions, fresh evidence/digest binding, signed decision parity, manifest completeness, active/listener baseline, success canaries, partial-disable restore, post-stop failure restore, restore failure reporting, SSH dry-run semantics, secret-free contracts, and public metadata. The final `./verify.sh` run passed all 303 tests and built both `cloudx-local-0.1.15.pyz` and `cloudx-cloud-0.1.15.pyz`.
