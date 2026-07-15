# Current Workstation Local 0.1.8 Activation

## Scope

This records the separate local activation on the `/Users/hirohi` macOS workstation. Earlier endpoint evidence came from another computer and did not prove that this workstation had left its codex-plus-only local installation.

The active communication path remained the existing `codexx use api` profile and external CLIProxyAPI throughout this work. No process, listener, launchd job, SSH service, cloud unit, gateway, importer, credential, or auth inventory was stopped, restarted, rebound, or deleted.

## Pre-Activation State

- official Codex: `/opt/homebrew/bin/codex`, version `0.144.3`
- active global `codexx`: regular codex-plus launcher under `/Users/hirohi/.local/bin`
- local Cloudx `current` and `previous`: absent
- locally staged signed releases: `0.1.1` and `0.1.2`
- cloud endpoint: signed `0.1.8`, previous `0.1.7`
- local CLIProxyAPI: PID `38189` on `127.0.0.1:8317`
- existing official Codex PIDs: `45333`, `74770`, `79620`, `79875`, and `80478`
- legacy port `18317`: not bound on this workstation

The repository passed the architecture gate and all `115` tests outside the restricted socket sandbox. Deterministic candidate builds returned healthy `cloudx.self-check.v1` documents for local and cloud `0.1.9`.

## Legacy Continuity

Before any entrypoint moved, the installer created `/Users/hirohi/.local/state/cloudx/legacy-backups/20260715T122545Z`:

- schema: `cloudx.legacy-local-backup.v1`
- files: `287`
- total bytes: `43,987,717`
- recovery root mode: `0700`
- manifest mode: `0600`
- recorded hash or size errors: `0`

The recovery command `/Users/hirohi/.local/bin/codexx-legacy` points to the archived launcher and reported the existing API service, launchd jobs, account profile, and model endpoint as healthy without exposing an unmasked key.

All `26` account-scoped Git shims that still called the removed `codexx git-shim` internal command were first included in the private backup, then atomically reduced to direct `/usr/bin/git` continuity launchers. Unknown or custom shims would have been preserved; none were present. This keeps already-running codex-plus shells able to use Git after the global `codexx` entrypoint changes.

## Signed Activation And Rollback

The local installer fetched immutable ref `release-artifacts/v0.1.8` at `510a1e45d34dfe094f079e9ba819ae0fe9b78e12`, verified the release signature, staged the artifact, seeded the native profile from `soul0`, installed one Cloudx shell source block, and activated local links without a service restart.

Because this workstation initially had no staged `0.1.7`, first activation registered `0.1.2` as `previous`. The active `0.1.8` trust root then verified signed `0.1.7` in an isolated temporary HOME before that canonical staged directory was moved beside the active release. A normal endpoint-only transition completed:

1. local rollback `0.1.8 -> 0.1.2`
2. local apply `0.1.2 -> 0.1.7`
3. local apply `0.1.7 -> 0.1.8`

The failed attempt to make `0.1.2` fetch `0.1.7` stopped at signature verification because `0.1.2` predates the replacement trust root. It wrote no staged release. The active `0.1.8` trust root subsequently verified the immutable `0.1.7` release before any production release directory was added.

Final local state:

- current: signed `0.1.8`
- current artifact SHA-256: `6df9a949b926435c99cee9881c226104926bb7dbe9f8b06491d728540b5dfa69`
- previous: signed `0.1.7`
- previous artifact SHA-256: `19a0861b07b4ab1d0b9d0532965c7914eb62d376468eeff229ec35a977c1322e`
- native `auth.json`: exact hash match with `soul0`
- native `config.toml`: exact hash match with `soul0`
- `.zshrc`: one Cloudx source block and no marked codex-plus source block

## Acceptance

From a clean zsh environment, `codexx use api` selected `/Users/hirohi/.codex-accounts/api/.codex`, retained real `HOME=/Users/hirohi`, and left `codex` resolving directly to `/opt/homebrew/bin/codex`. `codexx exit` cleared the selection without changing `HOME`.

Live acceptance returned:

- local API/CPA official-Codex model request: `CLOUDX_LOCAL_018_API_OK`
- isolated Cloudx broker check: remote mode `cloudx`, gateway HTTP `200`
- complete isolated cloud model request: `CLOUDX_LOCAL_018_CLOUD_OK`
- signed update check: current and available `0.1.8`, no update, no activation
- cloud release status: current `0.1.8`, previous `0.1.7`, healthy fresh `cloudx.health.v1`

After activation, rollback, reactivation, and canaries, CLIProxyAPI remained PID `38189` and all five pre-existing Codex PIDs remained alive with their original parents and start times. The local codex-plus service remains an external dependency and the recovery bundle remains required; this evidence does not satisfy the M5 legacy-removal gate.
