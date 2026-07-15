# 2026-07-15 M3 Cloud Helper Activation

This document records the separately approved first activation of the cloud endpoint only. The local Cloudx release and commands remained inactive, and the legacy codex-plus path remained available.

## Verified Network Topology

The current path was measured rather than inferred:

- `ssh cloud` resolves to user `hirohi` at public address `39.96.201.183:22`.
- The local route to that public SSH address uses `utun9`; local Clash listens on port `7890`.
- The legacy listener remains `127.0.0.1:18317`, owned by SSH PID `78601`, forwarding to `100.90.97.113:8317` through the `cloud` SSH host.
- `100.90.97.113` is the cloud host's own Tailscale address. On the cloud host, routing to it is local loopback, not a second hop back to the Mac.
- CLIProxyAPI listens on cloud Tailscale address `100.90.97.113:8317`.
- The cloud host also runs mihomo on `127.0.0.1:7890`.

Therefore the observed legacy request path is local codex-plus/profile selection, local VPN-routed public SSH, the cloud host's own Tailscale-bound CLIProxyAPI, and the cloud-side upstream path. Cloudx replaces the account/tunnel/import/release bridge; it continues to treat SSH, Tailscale, mihomo, and CLIProxyAPI as external dependencies.

## Activation Transaction

- Activated signed cloud release: `0.1.2`
- Source commit: `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e`
- Active artifact SHA-256: `e5af505cfc6f9398b84e532540a48015d0e56bb7864e7e65f2d0ea824bd4194c`
- `/opt/cloudx/current`: `/opt/cloudx/releases/0.1.2`
- `/usr/local/bin/cloudx-remote`: mode `0755`, root-owned, SHA-256 `166f17138de93f80bb9dce97dc409f1e61b5dc3d23daad66884d53594567b436`
- `/usr/local/libexec/cloudx-remote-runner`: mode `0755`, root-owned, SHA-256 `b460e17d8ad74fd2048f976bdd5d8fc5c46bf97efcfac450e6b6014fd9663f0d`
- `/etc/sudoers.d/cloudx-remote`: mode `0440`, root-owned, SHA-256 `e70c6bf0534a269bc17f7937a3810bdc41297790af30afe22c14f409897c5eeb`
- `visudo` validation: parsed OK
- Service restarts: none

Normal handshake, health, client configuration, self-check, release status, and import commands dispatch as the restricted `cloudx` identity. Only signed release stage, activation, and rollback commands dispatch through the root release boundary.

Two initial bootstrap attempts exposed a launcher self-check bug and rolled back every managed path. Gateway PID `977036`, importer PID `133756`, local listener PID `78601`, and all active services remained unchanged. After changing installed-shell-helper verification from Python interpretation to direct execution, the confirmed transaction succeeded.

## Formal Helper Acceptance

- self-check: cloud `0.1.2`, protocol `1..1`, status `ok`
- handshake: deployment `shadow-0.1.2`, gateway `healthy`, importer contract `1`
- release status: active `0.1.2`, no previous release, artifact hash matched the signed manifest
- health: fresh, gateway `healthy`, importer `ready`
- client config: schema valid, scoped key present, forward target `100.90.97.113:8317`; the key value was not printed
- low-level local-file dry-run: `ssh cloud cloudx-remote import --dry-run < file`, accepted
- staged local command dry-run: `cloud import <local-path> --dry-run`, accepted through the formal helper

## Broker And Model Acceptance

The staged local artifact used the now-default `cloudx-remote` helper without a temporary override:

- `cloud codex --check`: remote mode `cloudx`, separate broker port `28955`, HTTP `200`
- complete official Codex request: returned exactly `CLOUDX_M3_CLOUD_OK`
- canary broker: zero leases after the request and shut down cleanly
- legacy `127.0.0.1:18317`: retained SSH PID `78601`

## GitHub Dual-Endpoint Synchronization

The formal active helper accepted the signed release-stage protocol from the local updater. Fetching GitHub `release-artifacts/v0.1.2` and staging both endpoints returned:

- local: `already-staged`
- cloud: `already-staged`
- activated by staging: `false`

This proves that one signed GitHub release can be verified and synchronized to both release stores without implicit activation or service restart.

## Remaining M3 Boundary

The local endpoint remains inactive:

- `/Users/BofeiChen/.local/lib/cloudx/current`: absent
- official `codex`: `/opt/homebrew/bin/codex`
- active `codexx`: account-scoped legacy codex-plus path
- `cloud` command: absent

Local profile seeding, shell-hook replacement, local command activation, rollback rehearsal, and the local observation window require their own operator confirmation.
