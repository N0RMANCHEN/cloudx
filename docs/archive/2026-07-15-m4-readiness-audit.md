# M4 Readiness Audit

Date: 2026-07-15

This audit is read-only. It did not start, stop, restart, enable, disable, or rewrite a service, release, credential, auth directory, or Phi state.

## Time Gate

M3 activation was accepted on 2026-07-15. The roadmap permits the first Phi consumer migration no earlier than 2026-07-22, after a fresh seven-day stability review. No M4 migration was attempted.

## Formal Cloudx Signal

The active helper returns secret-free `cloudx.health.v1` with Cloudx `0.1.6`, protocol 1, a healthy gateway, a ready importer, fresh aggregate account counts, and no account identities or credentials. The shadow publisher also writes the formal schema to `/run/cloudx-shadow/health.json`, currently from staged Cloudx `0.1.2`.

The installed Phi consumer does not yet read that schema. It reads `/var/lib/cloudx/health/v1.json`, whose top-level identity is `contract: cloudx.health` with `schemaVersion: 1` and producer version `0.7.0`. Although sanitized, this is a legacy migration contract rather than `cloudx.health.v1`.

## Phi Consumer Boundary

`phi-cloudx-health.service` runs as the dedicated `phi-cloudx-health` user. Its unit declares `NoNewPrivileges=true`, `ProtectSystem=strict`, a single Cloudx health file in `ReadOnlyPaths`, and explicit `InaccessiblePaths` for gateway configuration, importer keys, and auth directories. Direct discretionary-access checks confirmed that the service identity can read the legacy health file but cannot read those credential paths.

The service was not run during this audit. Its timer is enabled but reports `active (elapsed)`, `NextElapseUSecMonotonic=infinity`, and no next realtime trigger; its last trigger was 2026-07-15 00:40:05 CST. This must be repaired or replaced in the Phi release window, not by Cloudx.

## Other Observations

- `cloudx-health-contract.timer`, `cloudx-shadow-account-state.timer`, and `cloudx-shadow-health.timer` remain active.
- `phi-goal-watchdog.service` is failed; it is Phi-owned and not a Cloudx availability dependency.
- `phi-roadmap-driver.service` remains active.
- The legacy health exporter still runs from `/home/hirohi/workspace/cloudx`, which is a mutable checkout and cannot be the final M4 contract producer.

## Prepared Source Change

Cloudx `0.1.7` source carries signed-artifact systemd templates for:

- `cloudx-account-state.service` and `.timer`, publishing aggregate state to `/run/cloudx-account-state/accounts.json`
- `cloudx-health.service` and `.timer`, publishing mode-0644 `cloudx.health.v1` to `/run/cloudx/health.json` as the restricted `cloudx` user

The templates deny access to gateway configuration, importer keys, and auth directories. Health inspection no longer creates or writes the importer lock. The artifact exposes each exact template through `cloudx-remote systemd-template <name>`.

Publishing, staging, or activating the artifact does not install or run these units. Installation remains a separate operator-confirmed Cloudx maintenance action before M4.

## Signed Release And Staging

- source commit: `fb4d7e7e4094a90e0edea3e09aeca9802e980f25`
- artifact ref: `release-artifacts/v0.1.7`
- artifact ref SHA: `a78965434a182e1bfb9a1976186b4b6b910f5010`
- stable ref SHA: `1b6f87b5e243f0e7e65feaba3fcafe7beaddc2c6`
- local artifact SHA-256: `19a0861b07b4ab1d0b9d0532965c7914eb62d376468eeff229ec35a977c1322e`
- cloud artifact SHA-256: `1302b83569559125b70ba041a01693cc4624d2983887212d8b1ac6ff76daa60b`

Fresh clones verified the signed manifest and stable index. Both artifacts reported version `0.1.7` and protocol range 1 through 1. The emitted active health template from the published cloud artifact matched the repository template, and `systemd-analyze verify` accepted all four unit files.

Local staging completed first. The initial combined updater attempt then received a transient SSH exit 255 before remote staging; the local `current` and `previous` links remained `0.1.6` and `0.1.5`. Replaying the exact signed offline bundle through `cloudx-remote release-stage` succeeded, and the formal updater retry reported `already-staged` on both endpoints.

After staging:

- local and cloud `current` remain `0.1.6`
- local and cloud `previous` remain `0.1.5`
- `cloudx-account-state.*` and `cloudx-health.*` are absent from `/etc/systemd/system` and have `LoadState=not-found`
- the legacy 18317 listener remains PID `78601`
- the local CPA remains PID `17165`
- cloud CLIProxyAPI remains PID `977036`
- the old cloud importer remains PID `133756`

No service was installed, enabled, started, stopped, restarted, or reloaded. Repository verification passed architecture checks, 92 tests, and deterministic `0.1.7` local/cloud builds before publication.

## Operator-Confirmed Activation

The operator explicitly approved activation of Cloudx `0.1.7` on both endpoints and installation of the active account-state and health units while retaining the old health contract and prohibiting restarts of CLIProxyAPI, the importer, and Phi.

The cloud endpoint was activated first and reported `currentVersion` `0.1.7`, `previousVersion` `0.1.6`, and cloud artifact SHA-256 `1302b83569559125b70ba041a01693cc4624d2983887212d8b1ac6ff76daa60b`. Its handshake added `health-publisher-templates.v1`; direct health reported a healthy gateway, ready importer, and fresh aggregate state.

The local endpoint was then activated without reinstalling the unchanged shell hook. It reports `current` `0.1.7` and `previous` `0.1.6`; official Codex remains `/opt/homebrew/bin/codex`, `codexx` remains a shell function, and the zsh badge remains `[cx:api]`.

## Health Unit Transaction

Before unit installation, the old contract, old unit files, release links, unit states, and key process identities were saved under:

`/var/lib/cloudx/health-service-backups/20260715T075426Z`

The first install transaction exposed two template assumptions. `/etc/cloudx/cloudx-shadow.env` overrode the base unit's output-path environment, and oneshot runtime directories needed explicit preservation. The account adapter therefore wrote only to the existing shadow path and the formal health condition was not met. The transaction automatically disabled the new timers, deleted all four new unit files, reloaded systemd, and left the old contract and all pre-existing services untouched.

The accepted retry installed the exact signed `0.1.7` base units plus two root-owned mode-0644 `10-active-paths.conf` drop-ins. The drop-ins contain no credentials or mutable program content; they override only the signed artifact command's two declared output paths through `/usr/bin/env` and set `RuntimeDirectoryPreserve=yes`. Repository `0.1.8` incorporates both corrections directly into the signed templates and changes first timer scheduling to `OnActiveSec`.

Accepted outputs are:

- `/run/cloudx-account-state/accounts.json`: mode 0644, owner `root:root`, schema `cloudx.account-state.v1`
- `/run/cloudx/health.json`: mode 0644, owner `cloudx:cloudx`, schema `cloudx.health.v1`, Cloudx `0.1.7`

Both new timers are enabled and repeatedly enter `active (waiting)` with one-minute deadlines. Multiple scheduled runs refreshed both files successfully. Health remained `gatewayStatus: healthy`, `importStatus: ready`, and `freshness.state: fresh`.

The `phi-cloudx-health` identity can read `/run/cloudx/health.json` but cannot read `/etc/cliproxy/config.yaml`, the production auth directory, or importer client keys. Its existing unit and elapsed timer were not changed or run.

The old `/var/lib/cloudx/health/v1.json`, `cloudx-health-contract.service`, and `cloudx-health-contract.timer` remain present, enabled, and active as rollback. No old health file or unit was replaced.

## Acceptance Canaries And Continuity

`cloud codex --check` reported the Cloudx remote helper, a healthy independent broker tunnel, and HTTP 200 from the gateway. A complete official Codex request through `codexx cloud` returned exactly `CLOUDX_017_HEALTH_OK`; its broker lease was reclaimed and the final lease count was zero.

The following identities remained unchanged across activation and unit installation:

- legacy local tunnel PID `78601` on `127.0.0.1:18317`
- local CPA PID `17165` on `127.0.0.1:8317`
- cloud CLIProxyAPI PID `977036`
- old cloud importer PID `133756`
- `phi-roadmap-driver` PID `1036613`
- `phi-cloudx-health.timer` last trigger `2026-07-15 00:40:05 CST`, still `active (elapsed)`

No CLIProxyAPI, importer, Phi, Tailscale, SSH, mihomo, or legacy tunnel process was restarted. The only service-manager mutations were a daemon reload plus installation, enablement, starts, and one recovery restart of the two newly created Cloudx timers.
