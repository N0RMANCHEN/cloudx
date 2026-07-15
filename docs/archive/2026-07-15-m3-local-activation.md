# 2026-07-15 M3 Local Activation

This document records the separately approved local Cloudx `0.1.2` activation, native-profile seed, legacy API/CPA recovery bundle, formal command acceptance, and dual-endpoint rollback rehearsal.

## Legacy Recovery Before Activation

The existing codex-plus API/CPA path was copied to private Cloudx state before any local entrypoint changed.

- recovery root: `/Users/BofeiChen/.local/state/cloudx/legacy-backups/20260715T050707Z`
- schema: `cloudx.legacy-local-backup.v1`
- files: `169`
- total bytes: `43,485,242`
- recovery root mode: `0700`
- manifest mode: `0600`
- verified manifest hashes: every recorded file

The bundle contains the old global and account-scoped launchers, full adjacent `codexx_app` runtime, existing `api` and `cpa` profiles, account-scoped Git shim, local CLIProxyAPI binary, launchd definition, configuration, and top-level credential files. Raw content and credentials do not appear in the manifest or Git.

The explicit recovery command `/Users/BofeiChen/.local/bin/codexx-legacy` points into this bundle. `codexx-legacy api status` successfully verified the preserved local CPA service without exposing its key.

## Native Profile And Shell Activation

- active local release: `0.1.2`
- local `current`: `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.2`
- local `previous`: `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.1`
- native source: `soul0`
- native `auth.json` SHA-256: `566e6b32a0fc5859579e3aa048eb6138fa38eb0429484cb4149ae741fb6c9330`
- native `config.toml` SHA-256: `99de12acf6914428e0b00846677b2e19fb30695be7e32207643238a39a19a0dc`
- source and destination hashes: exact match
- native file modes: `0600`
- previous native config backup: `/Users/BofeiChen/.local/state/cloudx/native-profile-backups/20260715T050846Z/config.toml`
- previous native auth backup: absent because no native `auth.json` existed before activation
- shell backup: `/Users/BofeiChen/.local/state/cloudx/shell-backups/zshrc-20260715T050846Z`

The local `codexx`, `cloud`, and `cloudx-update` links point through `current/cloudx-local.pyz`. The official `codex` continues to resolve to `/opt/homebrew/bin/codex` and is not wrapped.

The installed minimal shell hook preserves both `codexx <account>` and `codexx use <account>`. In a clean shell with no inherited codex-plus state:

- initial selection: native, real `HOME=/Users/BofeiChen`
- `codexx use api`: selected `/Users/BofeiChen/.codex-accounts/api/.codex`
- `codexx cpa`: selected `/Users/BofeiChen/.codex-accounts/cpa/.codex`
- `codexx exit`: returned to native
- real `HOME`: unchanged through every selection

## Local CPA Continuity

The existing local CLIProxyAPI remained an external launchd service on `127.0.0.1:8317`, PID `17165`. Both existing profiles remained usable:

- `api`: local CPA profile
- `cpa`: local CPA profile

A complete official Codex request after `codexx cpa` returned exactly `CLOUDX_LOCAL_CPA_OK`.

The old CPA management surface is available only through the clearly labeled `codexx-legacy` recovery command during observation. Cloudx does not take ownership of the CLIProxyAPI binary, launchd lifecycle, provider pool, upgrades, or credential refresh.

## Active Cloudx Command Acceptance

From a clean post-activation shell:

- `cloud codex --check`: remote mode `cloudx`, HTTP `200`
- `cloud import <local-path> --dry-run`: accepted through real SSH stdin
- `cloudx-update check`: current and available `0.1.2`, no update, no activation
- complete installed `cloud codex` request: returned exactly `CLOUDX_M3_LOCAL_OK`
- canary brokers: zero leases after use and shut down cleanly

The accepted interaction model is documented in `docs/command-surface.md`.

## Rollback Rehearsal

First activation registered the staged N-1 release as `previous` on both endpoints. A real one-endpoint-at-a-time round trip succeeded:

1. local `0.1.2 -> 0.1.1`
2. verify `codexx use api` and `cloud codex --check`
3. local `0.1.1 -> 0.1.2`
4. cloud `0.1.2 -> 0.1.1`
5. verify cloud `0.1.1` handshake and local-to-cloud HTTP `200`
6. cloud `0.1.1 -> 0.1.2`

Final state on both endpoints is current `0.1.2`, previous `0.1.1`.

## Existing-Session Continuity

The already-running `api` session inherited an account-scoped Git shim that called the removed codex-plus internal command `codexx git-shim`. Full verification detected this when `git init` failed. The original shim was added to the private recovery bundle, then the live shim was reduced to a direct `/usr/bin/git` continuity launcher. Repository verification subsequently passed.

Throughout activation and rollback:

- legacy cloud SSH listener remained PID `78601` on `127.0.0.1:18317`
- local CPA remained PID `17165` on `127.0.0.1:8317`
- cloud CLIProxyAPI remained PID `977036`
- cloud legacy importer remained PID `133756`
- no service was restarted or terminated

M3 endpoint activation and rollback acceptance are complete. The legacy path remains available for the observation window; retirement is a later, separately approved milestone.
