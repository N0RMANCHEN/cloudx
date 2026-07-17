# Phi Consumer Key Installer Readiness

## Scope

This batch prepares the Cloudx-owned transaction that can install or rotate Phi's dedicated gateway bearer. It does not generate a real key, edit gateway configuration, write a credential, create a group or directory, restart the gateway, restart Phi, revoke a previous key, publish a release, stage an endpoint, or change any deployed permission.

## Current Read-Only Evidence

The cloud host still reports:

- orchestrator component current `06c8720298dc0f05dcec847f7a427e4eb08554c0`
- mail-command component current `80e349fc1ba590f321e8e8f576d3371bfcb172a1`
- orchestrator `NoNewPrivileges=yes`
- mail-command `NoNewPrivileges=no`
- no `phi-cloudx-consumer` group
- no `/etc/cloudx/consumers/phi-cloud` directory or credential
- existing Cloudx client credential mode `0600`, owner/group `cloudx:cloudx`

The dedicated runtime credential therefore remains absent and the privileged-boundary evidence remains blocked. All queries were read only.

## Plan Contract

Running:

```text
python3 scripts/install_phi_consumer_gateway_key.py --release-version 0.1.15
```

returned `cloudx.phi-consumer-key-plan.v1` with:

```text
status=confirmation-required
confirmation=RESTART cliproxy.service FOR PHI CLOUDX CONSUMER KEY
credentialClass=scoped_phi_consumer
gatewayRestartRequired=true
phiServiceRestartRequired=false
automaticAction=false
```

Every authorization field was false. The plan read no credential or gateway file and emitted no secret-derived value.

Its explicit preconditions are an exact staged signed artifact, the dedicated group, a root/group mode-`0750` credential directory, and the existing private Cloudx client credential. The current host does not satisfy the first three, so apply is not ready even apart from missing operator confirmation.

## Apply Transaction

Only exact-confirmation root apply may:

1. require `/opt/cloudx/releases/<version>/cloudx-cloud.pyz` and verify its exact version self-check
2. reject alternate config, credential, client-credential, group, unit, or artifact paths
3. reject symlinked, non-regular, oversized, missing, or broadly readable required files
4. require the pre-provisioned credential directory to be root-owned, group-owned, and mode `0750`
5. retain an existing Phi credential in the gateway list before overlap rotation
6. append one new `cloudx-phi-*` gateway key without rewriting unrelated YAML text
7. save the old gateway config in a root-only mode-`0600` backup outside release directories
8. write only the Phi credential as root:`phi-cloudx-consumer` mode `0640`
9. restart only `cliproxy.service`
10. require a real `/v1/models` HTTP 200 and at least two restored gateway watches
11. require the pre-existing Cloudx client credential snapshot to remain byte-identical

The receipt contains counts, process identities, modes, watch count, continuity booleans, and the rollback backup path, but no credential, key hash, token fragment, or account identity. It explicitly reports `previousCredentialRevoked=false` and `phiServiceRestarted=false`.

If any config write, credential write, restart, probe, watch, or continuity check fails, the transaction restores the old config and prior/absent Phi credential, restarts the restored gateway configuration, and removes the failed backup after recovery. It never restores or changes the separate Cloudx client credential because it never owns a write to that file.

## Verification

Focused tests cover read-only planning, fixed contract paths, exact confirmation ordering, missing group, private-client permissions, bounded non-symlink inputs, overlap retention, success continuity, secret-free output, and failed-probe rollback. The final `./verify.sh` run passed all 262 tests and built both `cloudx-local-0.1.15.pyz` and `cloudx-cloud-0.1.15.pyz`.

## Decision

The Cloudx credential transaction is source-ready. Runtime installation remains separately blocked on a signed artifact, Phi-owned group membership and service configuration, the credential directory, an approved gateway restart, a live canary, and post-install proof that interactive/mail/orchestrator Agent surfaces cannot reach Cloudx auth or mutation capabilities.
