# CPA Policy 3 Cloud Activation Attempt

Date: 2026-07-18

## Decision And Boundary

The operator supplied the exact confirmation:

```text
ACTIVATE CLOUD CPA POLICY 7.2.71-cloudx-policy.3 453df72d1523
```

This authorized one cloud CPA candidate-selection transaction, one operator-approved `cliproxy.service` restart, and automatic baseline restoration including a second restart if any canary failed. It did not authorize local CPA activation, watcher activation, credential import/archive mutation, Cloudx selector changes, Phi changes, or legacy removal.

## Preflight

- active Cloudx selectors were `current=0.1.17`, `previous=0.1.16`
- staged candidate SHA-256 was `453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b`
- baseline SHA-256 was `1d0abbc6316b1869f74896109c0efb5e19c8197b8226f48a74212ed0a6f5a39d`
- cloud CPA was PID `977036`, active/running with restart count `0`, selecting `/usr/local/bin/cli-proxy-api`
- no policy drop-in, failure directory, sweep directory, or established port-`8317` connection existed
- active auth remained empty; the known-deactivated archive was unchanged

## Attempt And Automatic Rollback

The transaction atomically installed the two policy drop-ins, reloaded systemd, and restarted only `cliproxy.service`. Candidate PID `1611949` reported exact runtime identity `7.2.71-cloudx-policy.3`, commit `5b7f2361+cloudx-cpa-policy3`, and listener target `100.90.97.113:8317`.

`wait_systemd_active` observed the unit as active/running, but the old installer immediately issued a single HTTP health request. That request landed in the sub-second interval before the socket accepted connections and returned `CPA health canary could not connect`. The automatic recovery restored both prior drop-in snapshots, reloaded systemd, and restarted the baseline as PID `1612019`. Its own one-shot recovery probe hit the same readiness window, so the low-level connection error masked the intended high-level rolled-back result even though restoration completed.

Independent verification immediately afterward established:

- baseline `7.2.71` was active/running from `/usr/local/bin/cli-proxy-api`
- the service listened on the configured `100.90.97.113:8317` endpoint
- `/healthz` returned HTTP `200` with status `ok`
- `cloudx-remote handshake --json` reported Cloudx `0.1.17` and healthy gateway `7.2.71`
- both policy drop-ins were absent
- both newly created private policy directories were empty, owner/mode checked, and removed as the final rollback cleanup
- the root-only rollback manifest was retained outside the release directory
- no temporary activation source directory remained locally or remotely

The two restarts were the candidate selection and its explicitly authorized automatic rollback. systemd restart count remained `0` because both were operator-requested restarts rather than crash recovery. No local CPA or Codex process was touched, so the CPA-backed communication path for this session remained available.

## Root Cause And Source Correction

The top-level endpoint parser returned the correct configured address. Journal ordering shows candidate startup, listener announcement, failed canary, candidate stop, baseline startup, and baseline listener announcement within the same wall-clock second. The defect was therefore readiness synchronization, not candidate identity, bind address, policy behavior, or account state.

The deployment transaction now:

- retries health and policy connections for a bounded 20-second readiness window
- distinguishes an activation failure from a failure to verify baseline restoration
- removes only empty private failure/sweep directories created by the failed activation
- refuses to delete a directory containing any runtime evidence

Focused regressions cover the listener-startup retry and conservative directory cleanup. Full repository verification is required before another operator decision.

## Next Gate

The cloud `.policy.3` candidate remains staged and inactive. Reusing the consumed confirmation is prohibited because another attempt would restart the external cloud CPA again. After the source correction and full verification are committed and pushed, the next mutation requires the operator to repeat the exact confirmation:

```text
ACTIVATE CLOUD CPA POLICY 7.2.71-cloudx-policy.3 453df72d1523
```
