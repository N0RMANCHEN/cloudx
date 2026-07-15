# Phi Goal Watchdog Formal-Health Readiness

## Scope

This batch advances the Phi-owned dependency that blocks retirement of the old Cloudx HTTP importer. It prepares and validates source changes in an isolated Phi worktree, but does not commit or push Phi, create a production release, install a unit, reload systemd, start or restart a service, stop the importer, or mutate Cloudx auth state.

Cloudx remained at source `0.1.12` and commit `a569b420d701cc7f2b6bedae5283fc2c2663398c`. The isolated Phi candidate is based on clean Phi commit `a65adf2` and resides at:

`/Users/hirohi/.codex-tmp/phi-goal-watchdog-wal`

The active `/Users/hirohi/Phi` worktree is concurrently used for unrelated orchestrator development. None of those files were changed, staged, reverted, or committed by this work.

## Installed Drift

The installed `phi-goal-watchdog` component still selects immutable release `17d3e42e61fb2d88bf47c25497c05f0b3bb47438`. Its service reads `/var/lib/cloudx/health/v1.json` and executes the pre-formal-contract parser. Its timer remains enabled and active.

After the Codex SQLite databases entered WAL mode, natural watchdog runs intermittently failed with `sqlite3.OperationalError: unable to open database file`. The database files are readable by `hirohi`; the failure occurs because SQLite read-only WAL connections still open the `-shm` coordination files read-write while `ProtectHome=read-only` makes the whole home tree read-only. A later natural run succeeded after the sidecars existed, confirming an unsafe existence-dependent condition rather than a stable recovery.

Formal-health release `c06dfe905b961d0a979e8b0052d68d04f60a5224` already contains the exact `cloudx.health.v1` parser and default path. It cannot be reused for a new component activation: release verification now rejects one manifest-external root-owned `deploy/cloud/__pycache__/phi_cloudx_health.cpython-312.pyc`. Every manifest-listed file remains present with its expected SHA-256, so the extra cache is retained as drift evidence rather than deleted from the historical release.

## Isolated Candidate

The candidate changes only the Phi-owned goal-watchdog unit and adds one independent regression test:

- `deploy/cloud/systemd/phi-goal-watchdog.service`, SHA-256 `e519ce179a4ede9a681766338ac204859dbf8d09575fe5631407068c55751f18`
- `deploy/cloud/tests/test_goal_watchdog_wal_sandbox.py`, SHA-256 `041057123ce32ff2027d52604409ebd6afe7398d04a1fa4b1c39db81646b4ebe`

The unit now orders after `cloudx-health.service` instead of the legacy `cloudx-health-contract.service`. It retains `ProtectHome=read-only`, the formal `/run/cloudx/health.json` input, the private state directory, and all Cloudx credential denials. The only added writable paths are:

- `/home/hirohi/.codex/goals_1.sqlite-shm`
- `/home/hirohi/.codex/state_5.sqlite-shm`

The database files, WAL files, `.codex` directory, other home paths, Cloudx state, and credentials remain outside the writable sandbox. Missing shared-memory sidecars remain fail-closed because the optional path exceptions do not grant directory creation access.

## Verification

Repository verification completed in the isolated worktree:

- new focused regression: `1` passed
- goal-watchdog, cloud release, and sandbox modules: `53` passed
- `npm run check`: passed after a clean `npm ci --ignore-scripts`
- full cloud deployment discovery: `88` passed and `2` unrelated repair-PR tests failed identically on clean Phi main because their internal test subprocess returned no output; the unchanged baseline failure is outside this candidate's paths

A preflight-only 46-file candidate release staged and verified under synthetic release ID `ffffffffffffffffffffffffffffffffffffffff` with manifest SHA-256 `ef7e59b7f38cad76e249e47c2b7e98c81b6195254135cdc8288412579df3da88`. The synthetic ID is not a publishable source identity and the artifact was never copied to `/opt/phi`.

The rendered service and timer passed `systemd-analyze verify`. A temporary private mount namespace then reproduced the production boundary with `/home` read-only and only the two `-shm` files remounted writable. The formal-health candidate ran without `--apply` and returned:

- goals inspected: `5`
- actions emitted: `0`
- capacity state: `low_capacity`
- available accounts: `9` of `15`
- private state directory: mode `0700`
- state and status files: mode `0600`

## Component Rollback Rehearsal

A local temporary host root was seeded with exact copies of the installed units:

- installed service SHA-256: `8b3cc1a974bd00096ea31f037a263cb35a681fc44de83920c2dca53b6b55a467`
- installed timer SHA-256: `57b3ac282ad6367f7f1fe9649c4224c3bf6c3a82dfdb241e239e9a6a8e6ade53`

The component transaction selected `17d3e42 -> synthetic candidate`, changed exactly the service and timer targets, and retained `17d3e42` as previous. `rollback-component` then restored both installed hashes exactly and returned `17d3e42` to current. No real host path or systemd state participated in the rehearsal.

## Remaining Gate

Phi repository policy prohibits a commit without an explicit user request, and Phi service migration requires its own release and maintenance approval. The next accepted sequence is:

1. apply the reviewed two-file candidate to a clean Phi branch after concurrent work settles
2. commit and publish a new immutable Phi release from that exact source revision
3. verify the new release contains no manifest-external cache or other drift
4. stop only the goal-watchdog timer, snapshot its unit/state boundary, and install only the goal-watchdog component under explicit approval
5. run a non-apply preflight, an approved explicit oneshot, and repeated natural timer observations with zero unintended resume actions
6. update the Cloudx HTTP importer stop gate only after the installed watchdog reads `/run/cloudx/health.json` and no live consumer depends on importer process state

Until then, `phi-goal-watchdog`, the legacy health contract, `codex-import.service`, `/opt/codex-gateway/codexx_app`, and all rollback evidence remain installed and available.
