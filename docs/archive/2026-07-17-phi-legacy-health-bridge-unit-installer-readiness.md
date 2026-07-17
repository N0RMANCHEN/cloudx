# Phi Legacy Health Bridge Unit Installer Readiness

## Scope

This batch prepares the Cloudx-owned unit-file installation transaction for the migration-only Phi N-1 health bridge. It changes source, contracts, tests, governance evidence, and documentation only. It does not publish or stage `0.1.15`, install a production file, reload production systemd, start or enable the candidate, stop or disable the existing exporter, write legacy health output, change a selector, roll Phi back, or retire a legacy path.

## Current Runtime Boundary

The most recent read-only host evidence still shows the existing `cloudx-health-contract.timer` enabled and active, with the valid legacy document at `/var/lib/cloudx/health/v1.json`. Its service executes the mutable checkout exporter at `/home/hirohi/workspace/cloudx/scripts/export_cloudx_health.py`, so it remains a rollback path but cannot satisfy the fixed-artifact acceptance gate.

The formal signed Cloudx health timer remains enabled and active. Cloudx still selects `0.1.13/0.1.12`, the importer remains PID `133756` with restart count zero, and the gateway remains PID `977036` with restart count zero. No `cloudx-legacy-health-bridge` production unit or signed `0.1.15` artifact is installed.

## Read-Only Plan

Running:

```text
python3 scripts/install_legacy_health_bridge_units.py --release-version 0.1.15
```

returned `cloudx.legacy-health-bridge-unit-plan.v1` with the exact confirmation:

```text
INSTALL cloudx-legacy-health-bridge UNITS WITHOUT START
```

The plan read no artifact, unit file, systemd state, legacy output, credential, or release selector. It reported `serviceStartRequired=false`, `timerEnableRequired=false`, `automaticAction=false`, and every authorization field false.

## Apply Transaction

Only root apply with that exact confirmation may:

1. accept the exact `/opt/cloudx/releases/<version>/cloudx-cloud.pyz` and require its self-check to report the same cloud version
2. reject an alternate artifact path, symlinked or oversized artifact/unit input, non-root or writable install directory, or broadly mutable staged artifact
3. extract the environment, service, and timer from the exact signed artifact rather than the source checkout
4. require the environment to select that exact artifact and reject `/opt/cloudx/current`, mutable home code, network address families beyond `AF_UNIX`, or the wrong timer target
5. require the old service to remain loaded and the old timer to remain loaded, enabled, and active
6. reject a candidate service or timer that is active, enabled, or linked
7. preserve any prior candidate files in a root-only mode-`0700` rollback directory, with mode-`0600` copies and manifest
8. write only the three fixed root-owned mode-`0644` files, run `systemd-analyze verify`, and perform only `systemctl daemon-reload`
9. confirm after reload that the candidate remains disabled/inactive and the old path remains available
10. restore all prior/absent files and reload systemd if any write, verification, reload, or state check fails

The transaction contains no start, enable, stop, disable, output-publication, release-stage, release-activate, release-rollback, or Phi operation. Exact repeated apply is idempotent and performs no file write, backup creation, or daemon reload.

## Contracts And Governance

The plan and receipt are versioned as `cloudx.legacy-health-bridge-unit-plan.v1` and `cloudx.legacy-health-bridge-unit-install.v1`. Receipts expose only release identity, fixed modes, changed-file count, verification/reload booleans, non-activation facts, legacy continuity facts, and the root-only rollback path; they contain no credential, account identity, key, token, request content, or Phi control-plane metadata.

The legacy bridge governance checker now binds these schemas and the installer path, executes the default plan, and rejects it unless the exact artifact is selected, service start and timer enable remain unnecessary, automatic action is false, and every authorization field is false. Runtime acceptance remains false.

## Verification

Focused tests cover the non-authorizing plan, exact confirmation ordering, fixed staged artifact, signed-template validation, mutable-selector rejection, bounded non-symlink snapshots, active legacy prerequisite, inactive/disabled target enforcement, success, idempotence, rollback, secret-free contracts, public metadata, and governance integration. The final `./verify.sh` run passed all 272 tests and built both `cloudx-local-0.1.15.pyz` and `cloudx-cloud-0.1.15.pyz`.

## Decision

The inactive unit-file installation transaction is source-ready. The M4A release-ordering item remains open on the same three production gates: signed artifact publication, bridge unit runtime acceptance, and independently accepted runtime rollback. Any real apply, candidate start, output comparison, Phi N-1 rollback, restoration, or legacy exporter retirement still requires a separate operator-approved maintenance action.
