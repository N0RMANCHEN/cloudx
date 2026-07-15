# Current Workstation Fresh-Shell Readiness

## Scope

This batch validates the local M5 shell prerequisite and hardens source `0.1.12`. It does not install a new artifact, change `current` or `previous`, edit the active account shim, stop codex-plus or the local CPA, terminate a Codex process, source the candidate hook into the current conversation shell, or remove a legacy file.

## Active Legacy Baseline

The current conversation still runs inside the retained codex-plus API environment:

- codex-plus control server: PID `729`
- codex-plus execution parents: PIDs `45303`, `74765`, `79616`, `79871`, and `80474`
- official Codex children: PIDs `45333`, `74770`, `79620`, `79875`, and `80478`
- external local CPA: PID `38189` on `127.0.0.1:8317`
- inherited `HOME`: `/Users/hirohi/.codex-accounts/api`
- retained real home: `CODEXX_USER_HOME=/Users/hirohi`

At `2026-07-15 22:17:04 CST`, the active codex-plus runtime regenerated `/Users/hirohi/.codex-accounts/api/.local/bin/git`. The executable has SHA-256 `11233682717b6b2fad7323f4c395f06073b0175d83ce99723ac684b0dd55594e` and forwards to `codexx git-shim`. Because Cloudx intentionally has no such internal command, an inherited account-local `PATH` makes ordinary Git fail after the global `codexx` link selects Cloudx.

The regenerated shim and still-running codex-plus parents prove that the M5 no-legacy-session and package-removal gates are not satisfied. The shim remains untouched so existing sessions retain their original recovery behavior.

## Installed Fresh Shell

An isolated login zsh with real `HOME=/Users/hirohi` loaded the installed signed `0.1.11` hook from the single Cloudx source block in `.zshrc`. It observed:

- `codexx`: Cloudx shell function
- `codex`: `/opt/homebrew/bin/codex`, version `0.144.4`
- `cloud`: `/Users/hirohi/.local/bin/cloud`
- `cloudx-update`: `/Users/hirohi/.local/bin/cloudx-update`
- `codexx api`: `HOME` unchanged and `CODEX_HOME=/Users/hirohi/.codex-accounts/api/.codex`
- `codexx use api`: identical compatibility selection
- `codexx exit`: returned to native mode by clearing `CODEX_HOME` and Cloudx mode variables

The account inventory also exposed the existing named profiles, including `soul0`. No Cloudx broker lease was acquired during this check.

## Source 0.1.12 Hardening

The installed hook is safe in a normal fresh shell, but it did not sanitize an inherited legacy `PATH`. Source `0.1.12` now restores real `HOME` and removes only entries matching:

`/Users/hirohi/.codex-accounts/<account>/.local/bin`

It deliberately preserves account-scoped Codex temporary `arg0` paths and every unrelated path. The packaged and reference hooks remain byte-identical at SHA-256 `e76347b0589887000022fb9d1562bd8f722f200a0baec30bdc24ca3011771671`.

A child zsh started with the real conversation's legacy `HOME` and `PATH`, then sourced only the `0.1.12` source hook. It returned:

- real home: `/Users/hirohi`
- legacy account `.local/bin` entries: `0`
- Git: `/opt/homebrew/bin/git`
- Codex: `/opt/homebrew/bin/codex`
- named `soul0` selection: accepted with real home retained
- API direct and `use api` selection: accepted with real home retained
- native return through `codexx exit`: accepted

Before and after that subprocess, the API shim hash and mtime, Cloudx account record hash, `.zshrc` hash, local CPA PID, and all five Codex PIDs were identical.

The new regression sources the hook twice, proving idempotence, exact account-bin removal, preservation of a Codex account temporary path, and fallback to a non-account Git executable.

## Rollback Prerequisite

Local links remain:

- current: signed `0.1.11`
- previous: signed `0.1.10`

Both installed manifests passed Ed25519 verification against their retained signer files, and both local artifacts passed embedded version/protocol self-check. This proves N-1 is intact but does not replace the required explicit rollback transaction.

Before any codex-plus shell/package removal, a later operator-approved release must publish and activate the `0.1.12` hook, then complete an endpoint-only `0.1.12 -> 0.1.11 -> 0.1.12` rollback in fresh shells while the current recovery bundle and local CPA remain available. Existing codex-plus parents must also exit naturally or be separately accepted; none is terminated by this batch.
