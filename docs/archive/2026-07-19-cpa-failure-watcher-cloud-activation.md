# Cloud CPA Failure And Sweep Watcher Activation

Date: 2026-07-19

## Decision And Boundary

The operator approved all remaining independent confirmations while requiring local communication continuity. The cloud watcher transaction used its distinct confirmation:

```text
ACTIVATE CLOUD CPA FAILURE WATCHER 0.1.18
```

This authorized installation of the active signed Cloudx `0.1.18` trigger-aware CPA-health service/timer and failure/sweep path-service pairs, plus path enablement. It did not authorize CPA or importer restart, credential import/archive/restore, release selector movement, local watcher or CPA policy activation, Phi mutation, or legacy retirement.

Before activation, source commit `cd8ee68a55f5117095c2081bf6750d0fbf2b4bd8` advanced the operator gate from cloud `0.1.17` to the now-active signed `0.1.18`. Focused tests, all 419 repository tests, deterministic builds, and CI run `29655283138` passed before the transaction. Unit bytes continued to be extracted only from `/opt/cloudx/current/cloudx-cloud.pyz`.

## Baseline

- Cloudx selectors `0.1.18/0.1.17`
- active CPA policy `7.2.71-cloudx-policy.3`
- CPA PID `1613475`, importer PID `133756`, both active/running with restart count `0`
- zero active auth files, 45 reversible archive entries, zero failure receipts, zero sweep triggers
- failure/sweep path units absent/inactive
- existing CPA-health timer enabled/active/waiting
- CPA unit and policy drop-in captured unchanged
- local Cloudx `0.1.18/0.1.17`, CPA PID `61859`, health `ok`

## Activation

The rollback-protected source transaction:

1. required active signed Cloudx `0.1.18` and the exact active `.policy.3` receipt/trigger producer;
2. extracted and validated six unit files from the signed artifact;
3. snapshotted the old health service/timer and absence of the four new watcher units;
4. retained root-only rollback backup `1784398277383594551`;
5. atomically installed all six files as root/root mode `0644`;
6. ran `daemon-reload`;
7. enabled and started only `cloudx-cpa-failure.path` and `cloudx-cpa-sweep.path`;
8. required the previous health-timer enabled/active state to remain identical.

Any internal or post-activation failure would have disabled the new paths, restored every file and prior unit state, and repeated CPA/importer/health acceptance. No rollback was required.

## Acceptance

- active signed Cloudx version `0.1.18`
- active CPA producer `7.2.71-cloudx-policy.3`
- every installed unit byte matches the active signed artifact
- `cloudx-cpa-failure.path`: enabled/active/waiting
- `cloudx-cpa-sweep.path`: enabled/active/waiting
- `cloudx-cpa-health.timer`: enabled/active/waiting, state preserved
- CPA PID `1613475`, restart count `0`, health `ok`
- importer PID `133756`, restart count `0`
- Cloudx selectors, CPA unit/drop-in, credentials, 45-entry archive, empty failure/sweep inputs, and local communication remained unchanged
- no CPA, importer, Cloudx, Codex, or Phi service restarted

A real post-activation idle health service invocation exited `0` with:

```text
probe_gate=not_triggered
probe_concurrency=0
sweep_trigger_status=absent
sweep_triggered=false
archived_count=0
```

This accepts the no-unsolicited-periodic-probe behavior. Live rapid-sweep and archive classification still require an independently verified usable credential and a real aggregate-unavailable event.

## Next Gate

The local watcher cannot activate until local `.policy.3` is live. Local policy activation remains deferred to the prebuilt recovery worker and requires five consecutive zero-established-connection samples before launcher mutation. The current local CPA remains healthy and untouched.
