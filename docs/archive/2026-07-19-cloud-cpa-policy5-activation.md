# Cloud CPA policy.5 activation

Date: 2026-07-19

## Boundary

The exact activation confirmation was exercised only after signed Cloudx `0.1.21` was active, the exact candidate was staged, comprehensive endpoint state passed, and an independently executable policy4 recovery had passed a no-restart check with health, policy `2`, and real model traffic:

```text
ACTIVATE CLOUD CPA POLICY 7.2.71-cloudx-policy.5 5f83b1821d2b
```

This authorized one restart of `cliproxy.service` per bounded attempt. It did not authorize importer/Cloudx/local/Phi restart, credential/archive mutation, watcher change, local CPA activation, or legacy retirement.

## Recovery-Bounded Hardening Attempts

Two activation attempts selected the correct policy5 bytes and passed the canonical health/policy canary, but the independent acceptance deliberately rejected an overbroad auth-state invariant and automatically restored policy4:

1. Job `20260719T101124Z-114ddf79` selected policy5 as PID `1717536`, then rejected because the real restart/canary atomically refreshed one auth file's content. Recovery restored exact policy4 as PID `1717622` and passed real HTTP `200` model traffic with policy `2`.
2. Job `20260719T101919Z-78683e87` selected policy5 as PID `1718363`, then rejected because the private auth-layout digest still included CPA runtime cache/temporary entries rebuilt during restart. Recovery restored exact policy4 as PID `1718450` and again passed real HTTP `200` model traffic with policy `2`.

Both automatic recoveries restored the exact policy4 drop-ins and service selection, retained restart count `0`, one top-level active credential, the 45-entry archive manifest, empty failure input, absent trigger, active watchers, importer PID `133756`, Cloudx `0.1.21/0.1.20`, local CPA PID `61859`, and working local communication.

The accepted third job narrowed the auth invariant to the authoritative top-level regular `*.json` set: exact count `1`, private name-layout digest, owner/group/mode, and JSON-object validity. Archive remains full-byte bound; failure/trigger, watcher/unit, importer, prerequisite, and Cloudx-selector invariants remain exact. CPA may atomically refresh the existing credential's token content, which is runtime behavior rather than archive or account-set mutation.

## Accepted Activation

Root-only job `20260719T102318Z-ff41e660` captured active policy4 PID `1718450`, both exact drop-ins, the staged policy5 identity, authoritative credential layout, full archive/failure state, trigger absence, watcher/unit/prerequisite state, importer identity, and Cloudx selectors. Its recovery `--check` passed without restart and the final baseline was recaptured after the real canary.

The canonical installer retained backup `1784456709015161519-cloud`, restarted only `cliproxy.service`, and selected:

```text
/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.5/cli-proxy-api
SHA-256=5f83b1821d2be7cf5b7615973e4e6130d477386e16eae3a50af46e99bf7af7f8
PID=1719083
NRestarts=0
```

Independent acceptance verified exact ExecStart and digest, health, invalid-client policy header `2`, one-attempt real `codex-auto-review` HTTP `200` traffic with policy `2`, authoritative top-level active count `1`, archive manifest count `45`, zero failure inputs, absent trigger, active failure/sweep/health watchers, unchanged importer PID `133756`, and unchanged Cloudx `0.1.21/0.1.20`. Local CPA remained PID `61859`; all six long-lived Codex PIDs survived and a post-activation real official-Codex-through-local-CPA canary passed.

Manual recovery remains independently executable:

```text
sudo /var/lib/cloudx/cpa-policy-activation-jobs/20260719T102318Z-ff41e660/recover.sh 'RECOVER CLOUD CPA POLICY5 TO POLICY4 20260719T102318Z-ff41e660'
```

It restores exact policy4 only when required, avoids a redundant restart if policy4 is already healthy, and requires health, public policy `2`, and real authenticated model traffic.

## Next Gate

Run the rollback-bounded M4B production acceptance against natural all-candidate cooldown. Local policy5 remains staged/inactive and must not be activated while any established local CPA connection remains.
