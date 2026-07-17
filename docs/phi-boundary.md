# Phi Boundary

Phi is a separate product and repository.

## Cloudx-Owned

- gateway integration and readiness
- credential import and account health classification
- reversible credential quarantine with an audit trail
- `cloudx.health.v1`
- scoped Phi cloud consumer credential lifecycle
- provider capacity, compatibility, backpressure, and independent release signals

## Phi-Owned

- mail commands and replies
- Codex goal recovery or watchdog behavior
- DeepSeek and other Phi provider balance monitoring
- human-facing notifications
- an explicit repair assistant that may prepare a branch or pull request
- Personal Agent Mesh Device, Task, writer/execution lease, target selection, approval, ContextRequest, LocalAction, transfer, and Artifact truth
- macOS directory, TCC, Keychain, local policy, and target-device approval

## Shared Rule

Phi may read `/run/cloudx/health.json` or execute `cloudx-remote health --json` with a scoped identity. The signal contains counts and status only. Phi must not read Cloudx keys, auth files, account identities, or release directories.

The M4 target is the exact `cloudx.health.v1` schema produced by a signed Cloudx artifact. The older `/var/lib/cloudx/health/v1.json` document with `contract: cloudx.health` and `schemaVersion: 1` remains a migration-only N-1 bridge, not the final Cloudx runtime contract. It can satisfy only the recorded previous Phi consumer after the bridge itself is published from an immutable signed artifact, installed independently of the Cloudx selector, and rollback-rehearsed.

Cloudx never imports Phi modules and never requires Phi for routing, import, health, recovery, update, or rollback.

The legacy unattended repair timer that edits a checkout, deploys a parser, restarts the importer, and merges a branch is not a supported target behavior. Its replacement is diagnostic evidence plus an operator-reviewed pull request.

## Personal Agent Mesh Companion Boundary

The initial dependency direction is fixed:

```text
trusted devices
      |
      v
Phi private gateway / Task control plane
      |
      v
Cloudx gateway and secret-free health contracts
      |
      v
provider
```

Trusted devices do not register with Cloudx. The Phi cloud runtime is the only normal Mesh consumer, and it uses a scoped credential that is independent from Phi `deviceId`, writer lease, execution lease, or target approval.

| Boundary | Phi | Cloudx |
|---|---|---|
| Device trust, target and local permissions | owner | no visibility |
| Task, lease, approval and LocalAction | owner | no visibility |
| Model request semantics and result use | owner | compatible gateway transport only |
| Gateway, account import and capacity | consume | owner |
| Health, protocol and release compatibility | adapter/policy owner | signal owner |
| Production mutation | Phi release path only | Cloudx release/import path only |

Cloudx public contracts and logs must not contain Phi Task/session IDs, device identities, local paths, approvals, transfer content, or Artifact metadata. Phi must not read Cloudx auth, account identity, importer state, private release directories, or gateway credentials beyond its scoped consumer secret.

The signed cloud runtime enforces the first half of that boundary before every helper stdout/stderr emission and before health or account-state publication. The architecture gate rejects any new direct cloud-runtime output path. The only `device`, `task`, or `session` fields allowed in a Cloudx public contract are literal `false` values inside the scoped consumer credential policy's non-representation declaration; Cloudx signed release `artifacts` are a distinct product-owned release record.

A Cloudx outage, stale health document, unknown capacity, incompatible protocol, revoked consumer credential, or Cloudx rollback may only make provider-dependent Phi phases wait, degrade, or fail. It must not corrupt Phi Device, Task, lease, approval, revocation, notification, or completed local-action truth.

Phi and Cloudx keep independent release trains and N/N-1 rollback. Their compatibility gate binds only public protocol range, health schema, gateway capability, consumer credential revision, capacity/backpressure semantics, and secret-free evidence. No synchronized deployment is required.

`config/governance/phi_cloudx_release_ordering.v1.json` records the current sanitized cross-repository ordering evidence. Its executable audit proves that Phi current can consume both Cloudx current and N-1 directly. For Phi N-1 it now records an explicit legacy-bridge path instead of treating protocol number `1` as sufficient. The source bridge output is accepted by the exact recorded Phi N-1 parser, and the source now includes a non-activating exact-confirmation unit-file installer whose plan is machine-checked. Phi rollback and both upgrade-order sequences remain blocked until signed publication, fixed-artifact unit runtime acceptance, and rollback rehearsal are complete.

`config/governance/phi_cloudx_privileged_boundary.v1.json` records a separate sanitized production permission snapshot. `scripts/check_phi_cloudx_privileged_boundary.py` evaluates the normal interactive CLI, mail-command, and orchestrator Agent instruction surfaces without storing usernames, host addresses, filesystem paths, credential values, or command text. It combines direct Cloudx capabilities with the surface's command tool, runtime identity, privilege-elevation class, `NoNewPrivileges`, and sensitive-path masking.

The current snapshot is `blocked`. Phi's configured Cloudx consumer is still sourced from an administrative gateway key through privilege elevation instead of the dedicated scoped consumer credential. The interactive CLI and authenticated mail-command path expose arbitrary Agent command execution under an identity with unrestricted root elevation, making auth read, import, gateway mutation, and Cloudx release mutation reachable. The active orchestrator does not inherit that effective authority because its unit masks Cloudx-sensitive paths and enforces `NoNewPrivileges=true`. This audit made no credential, sudoers, unit, service, release, or runtime change; remediation and activation remain Phi-owned operator actions.

The normal verifier accepts a truthful `blocked` evidence file so the known external gap stays continuously visible. The M4A acceptance command is stricter:

```bash
python3 scripts/check_phi_cloudx_privileged_boundary.py --require-secure
```

Cloudx publishes the initial reference set as `cloudx.phi-mesh-compatibility-profile.v1` from the signed cloud artifact. The profile reuses `cloudx.handshake.v1`, `cloudx.health.v1`, the migration-only `cloudx.health` v1 bridge, `legacy-gateway.v1`, `cloudx.client-config.v1`, and the existing signed release/status/rollback contracts; it creates no runtime state and grants no credential or mutation authority.

The companion `cloudx.phi-cloud-consumer-credential.v1` policy defines a separate gateway bearer stored outside release directories at `/etc/cloudx/consumers/phi-cloud/credential`, owned by root and readable only by the dedicated `phi-cloudx-consumer` group. It represents the Phi cloud service only, has no SSH or `cloudx-remote` authority, and cannot import, mutate gateway configuration, change releases, or assert Device, Task, or session identity. Rotation installs and canaries a new key before revoking the previous key; the policy itself authorizes no install, rotation, revocation, or restart.

Source `0.1.15` now also carries a repository operator transaction for that exact policy. Its plan is non-authorizing; apply is bound to an exact staged artifact and can change only the external gateway config plus the dedicated credential file, with overlap-first rotation and rollback. Phi identity/group provisioning, Phi service configuration/restart, old-key revocation, and proof that every Agent surface lacks Cloudx authority remain outside that transaction. The deployed credential is still the administrative key, so the privileged-boundary result remains blocked.

`cloudx.phi-cloud-consumer-traffic-policy.v1` supplies the initial four-request concurrency ceiling, sixteen-entry FIFO wait bound, thirty-attempts-per-minute rate with burst four, separated admission/connect/header/stream-idle/overall timeouts, and a three-attempt retry ceiling. Retries consume rate budget, retain the same concurrency slot, and never occur after response bytes. Phi owns enforcement in its provider adapter; Cloudx publishes the rule but stores no queue or work-item metadata.

The live `cloudx.capacity.v1` result preserves six distinct states: healthy capacity, exhausted capacity, unknown observation, stale contract, probe failure, and incompatible producer. It includes only producer/consumer protocol ranges, gateway probe class, freshness, and aggregate account counts. Phi must not collapse unknown, stale, failed, or incompatible states into exhausted capacity.

`config/governance/phi_cloudx_failure_semantics.v1.json` binds those public contracts to a strict nine-case dependency matrix: gateway unavailable, capacity unknown, exhausted capacity, stale health, incompatible protocol, revoked credential, rate limit, Cloudx rollback, and independent release ordering. Every case permits only an explicit provider-phase outcome and forbids mutation of Phi Device, Task, lease, approval, revocation, notification, or completed local-action truth. It also freezes the matching owner matrix and records exact digests for the relevant Phi canonical architecture, acceptance, and Roadmap files.

The normal verifier accepts the truthful blocked snapshot while checking that the Cloudx matrix remains complete and contract-backed. A checkout-aware audit can additionally verify the exact Phi commit and file digests:

```bash
python3 scripts/check_phi_cloudx_failure_semantics.py --phi-root <phi-checkout>
```

The stricter `--require-accepted` exit remains nonzero until current/N-1 release ordering is compatible, the privileged boundary is secure, Phi `INT/P1-1` and `CT/P1-3` are complete, and Phi runtime fixtures are accepted. The fixture grants no credential, deployment, restart, release, or runtime mutation authority.

Direct endpoint-to-Cloudx connectivity for future local inference is outside the initial Mesh boundary and requires its own threat model, credential contract, roadmap gate, and operator approval.
