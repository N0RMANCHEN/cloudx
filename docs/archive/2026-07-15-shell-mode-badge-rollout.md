# Cloudx 0.1.6 Shell Mode Badge Rollout

Date: 2026-07-15

## Release Identity

- source commit: `907d1746e0d76dfada579a77454d4efbc3ce69c4`
- artifact ref: `release-artifacts/v0.1.6`
- artifact ref SHA: `5dfdb4b810a02b6e2cdb06ae31b1c0d96165e88e`
- stable ref SHA: `d8df04021408e4efb9f12e5adb627cf366d77225`
- local artifact SHA-256: `226ecfdf5bd5ac97d61bc66dc42d7493ee9e8a5857a581f0c43b19598ff0f916`
- cloud artifact SHA-256: `a1301702bfc98bf2fed76faa43de8c5b3209ad43b7f3650335eabb59d1eadf2d`

The signed manifest and stable index verified from fresh clones. Both artifact self-checks reported product version `0.1.6` and protocol range 1 through 1.

## Activation

The cloud endpoint was activated first and reported `currentVersion` `0.1.6`, `previousVersion` `0.1.5`, and the expected cloud artifact hash. The local endpoint then selected `0.1.6` with `0.1.5` retained as `previous`.

The first local `--install-shell-hook` attempt exposed a stable-entrypoint zipimport race: after the old updater moved `current`, it tried to load an embedded resource through the now-retargeted zipapp path and received a truncated-stream error. The release selection itself had completed. Re-running the exact confirmed activation from the immutable `0.1.6` artifact path installed the hook idempotently and retained `0.1.5` as the rollback release. Repository development advanced to `0.1.7` with a regression fix that reads the target hook before moving `current`.

No service restart occurred.

## Prompt Acceptance

A fresh zsh using the installed Cloudx hook produced:

- initial and local API mode: `[cx:api]`
- cloud mode: `[cx:cloud]`
- named account mode: `[cx:soul0]`
- `codexx exit`: no Cloudx prompt segment

Repeated hook loading registered exactly one `__cloudx_refresh_prompt` precmd hook. The official Codex executable remained `/opt/homebrew/bin/codex`, while `codexx` remained a shell function for applying mode exports to the current shell.

## Continuity

- legacy local tunnel listener: PID `78601` on `127.0.0.1:18317`
- local CPA listener: PID `17165` on `127.0.0.1:8317`
- cloud CLIProxyAPI: PID `977036`
- old cloud importer: PID `133756`
- tunnel broker after the canary: zero active leases

These processes remained alive with the same PIDs. The local current and previous releases are `0.1.6` and `0.1.5`; the cloud current and previous releases are also `0.1.6` and `0.1.5`.
