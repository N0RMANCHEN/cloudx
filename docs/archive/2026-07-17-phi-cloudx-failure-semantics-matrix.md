# Phi/Cloudx Failure Semantics Matrix

## Scope

This batch completes the Cloudx-owned contract side of the M4A cross-repository failure matrix. It adds no runtime adapter, queue, credential, service, release, deployment, restart, activation, or production mutation.

The evidence is intentionally separate from full cross-repository acceptance. It proves that Cloudx publishes an exact, machine-checked meaning for every required dependency failure; it does not claim that Phi runtime handling, release ordering, or the privileged boundary has passed.

## Exact Phi Snapshot

The fixture records Phi source `3f125abf16fec1e7c17d2ccff0f6ce0a2414193e` and these canonical-file digests:

```text
70f3db6475959fc67f0f97e7e71a2e263c05dc24193cf44fd21bfbbca7ea9fa1  docs/architecture/personal-agent-mesh.md
2780f4ff342586f08effa836d5753d9dcade2158488c44b3f4714b945ab014be  docs/standards/product-acceptance.md
2a3e69c023039b0412d38fb1fdd07c52c78c3809598d9ec94ef4bb727cedf13d  docs/roadmap/roadmap.json
```

The optional checkout-aware verifier matched that commit, all three digests, and the recorded `blocked` status of Phi `INT/P1-1` and `CT/P1-3`. The unrelated untracked Phi worktree content was not read, changed, staged, or committed.

## Contract Matrix

| Case | Cloudx signal/disposition | Permitted Phi provider-phase result |
|---|---|---|
| Gateway unavailable | `gateway_network_failure` / `probe_failure` | wait, degrade, or fail |
| Capacity unknown | `missing_health_observation` / `unknown_observation` | wait, degrade, or fail |
| Capacity exhausted | `no_available_accounts` / `exhausted_capacity` | wait or fail |
| Stale health | `stale_health_observation` / `stale_contract` | wait, degrade, or fail |
| Incompatible protocol | `protocol_range_mismatch` / `incompatible_producer` | fail after compatibility gate |
| Revoked credential | `gateway_credential_invalid` / `probe_failure` | fail |
| Rate limit | HTTP `429` / `consumer_rate_limited` | bounded wait or fail |
| Cloudx rollback | revalidate current/N-1 compatibility | continue, wait, degrade, or fail |
| Independent release order | revalidate before use | continue, wait, degrade, or fail |

Every row forbids Phi truth mutation and Cloudx runtime mutation. The preserved Phi truth set is Device registry, Task, writer/execution lease, approval, revocation, notification, and completed local-action receipt. Cloudx remains owner only of gateway, provider accounts/import, capacity, health, consumer credential, release, and rollback.

The checker reads the actual Cloudx contract files rather than trusting the fixture labels. It requires the capacity states/reasons, revocable scoped credential denials, bounded HTTP-429 retry policy, current/N-1 rollback requirement, independent release ordering, and no synchronized deployment.

## Verification Result

The normal command returned:

```text
phi-failure-semantics: blocked (5 blockers; 9 scenarios; phi-snapshot=recorded)
```

The checkout-aware command returned the same product status with `phiSnapshotVerified=true`. The five blockers are:

1. current/N-1 release ordering is not yet compatible
2. the Phi privileged boundary is not yet secure
3. Phi `INT/P1-1` is not complete
4. Phi `CT/P1-3` is not complete
5. Phi runtime failure fixtures are not accepted

`--require-accepted` exits nonzero while any blocker remains. Normal repository verification accepts the truthful blocked snapshot so contract drift or an accidental false acceptance fails closed.

## Decision

The Cloudx-side M4A failure matrix is complete and continuously checked. The broader cross-repository acceptance gate remains open, and the two existing M4A compatibility/privilege checkboxes remain unchecked. No runtime or operator authority follows from this evidence.
