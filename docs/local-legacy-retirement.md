# Local Legacy Retirement Runbook

This runbook retires the remaining local codex-plus runtime without stopping, restarting, rebinding, or reconfiguring the external local CPA on port `8317`. It uses three separately confirmed transactions in a fixed order. None may run from a Git checkout; copy the exact committed scripts into a private immutable operator bundle first.

## Safety Boundary

- The stale-exec transaction may send `SIGTERM` only to digest-bound, PPID-1 `codexx.py exec` groups that are at least thirty days old, have revoked standard I/O, have no network socket, contain exactly one official Codex child, and remain CPU-bound across repeated samples. It never sends `SIGKILL`, writes a file, or restarts a service.
- The control migration may restart only `com.codexx.control` on port `8765` after five zero-connection samples and a thirty-day state-idle check. It prepares retained and live-runtime recovery plists plus an executable recovery script before the restart. It never touches CPA, Codex sessions, accounts, or Cloudx selectors.
- The package transaction may move only `codexx_app`, `codexx.py`, and `codexx-legacy` into same-filesystem private quarantine after all live references are gone. It prepares a standalone restore script before the first move and automatically restores partial moves or failed acceptance.

Stop immediately if the CPA PID changes, port `8317` becomes unavailable, a target decision digest changes, port `8765` has an active connection, or any script reports a different target set.

## Prepare An Immutable Operator Bundle

From a clean, pushed commit, create a user-private bundle outside the checkout:

```bash
commit="$(git rev-parse HEAD)"
bundle="$HOME/.local/state/cloudx/operator-bundles/$commit-local-m5"
umask 077
mkdir -p "$bundle"
git archive "$commit" \
  scripts/retire_stale_local_codexx_exec.py \
  scripts/migrate_legacy_local_control.py \
  scripts/remove_legacy_local_package.py |
  tar -x -C "$bundle" --strip-components=1
chmod 700 "$bundle" "$bundle"/*.py
git diff --quiet && git diff --cached --quiet
```

Record the commit and SHA-256 of all three copied scripts. Do not place account data, API keys, auth files, or runtime logs in this bundle.

Capture the baseline without reading credentials:

```bash
pgrep -f "$HOME/.local/bin/cli-proxy-api"
lsof -nP -iTCP:8317 -sTCP:LISTEN
lsof -nP -iTCP:8765
```

Run one official-Codex-through-CPA canary before the first transaction and after the final transaction. Use a fresh temporary working directory, source the Cloudx hook, select `api`, and require one exact short response. This verifies communication; it grants no CPA lifecycle authority.

## 1. Retire Proven-Stale Exec Groups

The default plan is offline and non-authorizing:

```bash
python3 "$bundle/retire_stale_local_codexx_exec.py"
```

Inspect the live decision and record its `decisionDigest`, `targetPids`, `childPids`, and `localCpaPid`:

```bash
python3 "$bundle/retire_stale_local_codexx_exec.py" --check
```

Apply only with that unchanged digest:

```bash
python3 "$bundle/retire_stale_local_codexx_exec.py" \
  --apply \
  --confirm "RETIRE STALE ORPHANED LOCAL CODEXX EXEC PROCESSES" \
  --decision-digest '<fresh-decision-digest>'
```

Acceptance requires the exact parent and child PIDs absent, the control service still listening on `8765`, the original CPA PID still listening on `8317`, `signal=SIGTERM`, `sigkillSent=false`, and `serviceRestarted=false`. A group that does not exit after `SIGTERM` remains an explicit manual blocker; do not escalate automatically.

## 2. Move The Idle Control Service To Retained Runtime

Print the non-authorizing plan, then obtain a fresh decision:

```bash
python3 "$bundle/migrate_legacy_local_control.py" --release-version 0.1.21
python3 "$bundle/migrate_legacy_local_control.py" --check --release-version 0.1.21
```

Apply only with the fresh digest:

```bash
python3 "$bundle/migrate_legacy_local_control.py" \
  --apply \
  --confirm "MIGRATE IDLE LOCAL CODEXX CONTROL TO RETAINED RECOVERY RUNTIME" \
  --decision-digest '<fresh-decision-digest>' \
  --release-version 0.1.21
```

The expected interruption is limited to the otherwise idle legacy control listener on port `8765`; CPA remains continuously available. Acceptance requires HTTP authentication canary `401`, zero active connections, a new control PID using the retained recovery runtime, unchanged CPA PID/port, and a private `rollbackBackupId`.

Locate the matching directory under `~/.local/state/cloudx/legacy-control-migration-backups/` and verify recovery before continuing:

```bash
./recover.py --check --mode retained
./recover.py --check --mode live
```

Before package quarantine, either recovery mode is available. After package quarantine, only retained mode is expected to remain available. To restore the live mode later, restore the quarantined package first, then run:

```bash
./recover.py --mode live \
  --confirm "RECOVER LOCAL CODEXX CONTROL FROM RETAINED BACKUP"
```

## 3. Quarantine The Live Legacy Package

Inspect the offline plan:

```bash
python3 "$bundle/remove_legacy_local_package.py" --release-version 0.1.21
```

Apply only after the first two acceptance gates pass:

```bash
python3 "$bundle/remove_legacy_local_package.py" \
  --apply \
  --confirm "QUARANTINE LOCAL CODEX-PLUS PACKAGE WITH AUTOMATIC RESTORE" \
  --release-version 0.1.21
```

Acceptance requires exactly three targets quarantined, native import and fresh-shell checks accepted, official Codex/Git and Cloudx entrypoints unchanged, the external CPA unchanged, no process termination, and no service restart. The receipt's `backupId` identifies the private quarantine under `~/.local/state/cloudx/legacy-removal-backups/`.

Verify the manual restore tool:

```bash
./recover.py --check
```

Restore only with the exact confirmation:

```bash
./recover.py --confirm "RESTORE QUARANTINED LOCAL CODEX-PLUS PACKAGE"
```

This restores files only. It does not restart CPA, Codex, the legacy control service, or Cloudx. To return completely to the former live control path, restore the package first and then use the control backup's `--mode live` recovery command.

## Closeout Evidence

Record only secret-free evidence: source commit, script digests, decision digests, old/new process IDs, listener states, recovery backup IDs, transaction receipts, active Cloudx selectors, and canary outcomes. Do not record process command lines containing user paths, auth filenames, account identities, request bodies, or credentials.
