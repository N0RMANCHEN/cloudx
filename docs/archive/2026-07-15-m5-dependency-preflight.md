# M5 Dependency Preflight

## Scope

This was a read-only inventory of the first M5 retirement gate. No local process, tunnel, broker, launchd job, cloud service, timer, credential, auth record, release link, or rollback file was changed.

## Local Evidence

- The official Codex executable remains `/opt/homebrew/bin/codex`.
- Three Codex processes were active during the snapshot. The auditing session itself retained the legacy `api` account environment with `HOME=/Users/BofeiChen/.codex-accounts/api`, so existing-session retirement is not yet safe.
- SSH PID `78601` still owns the legacy `127.0.0.1:18317` listener.
- CLIProxyAPI PID `17165` still owns the local `127.0.0.1:8317` CPA listener and had active local proxy connections.
- No `/Users/BofeiChen/.local/state/cloudx/tunnel/broker.json` existed, so there was no persisted Cloudx broker or lease to retire at the observation point.
- Cloudx local `current` and `previous` still select signed `0.1.7` and `0.1.6` respectively. The active `codexx`, `cloud`, and `cloudx-update` links point through `current`; `codexx-legacy` still points into the private recovery bundle.
- The mode-0700 legacy recovery bundle and mode-0600 shell/native-profile backups remain available outside release directories.
- `.zshrc` sources the Cloudx shell hook, but already-running shells can retain legacy account state and must be allowed to exit naturally before removal.

## Cloud Evidence

- `codex-import.service` remained enabled and active with PID `133756`; no restart was observed.
- `codex-import-phi-repair.timer` remained disabled and inactive. Its lock file exists, but `lslocks` showed no active import or repair lock holder.
- `codex-quota-monitor.timer`, `cloudx-cpa-health.timer`, and `cloudx-health-contract.timer` remained enabled, active, and repeating.
- The active CPA health service still executes `/home/hirohi/workspace/cloudx/deploy/cloudx/cloudx_cpa_health.py` from the mutable codex-plus checkout at commit `0c5a8280788ec99d08e4cdeaf14e7f728a20fb3f`.
- That service delegates quota probing and reversible quarantine to `/opt/codex-gateway/codexx_app`. This compatibility dependency remains required even after its executable moves into a signed Cloudx artifact.
- `phi-roadmap-driver` and `phi-roadmap-watchdog` still declare quota-monitor dependencies, while installed Phi health/goal units still declare ordering against the legacy health-contract service.
- The formal `cloudx-account-state` and `cloudx-health` timers were active and repeatedly publishing alongside the retained legacy contract.
- Cloudx cloud `current` and `previous` still select signed `0.1.7` and `0.1.6`.

## Gate Result

The first M5 checkbox remains open. There are active sessions, listeners, services, and rollback consumers, so no legacy retirement or deletion is safe.

Repository `0.1.8` now prepares the next reversible step: a signed `cpa-health` command plus service/timer templates that remove execution from the mutable checkout while explicitly retaining `/opt/codex-gateway/codexx_app` as a temporary read-only compatibility dependency. Building, testing, committing, or activating the artifact does not install or restart those units; production migration needs a separate operator-confirmed maintenance action.

The temporary `0.1.8` cloud artifact passed `systemd-analyze verify` for both new templates. A manual `cpa-health --check` using the template's proxy environment loaded the installed compatibility runtime and returned only aggregate data: 15 total accounts, 11 available, 4 limited, and 0 failed at that observation point. The public JSON contained no account path, filename, email, or token. The old importer and CLIProxyAPI retained PIDs `133756` and `977036`; the canary did not install a unit or write CPA health state.
