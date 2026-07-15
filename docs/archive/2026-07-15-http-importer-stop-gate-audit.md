# HTTP Importer Stop-Gate Audit

## Scope

This is a read-only dependency and traffic audit after the signed `0.1.11` SSH compatibility adapter replaced `/usr/local/bin/codex-gateway-import`. It does not stop, disable, restart, reload, replace, or remove a service, unit, runtime, credential, listener, health file, or rollback path.

## Traffic And Caller Evidence

`codex-import.service` remains enabled and active as PID `133756` with restart count `0`, listening only on the cloud Tailscale address at port `8780`. No established TCP connection to that port was present during the audit.

The importer journal has no entry after the adapter transaction at `2026-07-15 21:34 CST`. Its last request remains a successful `GET /v1/accounts` at `2026-07-15 11:41:25 CST` from the cloud host's own Tailscale address `100.90.97.113`. Earlier `100.119.136.10` requests map to `hirohimacbook-pro` and belong to the prior importer acceptance/replay work; that peer had no current connection.

The active compatibility command has SHA-256 `5830d8228b3bd7b1e46ec3276464dfc441f250da3da990a65c7b5eb3123dd539` and contains no HTTP endpoint, `curl`, token read, or port `8780`. Static inspection found active HTTP references only in the importer unit/drop-in and its Python runtime. Additional references are confined to a disabled import-repair unit, legacy implementation files, and private rollback copies. No cron job targets the importer.

## Systemd Boundary

The importer is wanted by `multi-user.target`. It has no `RequiredBy` unit and no runtime `Requires`, `Wants`, `PartOf`, or `BindsTo` relationship from another service. The legacy `cloudx-health-contract.service` and disabled `codex-import-phi-repair.service` use only `After=codex-import.service` ordering.

The disabled repair timer and service remain inactive with no trigger history and no process. The current `/usr/local/bin/codex-gateway-import` dry-run continued to return accepted `cloudx.import.v1` output without adding an importer journal entry. Production auth remained 15 files, the account archive remained empty, and the failure tree contained no raw `.input` file.

## Remaining Signal Dependency

The legacy health exporter remains enabled on its timer and executes a mutable historical checkout with these inputs:

- importer unit: `codex-import.service`
- legacy output: `/var/lib/cloudx/health/v1.json`
- formal Cloudx output remains separate at `/run/cloudx/health.json`

The legacy document records importer `processState` and currently reports that process as active. `phi-goal-watchdog.service` still declares `After=cloudx-health-contract.service`, requires the legacy file to exist, and reads it through `PHI_CLOUDX_HEALTH_PATH`. The formal `phi-cloudx-health` consumer has migrated to `/run/cloudx/health.json`, but the goal watchdog has not.

The goal watchdog also currently fails for an unrelated read-only Codex database access error. That Phi-owned defect is not caused or repaired by this audit, and it must not be combined with an importer service change.

## Decision

Absence of live HTTP traffic is necessary but not sufficient for retirement. Stopping the importer now would change a still-consumed migration signal and would combine a Cloudx service change with unresolved Phi-owned work. The service therefore remains enabled, active, and listening with its original PID and restart count.

A later stop transaction requires a separate explicit operator decision and must, at minimum:

1. migrate or explicitly retire every consumer of `/var/lib/cloudx/health/v1.json`
2. retain root-only copies of the service, drop-in, runtime hashes, token metadata, failure receipts, status, and journal evidence
3. stop and disable only `codex-import.service`, then prove port `8780` is closed without changing CLIProxyAPI, Tailscale, mihomo, SSH, or firewall policy
4. repeat signed SSH import acceptance, formal `cloudx.health.v1` publication, Phi consumer checks, and gateway/model canaries
5. atomically re-enable and start the preserved unit if any acceptance check fails

Removing `/opt/codex-gateway/codexx_app`, importer keys, unit files, or rollback archives is not part of that future stop transaction and remains independently gated.
