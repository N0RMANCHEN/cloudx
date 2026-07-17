# BofeiChen Legacy Local Removal Readiness

Date: 2026-07-17

This batch prepares a quarantine-first transaction for the live local codex-plus package on `/Users/BofeiChen`. It does not run the transaction. No selector, shell file, entrypoint, package, account, credential, external CPA state, process, listener, service, or recovery file was changed by the readiness audit.

## Read-Only Endpoint Evidence

- Cloudx `current` resolves to `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.8`.
- Cloudx `previous` resolves to `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.7`.
- `codexx`, `cloud`, and `cloudx-update` remain symlinks to the active Cloudx artifact.
- `.zshrc` contains exactly one marked Cloudx hook at lines 213 through 215 and no marked legacy codexx hook.
- The live legacy targets remain present: `.local/bin/codexx_app`, `.local/bin/codexx.py`, and the `.local/bin/codexx-legacy` symlink.
- `codexx-legacy` resolves to backup `20260715T050707Z/home/.local/bin/codexx` under the Cloudx private recovery root.
- The recovery bundle directory is mode `0700`; its `cloudx.legacy-local-backup.v1` manifest is mode `0600` and contains 169 file records.
- A process inventory constructed without the live path literals found zero independent codex-plus runtime/launcher processes.
- The one external local CPA remains PID `17165`, started 2026-07-13 18:21:28 local time, and listens on `127.0.0.1:8317`.
- No process listens on local port `18317`.

## Prepared Transaction

The default command is read-only and offline:

```text
python3 scripts/remove_legacy_local_package.py --release-version 0.1.15
```

It emits `cloudx.legacy-local-removal-plan.v1` with `status=confirmation-required`, `automaticAction=false`, and every authorization field false. The exact confirmation is:

```text
QUARANTINE LOCAL CODEX-PLUS PACKAGE WITH AUTOMATIC RESTORE
```

Confirmed apply is intentionally fail-closed. Before any move it requires:

1. exact active `0.1.15` local artifact self-check and stable current/previous selectors;
2. one Cloudx shell hook, no old hook, and unchanged Cloudx entrypoint symlinks;
3. no legacy process, closed port `18317`, and one stable external CPA on port `8317`;
4. a bounded real-directory runtime with no symlink, special, oversized, or over-count input;
5. live launcher/runtime hashes matching the private recovery manifest;
6. Cloudx-native local import dry-run and fresh-shell native/API/exit acceptance.

Only the three live legacy targets are moved, by same-filesystem atomic rename, into a mode-`0700` timestamped directory under `~/.local/state/cloudx/legacy-removal-backups`. The transaction retains a mode-`0600` aggregate manifest and does not copy raw credential data into its receipt.

After the move it repeats the fresh-shell and native-import canaries, exact selector and shell/entrypoint comparison, and external CPA process/listener comparison. A partial move is restored immediately. Any later failure restores all moved paths, audits selector/shell/CPA continuity, removes an empty failed quarantine only after successful restoration, and returns nonzero. It never terminates a process, restarts a service, writes an account, edits `.zshrc`, changes a Cloudx selector, or removes the original recovery bundle.

## Current Blocker

The endpoint is still active on `0.1.8/0.1.7`, not source `0.1.15`. Therefore the exact active-release precondition is not satisfied and real apply was not attempted. Signed publication, staging, activation, real native import acceptance, rollback acceptance, and a separate operator decision remain required before quarantine. Permanent deletion of the retained quarantine and recovery bundle remains outside this transaction and the broad M5 removal checkbox stays open.
