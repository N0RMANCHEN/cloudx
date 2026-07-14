# 2026-07-14 Cloud Shadow Stage 0.1.1

This document records side-by-side cloud staging only. No Cloudx release was activated and no production service or credential directory was changed.

## Staged Release

- Destination: `/opt/cloudx/releases/0.1.1`
- Stage result: `cloudx.release-stage.v1`, status `staged`
- Staged cloud zipapp SHA-256: `8ae86e10ddec5a5a50310fcaf5b00881612f149a7cbc7c351987f434052fe4dd`
- Staged manifest SHA-256: `a3a738b132da8be588861cd0fb86e66054356bf568e5ed2673339a47fe8e001c`
- `/opt/cloudx/current`: absent before and after staging

The staged hashes exactly match `docs/archive/2026-07-14-release-0.1.1.md`. Release files are root-owned; the zipapp is mode 0755 and manifest, signature, and trust root are mode 0644.

## Continuity Checks

Before and after staging:

- `cliproxy.service` retained PID `586892`, restart count `0`, and active timestamp `98063220486`.
- `codex-import.service` retained PID `133756`, restart count `0`, and active timestamp `43952803944`.
- The production auth directory retained inode/timestamp/mode/owner metadata `131173:1783989250:1783989250:700:cliproxy:cliproxy`.
- Local port `18317` had no listener before staging and remained unchanged afterward.

The uploaded `/tmp` artifact and offline bundle were removed after the staged copies were verified.
