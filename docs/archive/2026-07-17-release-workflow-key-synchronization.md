# Release Workflow Key Synchronization

Date: 2026-07-17

## Decision

The operator completed GitHub CLI browser authentication as repository administrator and supplied the exact confirmation:

```text
SYNCHRONIZE CLOUDX RELEASE WORKFLOW KEY 0.1.15
```

The confirmation authorized only the fixed GitHub `release` environment secret write and one non-publishing signing canary. It did not authorize a tag, artifact/stable publication, GitHub Release, endpoint staging/activation, service restart, credential use outside the release workflow, or legacy mutation.

## Preflight

- local `HEAD`: `f245186f62f298dba015f7a122a63eb2db177b33`
- `origin/main`: `f245186f62f298dba015f7a122a63eb2db177b33`
- worktree: clean
- repository permission: administrator
- GitHub environment: `release`, present, no protection-rule blocker
- environment secret `CLOUDX_RELEASE_SIGNING_KEY`: absent before apply
- signer fingerprint: `SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o`
- all three committed public roots: byte-identical to that signer
- `v0.1.15`: absent
- `release-artifacts/v0.1.15`: absent
- stable ref before apply: `ef5520e54a2832133ed1696b356cbfd9a7da4693`

The external private key passed owner, mode-`0700` parent, mode-`0600` file, non-symlink, bounded-read, Ed25519, and committed-root matching checks. Its path and bytes are not recorded here.

## Transaction Receipt

The transaction returned:

```text
schema=cloudx.release-workflow-key.v1
status=canary-accepted
version=0.1.15
repository=N0RMANCHEN/cloudx
branch=main
workflow=release.yml
environment=release
secret=CLOUDX_RELEASE_SIGNING_KEY
headCommit=f245186f62f298dba015f7a122a63eb2db177b33
signerFingerprint=SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o
secretExistedBefore=false
environmentSecretUpdated=true
workflowDispatched=true
runId=29579236303
signedReleaseVerified=true
releaseRefsUnchanged=true
tagCreated=false
artifactRefPublished=false
stableMoved=false
endpointStaged=false
endpointActivated=false
serviceRestarted=false
```

GitHub reports the environment secret metadata update at `2026-07-17T12:09:03Z`. The secret value remains unreadable and is absent from command output, logs, contracts, Git, and this evidence.

## Independent Workflow Verification

Run `29579236303` was independently read through the GitHub API:

```text
event=workflow_dispatch
headBranch=main
headSha=f245186f62f298dba015f7a122a63eb2db177b33
status=completed
conclusion=success
createdAt=2026-07-17T12:09:06Z
updatedAt=2026-07-17T12:09:38Z
```

The release job and these relevant steps succeeded:

- checkout
- Python setup
- `./verify.sh`
- signing-key load
- signed release build
- signed release evidence verification

The tag-verification step was skipped because the event was not a tag. `publish_release_refs.py` and GitHub Release publication were also skipped by their tag-only conditions. No workflow step published or staged an artifact outside the temporary runner.

After completion, stable still resolved to `ef5520e54a2832133ed1696b356cbfd9a7da4693`; `v0.1.15` and `release-artifacts/v0.1.15` remained absent.

## Boundary And Next Gate

No local/cloud selector, installed artifact, shell hook, account, external CPA, gateway/importer process, listener, systemd unit, Phi credential, or health publisher changed.

This evidence commit changes `main` after the accepted run. Therefore a final verification-only `workflow_dispatch` must succeed on the exact pushed commit that will become `v0.1.15`, with release refs still unchanged, before a separate explicit tag/publication decision. The synchronized secret does not itself authorize that tag.
