# 2026-07-14 Cloud Shadow Stage 0.1.2

This document records cloud side-by-side staging only. No release was activated and no service, credential, or production auth path was changed.

## Staged Release

- Destination: `/opt/cloudx/releases/0.1.2`
- Source commit: `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e`
- Cloud zipapp SHA-256: `e5af505cfc6f9398b84e532540a48015d0e56bb7864e7e65f2d0ea824bd4194c`
- Manifest SHA-256: `f59b81ae4643fa73639a1125e43103111ab2b733ce350fa324e0ad2637427087`
- Manifest signature SHA-256: `01ec61c6abcc6f1262b6b4dea7043d4bc334b1ef9c8e18cf7cbe196b35efdf13`
- Artifact self-check: cloud `0.1.2`, protocol `1..1`, status `ok`
- Release status from the staged artifact: `inactive`, with no `currentVersion` or `previousVersion`

The staged hashes exactly match the signed `0.1.2` release evidence. The release directory and zipapp are root-owned mode 0755; manifest, signature, and trust root are root-owned mode 0644.

## Continuity Evidence

- `/opt/cloudx/current`: absent before and after staging.
- Shadow environment artifact: remained `/opt/cloudx/releases/0.1.1/cloudx-cloud.pyz`.
- `cliproxy.service`: PID `586892`, restart count `0`, active/running before and after.
- `codex-import.service`: PID `133756`, restart count `0`, active/running before and after.
- Gateway config SHA-256: remained `1553bd677e7ba7ead7b37c799a65da476472660544dff35ad234d5aa3942cc34`.
- Production auth metadata: remained `131173:1783989250:1783989250:700:cliproxy:cliproxy`.
- Exact official local Codex PID set: remained `45333,74770,79772,80516,86256`.
- Local port `18317`: absent before and after.

No production symlink, service state, credential, auth content, legacy session, tunnel, or listener changed.
