# Local CPA Activation And Recovery Manual

This manual applies only to an explicitly confirmed future local CPA policy activation. It does not authorize an activation, restart, launcher edit, account mutation, watcher change, or recovery action by itself.

## Safety Contract

Before Cloudx may stop the shared local CPA, all of the following must be true:

1. Signed Cloudx `0.1.18` is active locally.
2. The exact `.policy.3` candidate remains staged with its pinned digest.
3. The scheduler has created a private activation job containing the installer, recovery tool, pinned deployment contract, original launcher snapshot, job manifest, and `RECOVERY.txt`.
4. Every copied file and the original baseline binary matches the digest in the private job manifest.
5. A real official-Codex request succeeds through the baseline CPA.
6. Five consecutive connection audits report zero established port-`8317` socket rows.

If any connection remains, activation stops before editing the launcher or calling `launchctl bootout`. Cloudx never terminates a Codex process to manufacture quiescence.

The prior `20260718T151333Z-7d40e597` job is failed historical evidence. It predates this recovery contract and must not be reused.

## Prepare A Future Activation Job

Inspect the plan first:

```bash
python3 scripts/schedule_local_cpa_policy_activation.py
```

The plan must report:

- `requiredActiveCloudxVersion=0.1.18`
- `requiresZeroEstablishedConnections=true`
- `manualRecoveryPreparedBeforeRestart=true`
- `automaticRecoveryUsesManualTool=true`
- `failureStageReceipt=true`

Only after a separate exact activation confirmation may the scheduler create a job. Its result prints the exact job ID, receipt, log, recovery plan, and recovery argument vector. Save that output outside the CPA-backed conversation before the deferred worker begins.

Each job directory is mode `0700`. `job.json`, `launcher.before`, the copied tools, `RECOVERY.txt`, logs, and receipts are mode `0600`. The original baseline executable remains outside the job and is verified by SHA-256 before every recovery.

## Recover The Baseline

Use the exact job path printed by the scheduler. Do not guess a job or use the historical failed job.

First inspect without changing service state:

```bash
python3 <job>/recover_local_cpa_policy.py --job <job>
```

Then open `<job>/RECOVERY.txt` and copy its exact apply command. The command has this form:

```bash
python3 <job>/recover_local_cpa_policy.py \
  --apply \
  --job <job> \
  --confirm 'RESTORE LOCAL CPA BASELINE <job-id> <launcher-sha-prefix>'
```

The recovery tool is idempotent:

- If the exact baseline launcher is already loaded, `/healthz` succeeds, and a real official-Codex request succeeds, it returns `already-recovered` without rewriting the launcher or restarting CPA.
- If CPA is offline or the candidate is loaded, it atomically restores the pinned original launcher, waits until launchd is fully unloaded for three consecutive observations, retries baseline bootstrap, then requires health and real Codex communication.
- Automatic rollback invokes this same job-local command. There is no separate weaker rollback implementation.
- The tool never stops a Codex, Codex App, terminal, workspace, or project process.

Successful output is `recovered` or `already-recovered`. The mode-`0600` `<job>/recovery-receipt.json` is the source of truth.

## Independent Verification

After recovery, verify the exact baseline without changing it:

```bash
launchctl print gui/$(id -u)/com.codexx.cliproxyapi
lsof -nP -iTCP:8317 -sTCP:LISTEN
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8317/healthz
```

The launchd output must select the baseline path recorded in `job.json`; the listener must be owned by that process; health must return `{"status":"ok"}`.

The recovery tool already runs the pinned official-Codex canary with the dedicated `api` profile. If an operator independently repeats it, use the official binary and exact private profile, and expect only `LOCAL_CPA_POLICY_COMMUNICATION_OK`:

```bash
HOME="$HOME" \
CODEX_HOME="$HOME/.codex-accounts/api/.codex" \
/opt/homebrew/bin/codex exec --skip-git-repo-check \
  'Reply with exactly LOCAL_CPA_POLICY_COMMUNICATION_OK'
```

## Failure Codes

- `connections_present`: no service or launcher change occurred. Finish or close CPA-backed requests, verify zero connections, and create a new separately confirmed job; do not kill Codex processes.
- `unload_timeout`: launchd never proved the old generation absent. Inspect the current PID, listener, and health before doing anything else; do not issue repeated blind `bootout` commands.
- `bootstrap_failed`: the launcher snapshot is restored but launchd did not load it. Re-run the exact recovery command; it retries bootstrap and is safe when the service is already healthy.
- `health_failed`: a baseline process may be loaded but health was not accepted. Inspect `launchctl print`, the listener, and the CPA log before retrying.
- `communication_failed`: baseline health may already be available, but the real Codex path was not accepted. Read `serviceAvailable` and `healthCanary` in the recovery receipt before assuming CPA is offline.
- `snapshot_changed`, `tool_changed`, `baseline_changed`, `launcher_unsafe`, or `job_unsafe`: stop. Do not mutate launchd or the launcher; the recovery trust boundary no longer matches.

The worker log contains only job ID, enumerated stage, and aggregate status. It never records credentials, account filenames, tokens, prompts, or model responses. The activation receipt separately reports the activation failure code, recovery status, service availability, and recovery-plan path.

## Manual Stop Condition

If the exact recovery tool and its second invocation both fail, stop automated work. Preserve the job directory, launcher snapshot, receipts, CPA logs, and current process state. Do not repeatedly unload the service, delete the job, edit account files, or substitute another CPA binary. Recovery then requires a new operator decision based on those retained artifacts.
