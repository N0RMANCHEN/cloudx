# Legacy Bridge Retirement Readiness

Date: 2026-07-23

This is a read-only readiness audit for the sole remaining Roadmap item. It does not authorize a release, timer change, service action, file removal, selector change, or Phi mutation.

## Current/N-1 Contract

The committed `cloudx.phi-release-ordering-evidence.v1` matrix still records:

- Cloudx current and previous publish `schema=cloudx.health.v1`;
- Phi current consumes `schema=cloudx.health.v1` directly;
- Phi previous consumes the legacy `contract=cloudx.health;schemaVersion=1` shape.

The strict evaluator therefore selects `healthPath=legacy_bridge` for `Cloudx current × Phi previous`. Integration coverage requires that bridged pair to remain compatible and requires the bridge evidence to remain `runtime-accepted`. The default verifier currently reports both `legacy-health-bridge: runtime-accepted (0 blockers)` and `release-ordering: compatible (0 blockers)`. Removing the bridge while this matrix remains authoritative would make at least the Phi rollback/current-Cloudx pair incompatible.

## Production Confirmation

Production independently matches the committed contract:

- Cloudx selects signed `0.1.29/0.1.28` with current artifact SHA-256 `272ce07da46da5f3d6c9e52dd108a2517bec4eadab3f0547324f6631413e8aa5`.
- `cloudx-legacy-health-bridge.timer` is enabled, active, and waiting; its latest service result is successful with exit status `0`.
- `phi-cloudx-health.timer` is enabled, active, and waiting; its latest consumer service result is successful with exit status `0`.
- Formal health continues at `/run/cloudx/health.json`; the signed compatibility publication continues at `/var/lib/cloudx/health/v1.json` and was refreshed by the active bridge timer.

The audit changed none of these states.

## Missing Preconditions

Retirement is not ready because both mandatory preconditions are absent:

1. Current/N-1 compatibility still requires the bridge. Phi N-1 has not been replaced by an accepted release that natively consumes `cloudx.health.v1`, and no fresh four-pair matrix proves every Cloudx-first, Phi-first, and independent rollback order with direct health only.
2. No separate signed rollback acceptance has approved bridge removal. The retained primary/old-exporter backups and prior cutover rehearsal prove recovery capability for the installed bridge; they are not approval to retire it.

## Re-entry Gate

Re-open this Roadmap item only when all of the following evidence exists:

- immutable Phi current and N-1 refs both declare and pass native `cloudx.health.v1` consumption;
- the refreshed four-pair release-ordering matrix reports every pair and every upgrade/rollback order compatible with `healthPath=direct` and no bridge fallback;
- a new signed Cloudx release contains a default-offline retirement transaction with exact unit/artifact/state binding, overlap-safe rollback to the current bridge, and no authority over gateway, importer, CPA, credentials, selectors, or Phi;
- an operator separately approves the exact retirement and rollback acceptance.

Until then, keeping the bridge active is the required safe state, not unfinished M5 work.
