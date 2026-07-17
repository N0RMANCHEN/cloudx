# Release Trust Rotation

Date: 2026-07-17

## Decision

The operator supplied the exact confirmation:

```text
ROTATE CLOUDX RELEASE TRUST 0.1.15
```

That confirmation authorized only repository-external key generation and synchronization of the three public source trust roots. It did not authorize a tag, release publication, stable-ref movement, endpoint staging or activation, service restart, credential change, or legacy retirement.

## Transaction Result

`scripts/prepare_release_trust_recovery.py` returned:

```text
schema=cloudx.release-trust-recovery.v1
status=prepared
version=0.1.15
previousFingerprint=SHA256:jJAS0rbecTDcU4QD3JjkJFv/5YpFyAOAtvdaf0fY4j0
replacementFingerprint=SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o
privateKeyCreated=true
privateKeyMode=0600
privateKeyInRepository=false
publicRootsUpdated=3
publicRootsMatch=true
automaticAction=false
```

The repository-external key directory is owned by the operator and mode `0700`; the private key is owned by the operator and mode `0600`. The private path and key material are intentionally absent from this record.

The following public files are byte-identical:

- `release/allowed_signers`
- `local/cloudx_local/data/allowed_signers`
- `cloud/cloudx_cloud/data/allowed_signers`

Their shared file SHA-256 is:

```text
b1c18acca5e619b52489bef8b9b2948ac0b5842b14627a30c015d801598d85fc
```

An independent `ssh-keygen -lf` check of the generated public companion returned the same replacement fingerprint recorded by the transaction.

## Verification And Boundaries

Full `./verify.sh` passed after the real rotation:

- architecture: ok
- 316 tests: passed
- local `0.1.15` candidate build: passed
- cloud `0.1.15` candidate build: passed

The existing external/runtime blockers remained truthful: legacy-health bridge source readiness still has three runtime blockers, Phi privileged-boundary and release-ordering checks remain blocked, and no checker was changed to claim runtime acceptance.

No `release-artifacts/v0.1.15` ref or `v0.1.15` tag existed at rotation time. The cloud endpoint remained `current=0.1.13`, `previous=0.1.12`, with no staged `0.1.15` artifact. No local selector, shell hook, account, external CPA process, cloud gateway/importer process, listener, systemd unit, Phi credential, or health publisher changed.

## Commit Boundary And Next Gate

This batch's repository commit contains only the three public roots, current documentation, and this secret-free evidence. The private key remains outside Git. After this commit, the next Roadmap item is an independently controlled `0.1.15` tag, signed artifact/stable publication, verification, and stage-only acceptance. None of those later actions is implied by this rotation receipt.
