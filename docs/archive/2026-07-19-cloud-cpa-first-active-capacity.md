# Cloud CPA First Active Capacity

Date: 2026-07-19

## Decision And Boundary

The operator approved all remaining independent Roadmap confirmations. After signed Cloudx `0.1.18`, cloud `.policy.3`, and both cloud watcher paths were active, the first-capacity transaction used its distinct confirmation:

```text
IMPORT ONE ACTIVE CLOUD CPA CREDENTIAL 0.1.18
```

Only the already direct-Codex-verified `soul0` credential was selected. The 45 known-deactivated archive records were not restored, and the 56-file local CPA pool was not bulk-transferred. Raw credential bytes crossed only SSH/stdin and were never written to a receipt, log, Git, release, or transaction manifest.

## Shadow Import Is Not Capacity

The ordinary `codexx cloud import` dry-run and apply both accepted request `eb193349afb022ad` with one write, but correctly targeted the Cloudx shadow importer. Cloud CPA active auth remained zero, so this write was not presented as live capacity evidence.

Source commit `c9153fc87351c6eec1aa1674d3d0cb646be53580` then added an exact-confirmation active transaction using the active signed importer, empty-pool and watcher prerequisites, atomic mode-`0600` write, real `/v1/responses` canary, public policy `2`, unchanged CPA service identity, and private same-filesystem failure containment. Later commits accepted identity-free `available` observations and bounded hot-load/refresh retries. Full verification reached 427 tests; final canary source commit `38fb30e87cabae282ba87b76821409ed2ce0ab39` passed CI run `29656191461`.

## Contained Attempts

Transaction `20260718T182652Z-b6979a6d` completed real model traffic and caused `.policy.3` to emit `cloudx.cpa-pool-observation.v1 state=available`. The first transaction version incorrectly treated any sweep-directory change as failure, so it moved both credential and observation into its private rollback and restored active auth to zero. CPA PID/restart state and the 45-entry permanent archive were unchanged.

Transaction `20260718T183228Z-d17b525e` encountered one HTTP `400` during the CPA hot-load/refresh write window. It emitted no permanent receipt and watcher archive remained false. The credential and all newly emitted watcher input were privately contained; active auth, failure/sweep inputs, CPA PID, and archive baseline were restored.

The source transaction was corrected to require an identity-free `available` observation with no `trigger.json`, to move newly emitted inputs during failed containment, and to retry bounded model/request combinations across request-level 400/409/429/5xx refresh windows without weakening final acceptance.

## Accepted Transaction

Transaction `20260718T183809Z-6171f256` passed:

- signed importer dry-run and apply for exactly one write
- active credential owner/group `cliproxy:cliproxy`, mode `0600`
- real `/v1/responses` HTTP `200`
- model `codex-auto-review`
- exact expected response text
- public `X-CPA-Max-Concurrent-API-Requests: 2`
- identity-free pool observation `available`
- no unavailable sweep trigger and no permanent failure receipt
- active auth `1`, archive entries `45`
- CPA PID `1613475`, restart count `0`
- no raw credential retained by transaction state
- no service restart

The signed trigger-aware CPA-health service then exited `0` with:

```text
total=1
ready=1
available=1
pool_observation=available
probe_gate=not_triggered
probe_concurrency=0
sweep_trigger_status=absent
archived_count=0
```

Account-state and formal-health publication succeeded. With the production environment applied, `cloudx.capacity.v1` reported `healthy_capacity`, gateway HTTP `200`, total/available `1`, zero unavailable/limited/unobserved accounts, and reason `available_accounts_observed`.

## Next Acceptance

Usable cloud capacity now exists without restoring a known-deactivated account. M4B still requires natural business-concurrency observation, aggregate-unavailable rapid sweep behavior, quota/provisional exclusions, one conclusive permanent archive, exact restore, and the deferred local policy plus local watcher transaction.
