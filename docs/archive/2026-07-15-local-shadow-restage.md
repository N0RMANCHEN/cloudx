# 2026-07-15 Local Shadow Restage

This records fresh evidence from the current macOS endpoint after the repository was fast-forwarded to `d63ffe2`. It supersedes assumptions that staging performed on another endpoint was present on this machine. No Cloudx release was activated.

## Staged Releases

- `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.1/cloudx-local.pyz`
  - SHA-256: `31ec54a222ab81033e2188fc947e8a1576c4cb15f2c56b680c055bf9c4dbc2ef`
  - self-check: local `0.1.1`, protocol `1..1`, status `ok`
- `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.2/cloudx-local.pyz`
  - SHA-256: `98462f223fc74bb64eee892e0b8c1bd2b0d833ed6f1b195894ed5647f62f5912`
  - self-check: local `0.1.2`, protocol `1..1`, status `ok`

Both artifact hashes match their signed manifests. The release directories are private and user-owned. `/Users/BofeiChen/.local/lib/cloudx/current` remained absent.

## Active-Path Continuity

- Official `codex` continued to resolve to `/opt/homebrew/bin/codex`.
- The active shell continued to resolve `codexx` to the account-scoped legacy path `/Users/BofeiChen/.codex-accounts/api/.local/bin/codexx`, SHA-256 `cf9264cd5a1150587edae6b10fad2753cf3dfb3525af0af179f3323a7ba26036`.
- The legacy `/Users/BofeiChen/.local/bin/codexx` file remained a regular file, SHA-256 `fc089c6b2b8d1aac959a35509407afdc63906ff57eaa1ee682b2d667241448c6`.
- No `cloud` command was installed.
- The legacy SSH listener remained PID `78601` on `127.0.0.1:18317` before and after staging.
- `/Users/BofeiChen/.zshrc` remained outside the staging transaction; its post-check SHA-256 was `c7fa7b58f759f05be517305a330b28de0cf4024abdc37d93e12ebb7c58e3c34a`.

The active Codex environment had an account-scoped `HOME`, but Cloudx resolved the real passwd home and staged only under `/Users/BofeiChen/.local/lib/cloudx`. No account profile, session, command symlink, shell hook, tunnel, cloud service, or production auth path changed.
