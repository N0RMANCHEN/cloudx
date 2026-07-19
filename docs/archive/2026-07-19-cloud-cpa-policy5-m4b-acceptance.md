# Cloud CPA policy.5 M4B acceptance

Date: 2026-07-19

## Boundary

The rollback-bounded production transaction used the exact confirmation:

```text
ACCEPT CLOUD CPA FAILURE POLICY 0.1.21
```

The local phase used signed Cloudx `0.1.21` to read-only classify top-level local CPA snapshots through the declared mihomo HTTPS path and selected three current distinct weekly-limited samples. It did not write, reload, restart, or reconfigure the local CPA and did not read the separately supplied optional sample file.

The cloud transaction prepared a root-only independent recovery before temporarily changing the active pool. It did not restart CPA, importer, Cloudx, Phi, or any local process.

## Accepted Transaction

Transaction `20260719T102932Z-aee5d40f` returned `cloudx.cloud-cpa-failure-policy-acceptance.v1` with `status=accepted`.

Isolated evidence accepted:

- three real weekly-limited credentials: limited `3`, archived `0`
- provisional refreshable HTTP 401: archived `0`, probe concurrency `1`
- conclusive non-refreshable HTTP 401: exactly one digest-matched archive, followed by exact restore
- raw credential persisted in transaction output/state: `false`

Natural aggregate evidence accepted:

- active exact cloud policy `7.2.71-cloudx-policy.5`
- natural business responses reached HTTP `429` cooldown after three attempts
- stable identity-free aggregate trigger observed: `true`
- trigger consumed by the active watcher: `consumed`
- incident sweep probe concurrency: `3`, independent of business maximum `2`
- limited accounts calibrated: `3`
- quota credentials archived: `0`
- public business policy: `2`
- elapsed aggregate phase: `9.045` seconds

Recovery and idle evidence accepted:

- the one useful active credential was restored
- archive manifest returned to exactly `45`
- real `codex-auto-review` recovery traffic returned HTTP `200`, policy `2`, in one attempt
- CPA PID `1719083` and restart count `0` were unchanged
- final idle maintenance reported `probe_gate=not_triggered`, probe concurrency `0`, absent trigger, and unchanged CPA service
- failure inputs are empty and the aggregate trigger is absent
- policy5 remains selected and healthy

Independent post-transaction verification found local CPA PID `61859`, the six long-lived Codex PIDs, and 56 established local CPA connections still present; a real official-Codex-through-local-CPA canary returned the exact expected response.

## Decision

The cloud M4B failure semantics and agile incident sweep are accepted: business concurrency remains declared as `2`; incident diagnosis triggers only on aggregate pool unavailability, runs above that business limit, retains weekly quota and provisional failures, archives one conclusive permanent credential immediately, and restores transaction state without a service restart.

Local policy5 remains staged/inactive. Its activation and local watcher remain blocked by the mandatory five-sample zero-established-connection gate; no process may be killed to satisfy it.
