# Cloud CPA Policy.4 Activation

Date: 2026-07-19

## Decision And Boundary

The standing operator authorization accepted:

```text
ACTIVATE CLOUD CPA POLICY 7.2.71-cloudx-policy.4 3e3ed137ff90
```

This authorized one recovery-bounded restart of cloud `cliproxy.service`. It did not authorize local CPA restart, credential/archive mutation, watcher changes, Cloudx selector movement, importer restart, Phi mutation, or legacy retirement.

## Recovery Before Restart

Root-only job `/var/lib/cloudx/cpa-policy-activation-jobs/20260719T085449Z-fda9a073` was prepared first with:

- exact active `.policy.3` gateway and health drop-in snapshots;
- mode-`0700` `recover.sh` plus mode-`0600` manual;
- snapshot and recovery-tool digest binding;
- an exact confirmation that restores `.policy.3`, reloads systemd, restarts only CPA, and requires old ExecStart, health, and policy `2`.

Its `--check` passed snapshot/tool digests, exact `.policy.3` SHA-256, active ExecStart, health, and policy `2` without a restart.

## Activation And Acceptance

The canonical signed-`0.1.20` installer retained automatic rollback backup `1784451450447783787-cloud`, atomically replaced only the two CPA policy drop-ins, ran `daemon-reload`, and restarted only `cliproxy.service`.

- active binary `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.4/cli-proxy-api`
- SHA-256 `3e3ed137ff90132203f2b0e969245b6580b3ff2b780e2f3a47b821642fd6fdc4`
- previous PID `1613475`; active PID `1693505`; restart count `0`
- health accepted; invalid-client canary returned HTTP `401` and public policy `2`
- authenticated real model canary returned HTTP `200`, exact expected text, and policy `2`
- importer PID `133756`, Cloudx `0.1.20/0.1.19`, one active credential, 45 archive entries, watcher paths, and empty failure/trigger inputs unchanged
- real official-Codex-through-local-CPA traffic passed before and after activation

## Next Gate

Repeat the rollback-bounded cloud M4B transaction. Natural weekly-limited traffic must now converge to upstream `model_cooldown`, emit the stable identity-free incident trigger, drive a sweep at concurrency at least three, archive zero quota credentials, and restore the one useful account. Local `.policy.4` remains staged/inactive until its independent five-sample zero-connection gate passes.
