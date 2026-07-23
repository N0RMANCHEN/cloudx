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
- The default 0.1.29 scoped-key invocation returned only `cloudx.scoped-key-plan.v1`, `status=confirmation-required`, and the exact restart confirmation. It read no production key and changed nothing.

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

- exact signed 0.1.29 artifact identity and unchanged non-gateway production boundaries;
- the new credential occurs exactly once and the previous credential remains exactly once;
- real gateway model traffic with the new credential;
- a fresh local `codexx cloud` broker generation fetches the new remote client configuration;
- real official-Codex-through-cloud traffic succeeds from that fresh generation;
- Phi's distinct consumer credential and every unrelated gateway key remain byte-identical;
- no credential value appears in stdout, receipts, logs, or repository state.

Failure restores the complete pre-rotation config, credential, environment, gateway process health, and client communication.

### Phase 2: Exact-One Revocation

Revocation is a later, separately confirmed restart boundary and needs a dedicated transaction that does not yet exist. It must:

- bind the current config and private previous/current credential evidence without emitting either value;
- require the new credential to be active and accepted by fresh broker plus official-Codex canaries;
- remove exactly one list entry matching the privately bound old credential and leave all other entries byte-identical and ordered;
- restart only `cliproxy.service`;
- require the new key to return HTTP `200` and the old key to be rejected;
- require restored inotify watches, unchanged non-gateway services, and fresh formal health;
- atomically restore the complete prior config and old gateway process behavior if any check fails.

The revocation receipt may report only counts, booleans, service identities, public status codes, and config digests. It must never contain either credential.

## Decision

No rotation or revocation is authorized by this threat model, repository verification, or the user's general Roadmap instruction. Phase 1 and Phase 2 each change external gateway state and restart an externally owned dependency, so each needs explicit operator approval. Until both pass, the scoped key must be treated as exposed.
