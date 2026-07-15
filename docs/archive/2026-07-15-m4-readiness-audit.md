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
