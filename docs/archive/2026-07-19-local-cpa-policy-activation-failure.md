# Local CPA Policy Activation Failure And Recovery Redesign

Date: 2026-07-19

## Decision Boundary

The operator had supplied the exact local activation confirmation:

```text
ACTIVATE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.3 1cff3152e346
```

The source scheduler created private job `20260718T151333Z-7d40e597`, returned without restarting CPA, and deferred execution by 180 seconds. The authorization covered one candidate-selection attempt and automatic baseline restoration. It did not authorize watcher activation, credential/archive mutation, Codex process termination, Cloudx release changes, cloud changes, or legacy removal.

## Failed Production Attempt

Pre-schedule evidence showed:

- signed local Cloudx `0.1.17/0.1.13`
- baseline CPA PID `38189` on `127.0.0.1:8317`
- exact staged candidate SHA-256 `1cff3152e34666d2753add54ce7f5f96dbd643e607c1f136a9052cd28eba9ecd`
- exact original launcher SHA-256 `80535ade89c6f0de399a6dbab9f69280c933b8fe3c5cbba829f96c86d6325970`
- 48 established port-`8317` socket rows and multiple live CPA-backed requests
- all six captured Codex/Codex-App processes alive

The job began its activation phase at approximately `23:16:33 CST`. The real baseline Codex canary completed successfully. CPA logs then show several pre-existing inference requests still active, followed at `23:16:46 CST` by:

```text
error stopping API server: failed to shutdown HTTP server: context deadline exceeded
service shutdown returned error: failed to shutdown HTTP server: context deadline exceeded
```

No candidate startup identity was observed in the watched CPA log after that shutdown. The old rollback code restored the original launcher bytes but raced launchd's unload transition: its process/PID check could observe the dying generation, while bootstrap errors were ignored and the worker retained no sanitized failure stage. The mode-`0600` job receipt therefore reported only:

- status: `failed`
- installer exit: `1`
- communication canary: `not-accepted`
- automatic rollback configured: `true`

`worker.log` was empty. The service remained offline until the operator manually reopened the baseline at `23:54:06 CST` as PID `61859`.

## Current Restored State

Read-only verification after the operator recovery established:

- launchd selects `/Users/hirohi/.local/bin/cli-proxy-api`
- PID `61859` listens on `127.0.0.1:8317`
- `/healthz` returns `{"status":"ok"}`
- launcher SHA-256 is the exact original `80535ade89c6f0de399a6dbab9f69280c933b8fe3c5cbba829f96c86d6325970`
- baseline SHA-256 remains `cf9641b3e50ae486aec1698dec88f735589680f9ae98558c29cde184daac3a96`
- `.policy.3` remains staged and inactive
- the failed attempt's private failure/sweep directories exist at mode `0700` and are empty
- current top-level auth inventory is 56 JSON files totaling 139573 bytes; this later inventory differs from the 40-file staging snapshot and is not attributed to the failed activation without stronger evidence
- two of the six historically captured Codex PIDs remain alive; process turnover after the incident is not classified as activation-caused without direct evidence

No additional service action, launcher edit, credential move, directory cleanup, watcher action, or release activation was performed during diagnosis or source correction.

## Root Causes

1. A fixed 180-second delay was treated as sufficient, but it did not prove the shared CPA was quiescent.
2. Activation called `launchctl bootout` while many established connections and in-flight requests remained.
3. The external CPA exceeded its graceful HTTP shutdown deadline.
4. Rollback did not wait for launchd to prove the old generation fully absent before bootstrap.
5. Rollback ignored bootstrap return status and could accept a stale dying PID before the listener disappeared.
6. Automatic and operator recovery were different paths; there was no prebuilt independent recovery command.
7. The worker discarded installer stderr instead of mapping it to a secret-free failure stage.

## Recovery Redesign

Repository development `0.1.18` now:

- requires signed local Cloudx `0.1.18` before any retry
- prepares a private original launcher snapshot, exact baseline/tool/contract digests, recovery tool, `RECOVERY.txt`, worker log, and receipts before starting the deferred worker
- refuses launcher mutation until five consecutive connection audits report zero established CPA socket rows
- never terminates a Codex process to obtain quiescence
- makes installer rollback and operator recovery invoke the exact same job-local tool and confirmation
- returns `already-recovered` without rewriting or restarting when the baseline is already healthy and a real Codex request succeeds
- on an offline or candidate-selected service, atomically restores the launcher, waits for three consecutive unloaded observations, retries bootstrap, and verifies health plus real official-Codex communication
- records enumerated worker/recovery stages, recovery status, health, communication, and service availability without raw stderr, account identity, token, prompt, or model response
- retains the private job and all recovery evidence on failure

Focused tests cover connection fail-closed behavior, repeated-zero sampling, healthy-baseline no-restart idempotence, offline bootstrap, candidate unload ordering, snapshot tamper rejection, scheduler recovery preparation, failure-stage receipts, and automatic recovery reuse. A real isolated macOS rehearsal executes the exact manual recovery command against a fake offline launchd service, a real temporary health listener, and a fake official-Codex canary, proving offline-to-healthy recovery without touching the production CPA.

The standalone operator procedure is [Local CPA Activation And Recovery Manual](../local-cpa-recovery.md).

## Next Gate

The failed confirmation is consumed. Another local CPA restart is not authorized. Before a new exact activation decision, this correction must pass full verification, be committed and pushed, be published in a separately confirmed signed Cloudx `0.1.18` release, and be installed locally under its own exact confirmation. Only then may a new scheduler job prepare and expose its independent recovery command before another restart confirmation.
