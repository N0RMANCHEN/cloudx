# Phi N-1 Legacy Health Bridge Rollback Rehearsal

## Scope

This rehearsal proves that the migration bridge remains available while the Cloudx endpoint selector rolls back independently. Every artifact, selector, input, output, and release directory is created inside an automatically cleaned temporary root. It does not use the production release root, publish or stage an artifact, install a unit, start or stop a service, modify a real selector, read a credential, or write production health state.

## Candidate And Initial State

The rehearsal built the cloud candidate from repository source `0.1.15` at commit `5bceafa0f38d3eb8941cefa3f8c36b241a53d60c`. It copied that candidate to a fixed isolated release path equivalent to `/opt/cloudx/releases/0.1.15/cloudx-cloud.pyz` and required a healthy `cloudx.self-check.v1` response before use.

The isolated endpoint used placeholder rollback artifacts only to exercise the real selector transaction. Its initial state reproduced the accepted production pair:

```text
current=0.1.13
previous=0.1.12
```

The bridge candidate was not reached through either selector.

## Round Trip

The rehearsal ran the candidate bridge in each state and invoked `cloudx_cloud.release.rollback()` for both selector changes:

```text
0.1.13 / 0.1.12
0.1.12 / 0.1.13
0.1.13 / 0.1.12
```

All three invocations read the same formal fixture, published through the candidate's atomic legacy writer, and produced byte-identical persisted output. The final machine result recorded:

- candidate artifact SHA-256: `8c74f2e9c8b21dcc982f7c379bfd8e07689334a47264bad2a3709883522f860b`
- legacy output SHA-256: `ac8a955a2f2482f4581cc7117086a6080247aee2df5a9837f6044919cceb1a11`
- `rollbackRoundTrip=true`
- `fixedArtifactIndependent=true`
- `outputByteStable=true`

The artifact digest is tied to the recorded source commit and deterministic zipapp build. No real signed artifact was claimed or produced.

## Exact Phi N-1 Check

The optional checkout-aware run again loaded Phi release `17d3e42e61fb2d88bf47c25497c05f0b3bb47438` and consumer SHA-256 `6dea38ff43102a944027fe43f4419f19a8d931331d6dcc7d21827fa4d340123b`. Its real parser accepted the final round-trip output as:

```text
summaryState=degraded
capacityState=low_capacity
```

The sibling Phi checkout was read only and its unrelated local state was unchanged.

## Authorization Boundary

The result sets `automaticAction=false` and keeps publication, endpoint staging, unit installation, service start, and production selector mutation authorization false. The governance evidence records this as `sourceAcceptance.isolatedSelectorRollback=true`; it deliberately leaves `runtimeAcceptance.rollbackRehearsed=false`.

This distinction matters: an isolated selector proof reduces implementation risk, but only a separately approved signed-artifact unit transaction and real independent rollback can close the production ordering gate.

## Verification

The focused integration test and exact Phi run passed. Full `./verify.sh` then passed architecture validation, all 252 tests, and healthy local/cloud `0.1.15` builds while retaining the truthful source-ready/blocked runtime gates.
