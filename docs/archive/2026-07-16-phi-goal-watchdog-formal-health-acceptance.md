# Phi Goal Watchdog Formal-Health Acceptance

## Scope

This read-only reconciliation closes the Cloudx M4 goal-watchdog prerequisite against the current Phi repository, installed Phi component release, systemd state, natural-run journal, rollback metadata, and HTTP importer traffic. It did not commit or deploy Phi, change a Cloudx artifact, enable or stop a timer, restart a service, mutate credentials or auth state, move a release selector, or terminate a process.

## Phi Release And Publication

Phi commit `b9f668444ebc8f0258b152d3225df14e113860bf` (`fix: harden goal watchdog WAL sandbox`) is present on Phi `origin/main`. The repository was clean and synchronized when inspected.

Phi's component cutover closeout records an approved maintenance window for goal-watchdog. The later `b9f66844` hardening release used the same root-owned versioned component transaction and retained the already accepted rollback boundary.

The installed root-owned release is:

- release and source revision: `b9f668444ebc8f0258b152d3225df14e113860bf`
- manifest SHA-256: `1bbe2d8c2a4136632a48d8003bb8deae1b055b8c97667160a9866ffac089693f`
- installed service SHA-256: `87d4aa83b52293b8c0e468879de76edc57ed5e802a7d038a3c6d29e4f17e5eb6`
- installed timer SHA-256: `57b3ac282ad6367f7f1fe9649c4224c3bf6c3a82dfdb241e239e9a6a8e6ade53`
- installed watchdog source SHA-256: `b976e31cc560e25ee3261c54fca519777147f2953f4ca2d30a2ac961cf87fefa`

All three installed hashes match the release manifest. Phi's component state records `b9f66844` as current and `17d3e42e61fb2d88bf47c25497c05f0b3bb47438` as previous. The corrected release was installed, rolled back to `17d3e42`, and installed again through root-owned component snapshots before observation. The original fixed rollback receipt and both earlier maintenance snapshots remain available outside the release directory.

## Installed Boundary

The installed unit:

- orders after `cloudx-health.service`, not `cloudx-health-contract.service`
- reads `PHI_CLOUDX_HEALTH_PATH=/run/cloudx/health.json`
- preserves `ProtectHome=read-only` and `ProtectSystem=strict`
- permits writes only to Phi private state and the two SQLite `-shm` coordination files needed by WAL-mode read-only connections
- keeps Cloudx auth, archive, gateway configuration, and importer-key directories inaccessible
- uses only `AF_UNIX`, so it cannot call the HTTP importer or gateway network endpoints

No installed goal-watchdog unit or release file references `/var/lib/cloudx/health/v1.json`.

## Natural-Run Acceptance

The corrected timer started at `2026-07-16 00:45:12 CST`. Between that activation and the final successful invocation at `10:32:54 CST`, the systemd manager recorded:

- 265 completed `Finished` cycles
- 0 failed cycles
- 265 status documents with `actions: []`
- 0 documents with a non-empty action list

The final two scheduled attempts at `10:35` and `10:37` were safely skipped when a required SQLite `-shm` condition was absent. The Phi-owned timer was then stopped at `10:38:42` and is now disabled; this audit did not alter that state. The completed observation proves repeated natural formal-health reads and fail-closed behavior without making goal recovery a Cloudx availability dependency.

## HTTP Importer Recheck

The formal-health migration removes the goal watchdog as a consumer of the legacy health signal. It does not prove that the old HTTP importer has no callers.

At the read-only recheck:

- `codex-import.service` remained enabled and active as PID `133756`, restart count `0`
- the service still listened on `100.90.97.113:8780`
- no established port-`8780` connection was present at the snapshot
- the installed `/usr/local/bin/codex-gateway-import` remained the signed SSH adapter with SHA-256 `5830d8228b3bd7b1e46ec3276464dfc441f250da3da990a65c7b5eb3123dd539`
- the importer journal nevertheless contained new cloud-host `GET /v1/accounts` and `POST /v1/imports` requests between `08:36:37` and `08:39:33 CST`

Those requests postdate the earlier no-traffic audit and are not attributed by the available access log. The legacy health exporter also remains enabled as rollback evidence and still orders after `codex-import.service`.

## Decision

The Cloudx M4 goal-watchdog checklist item is complete: the Phi-owned change is committed, pushed, published in a versioned release, installed with rollback evidence, and accepted through repeated natural runs.

The M5 HTTP importer retirement item remains open. Before any stop transaction, the new HTTP caller must be attributed or eliminated, a fresh quiet-traffic gate must pass, rollback evidence must be reverified, and the operator must separately approve stopping and disabling only `codex-import.service`. No importer, legacy exporter, runtime package, key, unit, or rollback file is removed by this batch.
