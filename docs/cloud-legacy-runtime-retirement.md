# Cloud Legacy Runtime Retirement Runbook

This runbook quarantines only `/opt/codex-gateway/codexx_app`, the dormant codex-plus Python package left behind after native Cloudx health and SSH import acceptance. The transaction never starts, stops, restarts, enables, disables, or reloads a service; it never changes the gateway, CPA, Phi, a credential, a release selector, or the retained HTTP-importer rollback archive.

## Required Baseline

- Signed cloud Cloudx `0.1.21` is current and `0.1.20` is previous.
- `cliproxy.service` is active and healthy.
- The signed `cloudx-legacy-health-bridge.timer` and Phi formal-health timer are active; the old mutable exporter timer is disabled.
- `codex-import.service`, its Phi repair timer, and the DeepSeek quota-monitor timer remain inactive/disabled as declared.
- No process, systemd unit outside the declared dormant set, or cron entry references `codexx_app` or its five dependent legacy source files.
- `/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z` passes its complete SHA-256 manifest and its runtime archive still contains the full `codexx_app` tree.

Any difference is a blocker. Do not edit a unit or restore/start an old service to make the check pass.

## Prepare A Root-Only Operator Bundle

Use a clean pushed commit. Extract the exact committed script outside the checkout, verify its SHA-256 against `git show`, transfer it without credentials, and install it on the cloud host under a unique root-only directory such as:

```text
/var/lib/cloudx/operator-bundles/<commit>-cloud-m5/
```

The directory and script must be root-owned mode `0700`. The bundle contains code only; do not copy auth files, gateway keys, logs, account state, or release credentials into it.

## Plan And Decision

The default plan is offline and non-authorizing:

```bash
sudo /usr/bin/python3 ./quarantine_cloud_legacy_runtime.py \
  --release-version 0.1.21
```

Obtain a fresh root-level decision and record its digest plus aggregate counts:

```bash
sudo /usr/bin/python3 ./quarantine_cloud_legacy_runtime.py \
  --check \
  --release-version 0.1.21
```

The decision must report zero live process references, zero scheduled references, five dependent source files, three declared reference units, a verified importer rollback snapshot, the full runtime present in that archive, healthy gateway/compatibility canaries, and `serviceRestartRequired=false`.

## Apply

Use only the unchanged fresh digest:

```bash
sudo /usr/bin/python3 ./quarantine_cloud_legacy_runtime.py \
  --apply \
  --confirm "QUARANTINE DORMANT CLOUD CODEXX APP RUNTIME WITH AUTOMATIC RESTORE" \
  --decision-digest '<fresh-decision-digest>' \
  --release-version 0.1.21
```

Before the same-filesystem move, the transaction takes a root lock and repeats the complete decision. It writes a private manifest, executable `recover.py`, and `RECOVERY.md` first. After the move it rehashes the quarantined tree and repeats signed self-check, gateway PID/restart count, release selectors, public health/handshake, dependent unit state, bridge/Phi timer state, and the existing importer rollback archive. Any failure restores the original path automatically and repeats continuity checks.

Acceptance requires `runtimeLive=false`, `runtimeDeleted=false`, `serviceRestarted=false`, `daemonReloaded=false`, `credentialMutation=false`, `phiServiceRestarted=false`, unchanged gateway PID/selectors, and a retained quarantine ID.

## Recovery

The receipt's `backupId` identifies:

```text
/var/lib/cloudx/legacy-runtime-quarantine/<backupId>/
```

Verify the exact tree without moving it:

```bash
sudo ./recover.py --check
```

Restore code only with:

```bash
sudo ./recover.py \
  --confirm "RESTORE QUARANTINED CLOUD CODEXX APP RUNTIME"
```

Recovery performs one same-filesystem rename and no service action. Restoring the package does not authorize re-enabling the HTTP importer, repair timer, quota monitor, or old health exporter. Each remains behind its own rollback and operator confirmation.

## Closeout Evidence

Record only the source commit and script digest, decision digest, aggregate file/byte/tree digests, declared unit counts/states, gateway PID/restart count, current/previous versions, backup ID, recovery check, public canary outcomes, and unchanged local communication. Do not record credentials, account identities, raw logs, request bodies, or private gateway configuration.
