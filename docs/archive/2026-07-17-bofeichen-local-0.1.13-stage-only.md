# BofeiChen Local 0.1.13 Stage-Only Recovery

## Scope

This batch adds and exercises an exact-confirmation stage-only installer path on the `/Users/BofeiChen` macOS endpoint. It does not activate a release, move `current` or `previous`, install a shell hook, seed a profile, create or modify a legacy backup, contact the cloud endpoint, start a broker, stop a process, or change the external local CPA.

## Baseline

The endpoint was outside the earlier `0.1.13/0.1.12` local acceptance evidence:

- `current` selected signed `0.1.8`
- `previous` selected signed `0.1.7`
- signed local releases through `0.1.8` were present, but `0.1.13` was absent
- the installed `0.1.8` updater rejected the current stable index with `release signature verification failed`
- port `18317` had no listener
- the external local CPA retained its existing port-`8317` listener
- no Cloudx broker process or listener was active

The failure is a trust-recovery problem for a lagging installed updater, not permission to bypass release verification or activate from source.

## Implementation

`./install --stage-only` now has a distinct `STAGE CLOUDX <ENDPOINT> <version>` confirmation. It fetches the exact `release-artifacts/v<version>` ref and uses the repository trust root to verify the release signature, manifest artifact digest, and component self-check.

Local stage-only execution writes only the side-by-side release directory. Cloud stage-only execution has the same non-activation contract and still requires root for its release root. The ordinary install/activation behavior and its separate `INSTALL CLOUDX ...` confirmation remain unchanged.

## Real Staging Evidence

The exact command staged signed `0.1.13` locally and returned:

```text
schema=cloudx.install-stage.v1
status=staged
staged.local=staged
staged.cloud=not-requested
activated=false
shellSourceInstalled=false
nativeProfileChanged=false
legacyBackupChanged=false
```

An immediate repeat returned `staged.local=already-staged` with the same non-activation fields.

The staged artifact returned `cloudx.self-check.v1` with local component, version `0.1.13`, protocol range `1..1`, and status `ok`. Public artifact evidence is:

```text
manifest sha256 = a4b77470a4cc856775f957e4f816da50ede95400b999564528156a13029d6abb
local pyz sha256 = c2fc23d4b742e72dd0ada4bbafa380d3fbe4b3f790376e3484d2759f34afd532
```

## No-Activation Acceptance

Before and after staging:

- `current` remained `0.1.8`
- `previous` remained `0.1.7`
- `.zshrc`, the installed Cloudx shell source, and the account-state document were byte-identical
- the external local CPA retained the same PID and port `8317`
- port `18317` remained closed
- no Cloudx broker process appeared
- no cloud release was requested

The installed `cloudx-update` continues to execute `0.1.8` and may continue rejecting the new stable-index signature until a separately confirmed activation installs a newer updater. That expected limitation does not weaken the staged artifact verification.

## Decision

The lagging endpoint now has a verified signed `0.1.13` candidate available for an explicit later activation and N-1 reconciliation. Activation, hook installation, profile seeding, rollback-link changes, local CPA retirement, and legacy package removal remain unapproved and incomplete.
