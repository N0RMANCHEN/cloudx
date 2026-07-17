# Phi N-1 Legacy Health Bridge Readiness

## Scope

This batch prepares the explicit migration bridge required for independent Phi and Cloudx release ordering. It changes repository source, contracts, tests, and offline templates only. It does not rotate the release key, publish or stage an artifact, install a unit, start or stop a service, change a release selector, write production health state, roll Phi back, or remove the existing exporter.

## Read-Only Runtime Finding

The cloud host still has both health documents:

- formal `/run/cloudx/health.json`: `cloudx.health.v1`, refreshed by the enabled active signed Cloudx health timer
- legacy `/var/lib/cloudx/health/v1.json`: `contract=cloudx.health`, `schemaVersion=1`, refreshed by the enabled legacy timer

Cloudx selects signed `0.1.13` with `0.1.12` as previous. Phi component state selects goal-watchdog release `b9f668444ebc8f0258b152d3225df14e113860bf` with `17d3e42e61fb2d88bf47c25497c05f0b3bb47438` as previous.

The legacy document is currently fresh and valid, but its service executes `/home/hirohi/workspace/cloudx/scripts/export_cloudx_health.py` from a mutable checkout. That violates the production release boundary and cannot serve as accepted N/N-1 ordering evidence. The service and output were inspected read-only and left unchanged.

The final continuity check still reported Cloudx selectors `0.1.13/0.1.12`, importer PID `133756` with restart count `0`, and gateway PID `977036` with restart count `0`; both services remained active/running. No candidate unit or production file was installed.

## Signed-Source Bridge

Source `0.1.15` now provides `cloudx-remote legacy-health-bridge` and advertises `legacy-health-bridge.v1` in the handshake, compatibility profile, and signed release manifest. The command:

- accepts only a bounded non-symlink regular `cloudx.health.v1` input
- rejects missing, unknown, mistyped, inconsistent, oversized, and unsupported fields
- keeps unclassified accounts as `unknown`
- maps only formal `limited` counts to quota and keeps generic unavailable counts under `other`
- leaves gateway/import process state, HTTP status, failure receipts, active sessions, and recovery time unknown rather than probing or inventing them
- preserves unknown freshness as a missing legacy observation timestamp
- preserves formal `checkedAt` as legacy `generatedAt`, so repeated bridging cannot make stale or future source evidence look newly generated
- validates the exact legacy shape and digest before output
- writes only through atomic mode-`0644` replacement when `--publish-to` is explicitly supplied
- passes the same fail-closed Phi metadata boundary as other cloud output and publication

The shared schema is `cloudx.legacy-health.v1.schema.json`; the wire identity intentionally remains the previous consumer's `contract=cloudx.health` and `schemaVersion=1`.

## Rollback-Safe Template Boundary

The packaged service does not execute `/opt/cloudx/current`. Its root-owned, non-secret environment file selects one exact immutable path such as `/opt/cloudx/releases/0.1.15/cloudx-cloud.pyz`. This keeps the bridge available if the Cloudx endpoint selector rolls back independently.

The unit reads only the formal health file and immutable release/configuration paths, writes only `/var/lib/cloudx/health`, masks all declared credential/auth locations, enables only `AF_UNIX`, and uses no mutable home checkout. The adjacent timer is repeating and persistent. Templates are inspectable through `cloudx-remote systemd-template`; repository build or activation does not install or start them.

## Exact Phi N-1 Verification

The evidence binds:

- Phi previous release: `17d3e42e61fb2d88bf47c25497c05f0b3bb47438`
- consumer file: `deploy/cloud/phi_cloudx_health.py`
- consumer SHA-256: `6dea38ff43102a944027fe43f4419f19a8d931331d6dcc7d21827fa4d340123b`

The checkout-aware command loaded that exact Git object, executed its real `load_health_summary` and `goal_capacity_snapshot` functions against the generated bridge example, and returned `summaryState=degraded` plus `capacityState=low_capacity`. It did not classify the document as invalid, incompatible, or stale.

```text
python3 scripts/check_phi_cloudx_legacy_health_bridge.py --phi-root /Users/BofeiChen/Phi --json
```

The sibling Phi checkout was read only; its unrelated local state was not changed.

## Remaining Gates

The machine result is deliberately `source-ready`, not `runtime-accepted`, with three blockers:

1. `signed_artifact_not_published`
2. `bridge_unit_not_installed`
3. `rollback_not_rehearsed`

Every publication, install, service-start, and rollback authorization field remains false. The release-ordering matrix now labels Phi N-1 pairs `legacy_bridge_pending`; the M4A ordering checkbox remains open until all three runtime gates have accepted evidence.

## Verification

Focused bridge, contract, template, release, ordering, and exact-consumer checks pass. Full `./verify.sh` then passed architecture validation, all 249 tests, and healthy local/cloud `0.1.15` builds. The normal verifier continues to report bridge `source-ready`, release ordering `blocked`, privileged boundary `blocked`, and cross-repository failure semantics `blocked` rather than weakening any runtime gate.
