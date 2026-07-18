# CPA Policy 3 Cloud Staging

Date: 2026-07-18

## Decision And Boundary

The operator supplied the exact confirmation:

```text
STAGE CLOUD CPA POLICY 7.2.71-cloudx-policy.3 453df72d1523
```

This authorized side-by-side staging of the exact cloud candidate only. It did not authorize CPA activation or restart, unit/drop-in changes, watcher activation, credential/archive mutation, Cloudx selector changes, local staging, import, or legacy removal.

## Pinned Candidate

```text
version=7.2.71-cloudx-policy.3
upstream=5b7f2361ee27d195f6514dde08656f6e4773a9a4
sha256=453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b
size=45322402
runtime commit=5b7f2361+cloudx-cpa-policy3
build date=2026-07-18T12:30:00Z
```

The source transaction was bound to pushed commit `e65523f9eea4a4ebf5337a5cda0d7c293eac46c7`. Direct full and shallow GitHub clones on the cloud host were interrupted before staging because fetching repository history was abnormally slow. Both temporary-only Git processes and directories were removed, and the candidate directory remained absent. A mode-private source archive generated from the same exact commit was then transferred with SHA-256 binding. The final idempotent invocation returned `already-staged`, proving the exact atomic candidate had completed during the controlled retry and matched every pinned check.

## Acceptance

- staged path: `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.3/cli-proxy-api`
- binary: root/root, mode `0755`, exact size and SHA-256
- manifest: schema `cloudx.cliproxy-policy-stage.v1`, target `cloud`, exact version/hash/size, mode `0644`
- runtime `-h` identity matches version, commit label, and build date
- active CPA remained PID `977036`, restart count `0`, active/running
- active CPA still selects baseline `/usr/local/bin/cli-proxy-api`
- baseline SHA-256 remained `1d0abbc6316b1869f74896109c0efb5e19c8197b8226f48a74212ed0a6f5a39d`
- CPA service, CPA-health service/timer, and policy drop-in hashes were unchanged
- active auth remained empty; archive inventory and Cloudx `0.1.17/0.1.16` selectors were unchanged
- temporary source/candidate directories were removed

## Next Gate

Local `.policy.3` staging remains separately confirmed. Cloud CPA still runs the baseline and has no failure/sweep producer environment. Cloud activation is a later distinct confirmation that will restart only `cliproxy.service`, retain a root-only rollback snapshot and original binary, and require health plus public maximum-two policy canaries.
