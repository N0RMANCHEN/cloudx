# Native CPA Runtime Readiness

## Scope

This repository batch removes the Cloudx source dependency on `/opt/codex-gateway/codexx_app` for CPA credential discovery, quota probing, static failure classification, quarantine, and restore. It does not publish or activate a release, install a unit, write production health state, move a production credential, or restart a service.

Production remains on signed Cloudx `0.1.8`, whose installed CPA-health unit retains the compatibility runtime and the existing rollback snapshot. Repository development remains `0.1.9`.

## Native boundary

- `cloudx_cloud.cpa_auth` provides bounded no-follow JSON reads, direct/nested/sub2api parsing, static classification, atomic mode-0600 refresh state, locked same-filesystem quarantine, an atomic private manifest, rollback on manifest failure, and exact-selector restore.
- `cloudx_cloud.cpa_quota` provides bounded standard-library HTTP requests, the existing ChatGPT/Codex usage endpoint order, ready/warning/limited/login classification, reset normalization, and no token refresh or credential write.
- `cloudx-cpa-health.service` no longer declares a condition, environment variable, or read-only path for `/opt/codex-gateway` in the candidate template.
- The sanitized production-shape fixture is `tests/fixtures/cpa_auth/production-direct-sanitized.json`; every credential and identity value in it is synthetic.

## Verification

`./verify.sh` passed architecture checks, 113 tests, and deterministic local/cloud `0.1.9` builds. The deterministic candidate cloud zipapp SHA-256 was:

`7788fe1ba1d018eabc983694c6b9135ba5648955c270a4a4275d3b2ffada47a8`

The cloud candidate then ran once from an automatically removed `/tmp` artifact with `cpa-health --check`. Active signed `0.1.8` and the candidate both returned:

- total: 15
- available: 14
- ready: 13
- warning: 1
- limited: 1
- failed: 0
- state: `healthy`
- archived count and pending archive candidates: 0

Anonymous full auth/archive inventory summaries were identical before and after both probes. The candidate wrote no CPA state or quarantine record. The temporary artifact was deleted at command exit.

## Remaining gate

The native implementation is source-ready only. A later operator decision must publish and verify a signed release, stage both endpoints, activate in the required endpoint order, back up and replace only the CPA-health unit, observe repeated natural timer runs, and retain signed `0.1.8`, its old unit, and private state for rollback. `/opt/codex-gateway/codexx_app` must not be retired before that gate is accepted.
