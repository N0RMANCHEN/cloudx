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

The M4 target is the exact `cloudx.health.v1` schema produced by a signed Cloudx artifact. The older `/var/lib/cloudx/health/v1.json` document with `contract: cloudx.health` and `schemaVersion: 1` is sanitized migration evidence, but it is not the Cloudx runtime contract and cannot satisfy the final consumer gate.

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

A Cloudx outage, stale health document, unknown capacity, incompatible protocol, revoked consumer credential, or Cloudx rollback may only make provider-dependent Phi phases wait, degrade, or fail. It must not corrupt Phi Device, Task, lease, approval, revocation, notification, or completed local-action truth.

Phi and Cloudx keep independent release trains and N/N-1 rollback. Their compatibility gate binds only public protocol range, health schema, gateway capability, consumer credential revision, capacity/backpressure semantics, and secret-free evidence. No synchronized deployment is required.

Cloudx publishes the initial reference set as `cloudx.phi-mesh-compatibility-profile.v1` from the signed cloud artifact. The profile reuses `cloudx.handshake.v1`, `cloudx.health.v1`, `legacy-gateway.v1`, `cloudx.client-config.v1`, and the existing signed release/status/rollback contracts; it creates no new runtime state and grants no credential or mutation authority.

The companion `cloudx.phi-cloud-consumer-credential.v1` policy defines a separate gateway bearer stored outside release directories at `/etc/cloudx/consumers/phi-cloud/credential`, owned by root and readable only by the dedicated `phi-cloudx-consumer` group. It represents the Phi cloud service only, has no SSH or `cloudx-remote` authority, and cannot import, mutate gateway configuration, change releases, or assert Device, Task, or session identity. Rotation installs and canaries a new key before revoking the previous key; the policy itself authorizes no install, rotation, revocation, or restart.

`cloudx.phi-cloud-consumer-traffic-policy.v1` supplies the initial four-request concurrency ceiling, sixteen-entry FIFO wait bound, thirty-attempts-per-minute rate with burst four, separated admission/connect/header/stream-idle/overall timeouts, and a three-attempt retry ceiling. Retries consume rate budget, retain the same concurrency slot, and never occur after response bytes. Phi owns enforcement in its provider adapter; Cloudx publishes the rule but stores no queue or work-item metadata.

Direct endpoint-to-Cloudx connectivity for future local inference is outside the initial Mesh boundary and requires its own threat model, credential contract, roadmap gate, and operator approval.
