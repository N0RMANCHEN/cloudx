# Release Workflow Key Readiness

Date: 2026-07-17

## Scope

This batch closes the source/tooling gap between the separately rotated `0.1.15` public trust root and the GitHub Actions release workflow. It does not update a real GitHub secret, dispatch a real workflow, create a tag, publish an artifact or stable ref, stage or activate an endpoint, restart a service, or mutate a legacy path.

## Current Evidence

- committed and pushed trust-root commit: `cdaaecfa1f1a4bcc5731ca33b11669c5addf3939`
- current public signer fingerprint: `SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o`
- repository-external key: present, parent mode `0700`, private file mode `0600`
- `release-artifacts/v0.1.15`: absent
- `v0.1.15`: absent
- cloud staged `0.1.15`: absent
- release workflow: `release.yml`, fixed `release` environment, `workflow_dispatch` enabled, signing key read from `CLOUDX_RELEASE_SIGNING_KEY`
- artifact/stable publication steps: both guarded by the tag-only condition
- local GitHub CLI authentication: absent

The authentication audit emitted no token or secret metadata. Because the endpoint is not logged into GitHub CLI, no environment or repository secret inventory could be read and no external mutation was attempted.

## Plan Contract

The default invocation emits `cloudx.release-workflow-key-plan.v1` with:

```text
status=confirmation-required
version=0.1.15
repository=N0RMANCHEN/cloudx
branch=main
workflow=release.yml
environment=release
secret=CLOUDX_RELEASE_SIGNING_KEY
confirmation=SYNCHRONIZE CLOUDX RELEASE WORKFLOW KEY 0.1.15
automaticAction=false
```

Every authorization field is false. The result reports only whether a private-key argument was configured; it never reads or emits the path or key material and performs no Git or GitHub command.

## Confirmed Transaction Semantics

Only exact-confirmation apply may:

1. take a mode-`0600` user-private transaction lock;
2. require clean local `main` and exact equality with pushed `origin/main`;
3. require the private key outside the repository under an owner mode-`0700` directory, read its bytes without following symlinks, and derive its public key locally without emitting the path or material;
4. derive its Ed25519 public key and require byte/fingerprint equality with all three committed trust roots;
5. bind origin to `N0RMANCHEN/cloudx` and validate the fixed workflow, environment, secret name, dispatch path, verification commands, and tag-only publication guards;
6. require authenticated GitHub CLI access and the existing `release` environment;
7. require the requested tag and artifact ref to be absent and snapshot the stable ref plus prior dispatch runs;
8. send private key bytes only to `gh secret set` stdin for the `release` environment;
9. discover the new pushed-HEAD workflow-dispatch run and require its signed release verification to finish successfully;
10. require tag, artifact, and stable refs to remain byte-identical to the pre-write snapshot.

Success emits `cloudx.release-workflow-key.v1` with the public commit, signer fingerprint, workflow run ID, and explicit false publication/staging/activation/restart fields. It contains no key path or material.

## Non-Rollbackable Boundary

GitHub never exposes the old secret value. Therefore the transaction deliberately performs every reversible precondition before the write and never claims automatic secret rollback. If secret upload returns uncertainty, or any later metadata, dispatch, run, identity, signature, or ref check fails, the command returns nonzero with an explicit instruction not to create a release tag. A later separately confirmed run with the same matching key is the recovery path.

## Verification

Focused tests cover offline planning, exact confirmation, key path/mode/symlink limits, root matching, workflow publication isolation, pushed-HEAD binding, existing-ref rejection, stdin-only transfer, successful canary semantics, secret-write uncertainty, post-write canary failure, ref mutation, private locking, and path/key-free receipts.

The real default plan ran without GitHub authentication or mutation. Thirteen focused transaction tests passed. Full `./verify.sh` then passed architecture validation, 330 tests, and healthy local/cloud `0.1.15` candidate builds while retaining the truthful external/runtime blocker states.

## Decision

The synchronization transaction is source-ready. Real execution remains blocked until the operator authenticates GitHub CLI on this endpoint and supplies the exact confirmation. Tagging `v0.1.15` before a successful receipt is prohibited because the workflow secret has not yet been proven to match the newly committed public root.
