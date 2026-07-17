# Release Trust Recovery Pipeline Rehearsal

## Scope

This rehearsal closes the test gap between preparing a replacement public root and proving that the normal release artifacts can use it. It operates only inside a test-owned temporary directory. It does not rotate the repository's real trust root, retain a private key, commit or push a public root, create or move a tag, publish a release ref, stage a real endpoint, activate a selector, restart a service, or remove a legacy path.

## Pipeline

The integration regression performs the following sequence with source version `0.1.15`:

1. copy the local, cloud, release, and required release-tool sources into a temporary source root
2. save that copy's original public root as negative-test evidence
3. run the production trust-recovery preparation function with Git checking disabled only for the isolated copy
4. generate a mode-`0600` Ed25519 key outside the copied source root and atomically synchronize its three copied public roots
5. run the normal release creator to build both zipapps, sign the manifest, and create the offline bundle
6. verify the signed release with the replacement root and require verification with the original root to fail
7. run the normal stable-index creator and require its manifest digest to equal the release manifest digest
8. invoke the newly built local candidate to verify that stable index with its own embedded replacement root
9. invoke the local candidate twice for isolated local-only staging and require `staged`, then `already-staged`
10. invoke the cloud candidate twice with the same offline bundle and require `staged`, then `already-staged`

The regression reads each candidate zipapp directly and requires its embedded `allowed_signers` bytes to equal all three replacement public roots. Endpoint verification therefore does not rely on a mocked signer or the active repository package.

## Safety Assertions

- The replacement fingerprint differs from the copied original root.
- The original root rejects the replacement-signed manifest.
- The signed stable index identifies `0.1.15` and binds the exact manifest SHA-256.
- Both candidate self-checks execute as part of staging.
- The isolated local and cloud release directories retain the replacement root used for verification.
- Neither isolated endpoint receives a `current` or `previous` selector.
- Every authorization field returned by trust preparation remains false.
- The temporary directory cleanup discards the generated key, copied roots, bundle, stable index, and staged candidates.

## Verification

The focused command is:

```text
python3 -m unittest tests.integration.test_release_trust_recovery_pipeline -v
```

It passes the complete pipeline without network publication or production state access. Full `./verify.sh` then passed architecture validation, all 235 tests, and healthy local/cloud `0.1.15` builds. After both runs, the three real trust-root files remained byte-identical with SHA-256 `6435a8c5da019112938ccb00f2ae22c8ca5f74f91dbc0800cd8cec8540374cc7`.

## Decision

The source-level trust-recovery and signed-release pipeline are compatible end to end. This evidence does not authorize the real rotation. An operator must still explicitly approve the real external key path and trust-root write; commit, push, tag, publication, real endpoint staging, activation, and service changes remain separately gated transactions.
