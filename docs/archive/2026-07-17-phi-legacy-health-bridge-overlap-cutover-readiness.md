# Phi Legacy Health Bridge Overlap Cutover Readiness

## Scope

This batch prepares the final Cloudx-owned primary/legacy/primary runtime transaction required by the Phi N-1 compatibility gate. It changes source, contracts, tests, governance evidence, and documentation only. It does not publish or stage `0.1.15`, install a unit, reload systemd, start/stop/enable/disable a production unit, write either health document, change a selector, restart the gateway/importer, mutate Phi, or retire the old exporter.

## Current Runtime Evidence

The read-only cloud audit still reports Cloudx selectors `current=0.1.13` and `previous=0.1.12`; `/opt/cloudx/releases/0.1.15/cloudx-cloud.pyz` is absent. The old `cloudx-health-contract.timer` remains loaded/enabled/active and its static service remains loaded/inactive. The signed canary, primary service, and primary timer remain `not-found` and inactive.

The gateway remains `cliproxy.service` active/running at PID `977036`, restart count zero. The real HTTP importer is `codex-import.service`, loaded/enabled/active/running at PID `133756`, restart count zero. The similarly named `codex-gateway-import.service` is not the production importer. No runtime state changed during this audit.

The current old-exporter document is a strict `cloudx.health`/schema-version-1 document with producer version `0.7.0`, a non-unknown source revision, active gateway/import process evidence, and degraded import evidence. Those facts are distinct from the conservative bridge output, which deliberately reports revision and process/import-runtime facts as unknown.

## Read-Only Plan

Running:

```text
python3 scripts/rehearse_legacy_health_bridge_cutover.py --release-version 0.1.15
```

returned `cloudx.legacy-health-bridge-cutover-plan.v1` with:

```text
confirmation=CUT OVER AND REHEARSE cloudx-legacy-health-bridge WITH ROLLBACK
communicationGapAllowed=false
finalPublisher=signed_primary_bridge
automaticAction=false
```

All eleven authorization fields were false. The plan read no artifact, unit, process, selector, health file, credential, or rollback state.

## Confirmed Five-Phase Transaction

Only root apply with the exact confirmation may execute:

1. `isolated_canary`: require exact signed installed bytes and accept the production-path-masked static canary
2. `candidate_overlap`: enable the primary timer while the old timer remains enabled, start the primary writer, and require the conservative bridge identity
3. `candidate_cutover`: disable the old timer only after the primary timer/writer pass, then revalidate the primary output
4. `legacy_rollback`: re-enable and validate the old timer/writer before disabling the primary timer, then revalidate the distinguishable old producer
5. `candidate_restoration`: re-enable and validate the primary timer/writer before disabling the old timer, then finish on the signed primary output

Every timer disable is guarded by an already enabled/active target timer and a successful target writer. The transaction never intentionally enters a state where both publishers are inactive.

Before the first production-path transition it records the exact current/previous selector versions, gateway/importer PID and restart counters, and a root-only mode-`0600` copy of the public legacy document plus manifest under `/var/lib/cloudx/legacy-health-bridge-cutover-backups`.

Success requires the exact current/previous selector versions, gateway state, and importer state to remain identical. The receipt contains only phase names/statuses/public output digests, continuity booleans, final timer state, and the root-only backup path. It contains no credential, account identity, request content, or Phi control-plane metadata.

## Failure Recovery

Any candidate, output, timer, selector, or process-continuity failure first re-enables the old timer. It validates the old writer before disabling the primary; if the old writer cannot refresh, it restores the pre-cutover public document and leaves the primary available rather than deliberately disabling both paths. It reports recovery incomplete if old timer/writer/output recovery, selector continuity, or gateway/importer continuity cannot be proven.

The transaction has no release-stage/activate/rollback command, gateway/importer restart, credential write, or Phi operation. The old static service and root-only backup remain available after success.

## Governance And Remaining Gate

The plan and receipt are versioned as `cloudx.legacy-health-bridge-cutover-plan.v1` and `cloudx.legacy-health-bridge-cutover.v1`. The bridge governance checker binds the runner and schemas, executes its default plan, requires the exact five phases, `communicationGapAllowed=false`, the signed-primary final publisher, and every authorization field false.

This is source readiness only. `signedArtifactPublished`, `bridgeUnitInstalled`, and `rollbackRehearsed` remain false, and the M4A ordering checkbox remains open until the exact signed publication plus separately approved production install/canary/cutover transaction actually pass.

## Verification

Focused tests cover non-authorizing planning, exact confirmation, fixed artifact selection, five-phase order, overlap before every disable, candidate/old producer distinction, isolated canary prerequisite, final primary state, failure recovery, external selector fail-closed behavior, continuity receipts, contract secrecy, and governance integration. The final `./verify.sh` run passed all 291 tests and built both `cloudx-local-0.1.15.pyz` and `cloudx-cloud-0.1.15.pyz`.
