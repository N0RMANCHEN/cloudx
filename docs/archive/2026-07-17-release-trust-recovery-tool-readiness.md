# Release Trust Recovery Tool Readiness

## Scope

This batch makes the first step of release-key recovery deterministic and testable. It does not rotate the real trust root, generate a real release key, commit a public key, create or move a tag, publish an artifact or stable ref, stage or activate an endpoint, restart a service, or remove a legacy path.

## Current Evidence

- repository source version: `0.1.15`
- immutable failed publication tag: `v0.1.14`
- `release-artifacts/v0.1.14`: absent
- `release-artifacts/v0.1.15`: absent
- current repository/local/cloud signer fingerprint: `SHA256:jJAS0rbecTDcU4QD3JjkJFv/5YpFyAOAtvdaf0fY4j0`
- all three current `allowed_signers` files: byte-identical
- only visible rejected private-key candidate: different fingerprint and therefore unusable

The immutable `v0.1.14` tag remains untouched. Recovery must advance through source `0.1.15` rather than moving or rebuilding the failed release identity.

## Plan Contract

Running `python3 scripts/prepare_release_trust_recovery.py` against the real repository returned `cloudx.release-trust-recovery-plan.v1` with:

```text
status=confirmation-required
version=0.1.15
confirmation=ROTATE CLOUDX RELEASE TRUST 0.1.15
automaticAction=false
privateKeyConfigured=false
```

Every authorization field was false. The plan named commit, tag, release publication, stable selection, endpoint staging, endpoint activation, service restart, and legacy removal as forbidden actions. It emitted the public current fingerprint but no private path, key content, or secret-derived value.

## Confirmed Transaction Semantics

Only an exact-confirmation apply may:

1. require the requested version to equal repository `VERSION`
2. require repository, local-artifact, and cloud-artifact public roots to be byte-identical
3. require a clean Git worktree
4. require an absolute private-key path outside the repository
5. require the target key and `.pub` companion to be absent
6. require an existing key directory to already be mode `0700`, or create the final directory privately
7. generate one unencrypted Ed25519 private key and force mode `0600`
8. derive a `cloudx-release` allowed-signer line and require a different fingerprint
9. atomically replace all three mode-`0644` public roots
10. verify byte parity and the final replacement fingerprint

If generation, write, or verification fails, all three old public roots are restored and any generated private/public key files are removed. The result never contains the private key path or material.

Successful preparation explicitly leaves commit, tag, publication, stable-ref movement, staging, activation, and service restart unauthorized. Those are separate Roadmap transactions.

## Verification

Isolated tests cover read-only planning, exact confirmation, successful external key creation and three-root synchronization, repository-contained key rejection, broad existing directory rejection without chmod, mismatched-root rejection, partial-write rollback, generated-key cleanup, and secret/path-free output.

The real repository plan was then executed without `--apply`; hashes and fingerprints of all three trust roots remained unchanged and no private key was created.

Full `./verify.sh` passed architecture validation, 234 tests, and healthy local/cloud `0.1.15` builds.

## Decision

The trust-recovery preparation mechanism is ready. Actual rotation remains unexecuted and requires an explicit operator decision naming an external private-key path. After rotation, the public-root diff must be separately reviewed, committed, pushed, tagged, signed, published, freshly verified, and stage-only accepted before any activation can be considered.
