# 2026-07-14 Local Shadow Stage 0.1.1

This document records local side-by-side staging only. No Cloudx local entrypoint, shell hook, account profile, tunnel, or release symlink was activated.

## Staged Release

- Destination: `~/.local/lib/cloudx/releases/0.1.1`
- Stage result: `cloudx.release-stage.v1`, local status `staged`, `activated: false`
- Staged local zipapp SHA-256: `31ec54a222ab81033e2188fc947e8a1576c4cb15f2c56b680c055bf9c4dbc2ef`
- Staged manifest SHA-256: `a3a738b132da8be588861cd0fb86e66054356bf568e5ed2673339a47fe8e001c`
- `~/.local/lib/cloudx/current`: absent before and after staging

The staged hashes exactly match `docs/archive/2026-07-14-release-0.1.1.md`.

## Command Continuity

Before and after staging:

- `codex` resolved directly to `/opt/homebrew/bin/codex`.
- The active `codexx` resolution remained `/Users/hirohi/.codex-accounts/cloud/.local/bin/codexx`.
- No `cloud` command was installed.
- No Cloudx `codexx`, `cloud`, or `cloudx-update` activation symlink was created.
- Local port `18317` had no listener and remained unchanged.

No shell file, native Codex profile, account home, session, or running process was modified.
