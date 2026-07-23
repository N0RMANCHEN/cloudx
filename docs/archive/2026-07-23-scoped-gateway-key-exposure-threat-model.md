# Scoped Gateway Key Exposure Threat Model

Date: 2026-07-23

## Incident Boundary

During a read-only active-pool diagnosis, `cloudx-remote client-config --json` returned the existing scoped Cloudx gateway credential into the private tool transcript. The value was not copied into a repository file, commit, release, health document, or operator receipt. This document intentionally contains no key or credential digest.

The credential authorizes the Cloudx client path to call the gateway inference surface. It is not an SSH identity and grants no Cloudx import, credential-file, release, selector, service, Phi, or host-administration authority. An attacker would still require network reachability to the gateway, but transcript access plus that reachability is sufficient reason to treat the key as exposed.

## Read-Only Production State

- `/etc/cloudx/client-credential` remains a regular mode-`0600` file owned by its existing private service identity.
- Its value occurs exactly once in `/etc/cliproxy/config.yaml`.
- The gateway API-key list contains five entries in aggregate; no key value was printed.
- `cliproxy.service` remains active as PID `1871934`, restart count `0`.
- Cloudx remains signed `0.1.29/0.1.28` with current artifact SHA-256 `272ce07da46da5f3d6c9e52dd108a2517bec4eadab3f0547324f6631413e8aa5`.
- The initial 0.1.29 scoped-key invocation returned only `cloudx.scoped-key-plan.v1`, `status=confirmation-required`, and the exact restart confirmation. It read no production key and changed nothing. Source `0.1.30` now adds the pre-mutation digest manifest and exact-one revocation transaction required below.
- The first signed 0.1.30 Phase 1 apply then rejected two valid plain YAML key scalars before writing any file or restarting any service. Aggregate verification retained five keys, one credential match, unchanged process/restart state, and zero rotation transactions. Source 0.1.31 adds bounded mixed-scalar compatibility; manual production YAML normalization is not authorized.

## Existing Rotation Capability

`scripts/install_scoped_gateway_key.py` already provides an overlap-first installation transaction:

1. bind the exact signed staged cloud artifact and release version;
2. require `RESTART cliproxy.service FOR CLOUDX SCOPED KEY` before filesystem or service mutation;
3. append a fresh random key while preserving every existing key;
4. atomically switch `/etc/cloudx/client-credential` and its version-matched environment;
5. restart only `cliproxy.service`;
6. require HTTP `200` with the new key and restored config/auth watches;
7. restore config, credential, environment, and the old service configuration on failure.

This is necessary but insufficient remediation. By design it retains the old key for overlap continuity. Successful rotation therefore reduces reliance on the exposed key but does not revoke it.

## Required Two-Phase Remediation

### Phase 1: Overlap Rotation

This phase requires its own exact operator confirmation and gateway restart. Acceptance must prove:

- exact signed 0.1.31 artifact identity and unchanged non-gateway production boundaries;
- the new credential occurs exactly once and the previous credential remains exactly once;
- real gateway model traffic with the new credential;
- a fresh local `codexx cloud` broker generation fetches the new remote client configuration;
- real official-Codex-through-cloud traffic succeeds from that fresh generation;
- Phi's distinct consumer credential and every unrelated gateway key remain byte-identical;
- no credential value appears in stdout, receipts, logs, or repository state.

Failure restores the complete pre-rotation config, credential, environment, gateway process health, and client communication.

### Phase 2: Exact-One Revocation

Revocation is a later, separately confirmed restart boundary. Source `0.1.31` implements the required dedicated transaction with mixed YAML string-scalar compatibility; production use still waits for signed publication, endpoint installation, accepted Phase 1 evidence, and its own restart action. It must:

- bind the current config and private previous/current credential evidence without emitting either value;
- require the new credential to be active and accepted by fresh broker plus official-Codex canaries;
- remove exactly one list entry matching the privately bound old credential and leave all other entries byte-identical and ordered;
- restart only `cliproxy.service`;
- require the new key to return HTTP `200` and the old key to be rejected;
- require restored inotify watches, unchanged non-gateway services, and fresh formal health;
- atomically restore the complete prior config and old gateway process behavior if any check fails.

The revocation receipt may report only counts, booleans, service identities, public status codes, and config digests. It must never contain either credential.

## Decision

The operator has now approved both separate maintenance actions, but approval does not bypass their ordering or acceptance gates. Phase 1 and Phase 2 each change external gateway state and restart an externally owned dependency; each must still use its exact confirmation, automatic rollback, and independent evidence. Until both pass, the scoped key must be treated as exposed.

Phase 1 transaction `20260723T063726Z-485a416b` has now completed the overlap mutation and all key/tunnel/health checks: both old and new keys return HTTP `200`, unrelated and Phi consumer keys are preserved, and fresh broker/client-config routing is authorized. Its official-Codex business request reached the cloud gateway but returned existing capacity-layer `503 auth_unavailable`. That is not a credential `401`, but it does leave the required successful business canary unproven. The previous key therefore remains deliberately active and Phase 2 remains forbidden until a fresh real model request succeeds without any account mutation inferred from this authorization.

The capacity gate was later closed by the separately authorized active-pool recovery transaction and official-Codex marker `CLOUDX_PHASE1_ACCEPTED_0_1_33_OK`. Phase 2 then completed on the same rotation transaction: the current key returns HTTP `200`, the exposed previous key returns HTTP `401`, unrelated and Phi consumer keys remain unchanged, and official Codex returned `CLOUDX_PHASE2_REVOKED_OK`. The exposed credential is revoked and this threat-model remediation is closed.
