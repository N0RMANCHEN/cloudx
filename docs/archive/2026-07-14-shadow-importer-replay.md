# 2026-07-14 Shadow Importer Fixture Replay

This document records an isolated importer replay inside the configured cloud shadow auth root. It did not use or modify the production auth directory.

## Inputs

- Canonical importer: signed `/opt/cloudx/releases/0.1.1/cloudx-cloud.pyz`
- Replay tool SHA-256: `7670fee88abec6f7aad0f8ad5d7a8a0b8da180ea3ffddff40d0047a1a453aba9`
- Confirmed shadow root: `/var/lib/cloudx/shadow-auth`
- Execution identity: restricted `cloudx` user

## Result

- Schema: `cloudx.import-fixture-check.v1`
- Status: `ok`
- Accepted fixture formats: 8
- Normalized transactions: 8
- Idempotent replays: 8
- Raw sources retained: false
- Fixture output retained: false

The tool created a private isolated child directory under the shadow root, compared deterministic filenames and canonical JSON output, replayed every transaction, checked that no raw source bytes were present, and removed the child directory. The shadow auth root contained zero entries before and after the check.

## Production Continuity

- `cliproxy.service` retained PID `586892`, restart count `0`, and active timestamp `98063220486`.
- `codex-import.service` retained PID `133756`, restart count `0`, and active timestamp `43952803944`.
- The production auth directory retained metadata `131173:1783989250:1783989250:700:cliproxy:cliproxy`.
- The temporary replay tool was removed from `/tmp` after verification.
