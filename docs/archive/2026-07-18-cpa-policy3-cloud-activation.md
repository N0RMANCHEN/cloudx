# CPA Policy 3 Cloud Activation

Date: 2026-07-18

## Decision And Boundary

After the first authorized attempt safely rolled back and the readiness correction passed repository verification plus CI, the operator repeated the exact confirmation:

```text
ACTIVATE CLOUD CPA POLICY 7.2.71-cloudx-policy.3 453df72d1523
```

This authorized selection of the exact staged cloud candidate and one controlled restart of `cliproxy.service`, with automatic baseline restoration if any canary failed. It did not authorize local CPA activation, watcher activation, credential import/archive mutation, Cloudx selector changes, Phi changes, or legacy removal.

## Source And Preflight

The transaction used the exact pushed source commit `5be021206cbb9a04d7de1156fdf43873d1db567f`, whose readiness correction passed 394 repository tests and push CI run `29648642276`.

- Cloudx selectors: `current=0.1.17`, `previous=0.1.16`
- starting CPA: baseline PID `1612019`, active/running, restart count `0`
- baseline SHA-256: `1d0abbc6316b1869f74896109c0efb5e19c8197b8226f48a74212ed0a6f5a39d`
- staged candidate SHA-256: `453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b`
- staged candidate size/owner/mode: `45322402`, root/root, `0755`
- policy drop-ins and private failure/sweep directories: absent
- active auth files: zero
- established port-`8317` connections: zero
- Cloudx handshake: product `0.1.17`, gateway healthy at `7.2.71`
- local CPA: PID `38189`; all six captured Codex processes alive

Only the exact installer and deployment contract bytes from the clean pushed commit were copied to a mode-private temporary cloud directory. Their SHA-256 values were verified before execution, bytecode writes were disabled, and the temporary directory was removed after the transaction.

## Activation Result

The installer returned:

```json
{"backupName":"1784386207038953866-cloud","externalServiceManaged":false,"httpStatus":401,"operatorApprovedRestart":true,"pid":1613475,"policy":"2","schema":"cloudx.cliproxy-policy-deployment.v1","status":"active","target":"cloud","version":"7.2.71-cloudx-policy.3"}
```

Independent post-activation acceptance established:

- `cliproxy.service` is active/running as PID `1613475`, restart count `0`, result `success`
- `ExecStart` and `/proc/1613475/exe` both select `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.3/cli-proxy-api`
- live process SHA-256 is the exact candidate digest
- `/healthz` returns HTTP `200` with status `ok`
- an invalid-auth `/v1/responses` policy canary returns HTTP `401` and `X-CPA-Max-Concurrent-API-Requests: 2`
- gateway drop-in SHA-256 `bce547229d548559ab908f17cddd5e9a7f4fa450cdb9c034333f221d1ee5fc5c` matches generated source bytes
- CPA-health drop-in SHA-256 `57f34ca6cc74665d6e6c778f0ebc3f7a127740b332def91bd1aaf55a39daabfd` matches generated source bytes
- both drop-ins are root/root mode `0644`
- failure and sweep directories are `cliproxy:cliproxy`, mode `0700`, and initially empty
- the root-only mode-`0600` rollback manifest records that both prior drop-ins were absent
- the retained baseline binary is unchanged
- active auth remains empty
- the reversible archive remains schema `cloudx.cpa-quarantine.v1`, mode `0700`, with 45 manifest entries and 45 mode-`0600` credential files
- Cloudx remains `0.1.17/0.1.16` and handshake still reports the gateway healthy
- the existing natural `cloudx-cpa-health` timer ran successfully at `22:52:24 CST` with its unchanged pre-watcher command; formal health remained fresh/healthy with zero accounts, and capacity truthfully reported `exhausted_capacity`
- the natural health run created no failure or sweep entry and all four watcher units remained absent
- local CPA remains PID `38189`, local health is `ok`, and all six captured Codex processes remain alive
- no activation temporary directory remains locally or remotely

The external service restarted only once during this successful transaction. `NRestarts=0` is expected because this was an operator-requested systemd restart, not crash recovery.

## Remaining Acceptance Boundary

Cloud has zero active CPA accounts. With a truly empty pool, upstream CPA reports `auth_not_found`; the new aggregate sweep producer intentionally emits only after final `auth_unavailable`. Therefore this activation did not restore any of the 45 known-deactivated records merely to manufacture trigger evidence, and it cannot yet prove useful model traffic or natural archive classification.

The exact candidate identity binds the already tested producer and global two-request middleware, while the public runtime policy canary confirms that the active process advertises ceiling `2`. Natural business-concurrency, aggregate-trigger, rapid high-concurrency sweep, quota retention, permanent-failure archive, and restore acceptance remain pending at least one independently verified usable credential.

Both cloud failure/sweep watchers remain inactive. The existing CPA-health unit still uses its pre-watcher command even though the activation added only its required writable paths. Watcher installation remains a separate exact-confirmation transaction and must occur before usable cloud capacity is imported.

## Next Gate

The ordered M4B sequence next requires communication-safe local `.policy.3` activation. Because this Codex conversation depends on the local CPA, that transaction must use its existing real-Codex pre/post/rollback canaries and deferred restart mechanism under a separate exact confirmation. Cloud watcher activation, local watcher activation, credential import, and all M5 retirement actions remain unapproved.
