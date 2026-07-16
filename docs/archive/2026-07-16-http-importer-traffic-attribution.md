# HTTP Importer Traffic Attribution

## Scope

This is a read-only follow-up to the Phi goal-watchdog formal-health cutover and the refreshed HTTP importer stop gate. It correlates the five new importer requests with SSH, sudo, systemd, cron, installed-file, reverse-dependency, and live-socket evidence. It did not read or record any key contents, invoke an import, stop or disable a service, reload systemd, change a listener, mutate auth state, or alter rollback evidence.

## Request Correlation

The importer journal recorded five requests from the cloud host's own Tailscale address. Each request aligns within two seconds of a short-lived operator SSH session and an explicit read of the legacy server-admin key file:

| Importer request | Operator SSH session | Legacy compatibility evidence |
|---|---|---|
| `08:36:37 GET /v1/accounts` | opened `08:36:35` | admin-key read at `08:36:36` |
| `08:38:10 POST /v1/imports` | opened `08:38:08` | admin-key read at `08:38:10` |
| `08:38:51 GET /v1/accounts` | opened `08:38:50` | admin-key read at `08:38:51` |
| `08:39:06 POST /v1/imports` | opened `08:39:06` | admin-key read at `08:39:06` |
| `08:39:33 GET /v1/accounts` | opened `08:39:32` | admin-key read at `08:39:33` |

The surrounding systemd window contains ordinary Cloudx and Phi timers but no service whose execution matches or owns the HTTP requests. The cron journal contains only the unrelated system activity collector.

## Installed Caller Audit

A root-readable filename-only scan for port `8780`, `/v1/accounts`, and `/v1/imports` across active systemd units, cron directories, `/usr/local/bin`, and the installed Phi release returned only:

- the `codex-import.service` unit, drop-in, and enablement symlink
- the retained pre-SSH `/usr/local/bin/codex-gateway-import.before-ssh-path-import-20260714` rollback client

The active `/usr/local/bin/codex-gateway-import` remains the signed SSH adapter with SHA-256 `5830d8228b3bd7b1e46ec3276464dfc441f250da3da990a65c7b5eb3123dd539`. The installed Phi goal-watchdog release uses only `/run/cloudx/health.json` and `AF_UNIX` and cannot call the HTTP service.

`systemctl list-dependencies --reverse --all codex-import.service` reports only its enablement through `multi-user.target`; no other service requires it. The legacy health exporter and disabled repair unit retain ordering references only.

## Quiet Recheck

The final importer request remains the `08:39:33 GET /v1/accounts`. At `13:38` CST:

- no later importer journal entry existed
- no established port-`8780` connection existed
- `codex-import.service` retained PID `133756`, restart count `0`, and its original active state
- no timer, cron job, active installed HTTP client, or Phi release reference had appeared
- no import lock holder existed
- production auth contained 45 regular JSON records, the archive contained 0 files, and the two retained failure records contained 0 raw `.input` files
- formal `cloudx.health.v1` remained fresh with `importStatus=ready`

This focused evidence attributes the post-cutover traffic to explicit operator-driven legacy compatibility calls rather than an unattended production caller. It also proves that the observed POST requests had completed and left no active transaction or raw failure input.

## Decision

The traffic-attribution sub-gate is complete. The read-only preflight no longer finds an unowned HTTP caller, and the goal watchdog no longer consumes the legacy importer signal.

This does not authorize a production stop. Retiring `codex-import.service` remains a separate operator-confirmed transaction that must preserve its root-only unit, runtime, token metadata, status, journal, and failure receipts; stop and disable only that service; prove port `8780` closes; repeat signed SSH import, formal health, Phi consumer, gateway, and model canaries; and atomically restore the service if any acceptance check fails. Removing `/opt/codex-gateway/codexx_app`, keys, units, or rollback archives remains independently gated.
