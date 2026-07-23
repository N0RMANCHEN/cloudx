# Scoped Gateway Key Phase 2

Date: 2026-07-23

After active-pool recovery and successful Phase 1 official-Codex traffic, the immutable `v0.1.31` revoker executed exact-one transaction `20260723T063726Z-485a416b` with its distinct restart confirmation.

- gateway keys: `6 -> 5`
- gateway PID: `1916887 -> 1920633`, restart count `0`
- current credential HTTP: `200`
- previous credential HTTP: `401`
- current credential unchanged: true
- unrelated gateway keys unchanged: true
- inotify watches: `2`
- active accounts: `23`
- current credential matches: exactly `1`, mode `0600`
- Phi consumer credential matches: exactly `1`, mode `0640`
- manifest and revocation receipt: mode `0600`

Fresh broker routing returned HTTP `200`; official Codex `gpt-5.6-sol` returned exact marker `CLOUDX_PHASE2_REVOKED_OK`. Mihomo remained PID `277808`; no account, CPA binary, release selector, Phi service, or unrelated gateway/network setting changed. The previous exposed key is revoked and the two-phase remediation is complete.
