# HTTP Importer Stop-Gate Evaluation

## Scope

This batch evaluates a sanitized production snapshot with the committed source `0.1.15` migration-only stop-gate implementation. The evaluator ran locally against aggregate evidence; no mutable checkout code ran on the cloud host. No service, timer, listener, credential, auth record, failure receipt, rollback archive, release selector, or process was changed.

The evaluator implementation is release-packaged and covered by artifact execution tests, but it is not yet a published signed production artifact. This evidence therefore validates the source decision logic and current blockers without claiming a signed rollout or granting production authority.

## Sanitized Evidence

The versioned evidence document records only aggregate facts:

- `codex-import.service` remained active, enabled, and identity-stable
- port `8780` remained listening with zero established connections
- the final request remained `2026-07-16T00:39:33Z`, with zero unattributed, active-caller, or later requests
- import locks and raw failure inputs remained zero, while formal import status remained ready
- the active SSH adapter retained its accepted signed-artifact hash and zero HTTP references
- the goal watchdog remained on formal Cloudx health, with zero legacy readers and the exporter retained as rollback
- systemd reported zero required units
- the existing rollback set retained unit and token metadata evidence plus an explicit restore plan

The evidence contains no PID, source IP, SSH fingerprint, account identity, credential path, key contents, request body, or raw failure input.

## Machine Decision

Source `0.1.15` emitted `cloudx.http-importer-stop-gate.v1` with:

- status: `blocked`
- preconditions satisfied: `false`
- automatic action: `false`
- service-stop authorization: `false`
- blocker: `rollback_runtime_missing`
- blocker: `rollback_failure_receipts_missing`

Every other declared traffic, caller, transaction, adapter, consumer, dependency, and rollback precondition passed. The result is bound to the exact sanitized evidence through the recorded SHA-256 digest.

## Decision

The next safe preparation step is a separately controlled root-only snapshot of the active importer runtime and fresh sanitized failure receipts. Merely creating source code or evaluating evidence does not authorize that production write, and completing the snapshots would still not authorize stopping the service.

`codex-import.service` remains enabled and active. Its eventual stop must remain a separate operator-confirmed transaction with the full port, SSH import, formal health, Phi consumer, gateway, model, and atomic restore acceptance sequence.
