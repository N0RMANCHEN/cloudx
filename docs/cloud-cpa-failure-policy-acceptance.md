# Cloud CPA Failure-Policy Acceptance

This operator runbook accepts the cloud CPA failure and concurrency policy without restarting CPA, Cloudx, Phi, or any local process. It never mutates the local CPA. The transaction is bound to active signed Cloudx `0.1.19`, the already active cloud `.policy.3` producer, and both active cloud watcher paths.

## Safety model

The default command is offline and non-authorizing:

```bash
python3 scripts/accept_cloud_cpa_failure_policy.py
```

Apply requires the exact confirmation below:

```bash
python3 scripts/accept_cloud_cpa_failure_policy.py \
  --apply \
  --confirm 'ACCEPT CLOUD CPA FAILURE POLICY 0.1.19'
```

Before changing the active pool, the transaction:

1. Verifies signed Cloudx `0.1.19`, cloud CPA service identity, policy/watcher readiness, one healthy active credential, an empty failure input, an absent sweep trigger, and the retained 45-entry archive.
2. Copies the active signed cloud `0.1.19` artifact into a private temporary local directory, read-only probes only the local CPA's top-level JSON snapshots through the declared mihomo HTTPS path, and requires three current real weekly-limit samples. It does not change, reload, or restart the local CPA, and removes all temporary snapshots automatically.
3. Runs a real model request through the original active credential and requires policy header `2`.
4. Creates a root-only same-filesystem transaction, copies the independently executable recovery tool into it, writes the exact manual recovery command, and executes its offline self-test.
5. Accepts exactly three distinct bounded credentials over authenticated SSH stdin, holds the cloud import lock, and in isolated private directories proves each real weekly-limit credential is retained, a synthetic refreshable 401 is retained, a synthetic non-refreshable 401 archives exactly one digest-matched credential, and exact restore returns the same bytes.

Only then does it atomically hold the one active credential and install three transaction-owned copies of the real limited samples. Natural `/v1/responses` traffic must produce the aggregate `auth_unavailable` signal. The active watcher must consume the trigger, probe at concurrency at least `3`—independent of the business maximum `2`—and archive zero quota credentials.

The original active credential and prior watcher input are restored in a `finally`-equivalent failure path. Recovery removes or restores only the transaction's fixed canary filenames, restores an accidentally archived canary through the signed exact-restore command, requires the archive to return to 45 entries, requires CPA PID/restart state to remain unchanged, and completes a real post-recovery model request with policy `2`. A final idle maintenance run must report zero probes and an absent trigger.

## Manual recovery

Every transaction contains a mode-`0600` `RECOVERY.md` and a mode-`0700` `recover.py` before active state changes. If output reports `recoveryRequired=true`, log into the cloud host and inspect the newest root-only directory under:

```text
/var/lib/codex-gateway/cpa-policy-acceptance/
```

Run the exact command printed in that transaction's `RECOVERY.md`. Its confirmation is transaction-specific:

```text
RECOVER CLOUD CPA FAILURE POLICY <transaction-id>
```

Do not restart CPA as a recovery shortcut. The recovery tool is idempotent after a completed recovery and verifies useful model traffic itself.

## Regression command

The transaction never uses production paths in tests:

```bash
python3 -m unittest tests.integration.test_cloud_cpa_failure_policy_acceptance -v
```

Repository closeout still requires `./verify.sh`.
