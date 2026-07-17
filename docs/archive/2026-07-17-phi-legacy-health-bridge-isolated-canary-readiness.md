# Phi Legacy Health Bridge Isolated Canary Readiness

## Scope

This batch adds a signed systemd canary and an exact-confirmation operator transaction for the migration-only Phi N-1 health bridge. It changes repository source, signed templates, contracts, tests, governance evidence, and documentation only. It does not publish or stage `0.1.15`, install a production file, reload production systemd, start any production unit, write either health document, change a selector, stop the old exporter, stop the importer, roll Phi back, or retire a legacy path.

## Current Read-Only Runtime Evidence

The cloud host still selects Cloudx `0.1.13` with `0.1.12` as previous. The exact `/opt/cloudx/releases/0.1.15/cloudx-cloud.pyz` is absent.

The existing `cloudx-health-contract.service` is loaded/static/inactive and still executes the mutable checkout exporter. Its timer is loaded/enabled/active. The new primary service, primary timer, and canary service all report `LoadState=not-found` and `ActiveState=inactive`.

The separate old HTTP importer was also disambiguated during this audit: the real unit is `codex-import.service`, not `codex-gateway-import.service`. It remains loaded/enabled/active/running at PID `133756`, restart count zero, and port `8780` remains listening. No importer or bridge process was changed.

## Signed Canary Boundary

Source `0.1.15` now packages `cloudx-legacy-health-bridge-canary.service`. It selects the same exact artifact through `/etc/cloudx/legacy-health-bridge.env`, reads the same formal `/run/cloudx/health.json`, and retains the primary service's root identity, immutable release/config reads, credential/auth masks, `NoNewPrivileges`, strict system protection, and `AF_UNIX`-only boundary.

The canary differs in one deliberate way: its only writable location is `/run/cloudx-legacy-health-bridge-canary`, and its output is `/run/cloudx-legacy-health-bridge-canary/v1.json`. `/var/lib/cloudx/health` is explicitly inaccessible. It has no `[Install]` section and therefore remains static rather than enableable.

The unit installer now extracts, validates, backs up, and installs four signed files: environment, static canary, primary service, and primary timer. It still performs only `daemon-reload`; every candidate unit must remain inactive, the primary timer disabled, the canary static, and the old timer active/enabled.

## Read-Only Canary Plan

Running:

```text
python3 scripts/run_legacy_health_bridge_canary.py --release-version 0.1.15
```

returned `cloudx.legacy-health-bridge-canary-plan.v1` with the exact confirmation:

```text
RUN cloudx-legacy-health-bridge-canary WITHOUT LEGACY CUTOVER
```

The plan read no artifact, installed unit, systemd state, health file, credential, or selector. `automaticAction=false`, and all eight authorization fields were false.

## Confirmed Apply Contract

Only root apply with that exact confirmation may:

1. require the exact staged cloud artifact and matching self-check
2. require the installed environment and canary unit to be root-owned mode `0644` and byte-identical to that artifact
3. require the old timer active/enabled, the primary bridge inactive/disabled, the canary static/inactive, and no stale canary output
4. start only `cloudx-legacy-health-bridge-canary.service`
5. require `Result=success`, `ExecMainStatus=0`, and the strict bounded legacy contract
6. emit only the public output digest and non-mutation facts
7. delete the temporary file and directory and recheck every unit boundary
8. stop only the canary and remove temporary state if start, validation, cleanup, or boundary checks fail

It contains no primary start, timer enable, old-service stop, old-timer disable, production legacy-output write, release activation, selector change, importer action, or Phi operation.

## Governance And Acceptance

The plan and receipt are versioned as `cloudx.legacy-health-bridge-canary-plan.v1` and `cloudx.legacy-health-bridge-canary.v1`. The bridge governance checker binds the template, runner, schemas, and isolated-output rule; it executes both default operator plans and rejects any authorization bit or production legacy publish path.

The canary is a safer prerequisite for runtime acceptance, not a substitute for it. `runtimeAcceptance.signedArtifactPublished`, `bridgeUnitInstalled`, and `rollbackRehearsed` remain false. The M4A ordering checkbox remains open until a signed artifact is published, the installed primary bridge is accepted, and independent production rollback/restoration evidence exists.

## Verification

Focused tests cover template packaging, immutable selection, production-path masking, non-authorizing planning, exact confirmation ordering, installed-byte matching, stale-output rejection, systemd success, strict legacy validation, success cleanup, failure stop/cleanup, installer rollback/idempotence, contracts, public metadata, and governance integration. The final `./verify.sh` run passed all 282 tests and built both `cloudx-local-0.1.15.pyz` and `cloudx-cloud-0.1.15.pyz`.
