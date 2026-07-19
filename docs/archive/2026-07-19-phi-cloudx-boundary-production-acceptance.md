# Phi/Cloudx Boundary Production Acceptance

Date: 2026-07-19

Phi production now uses immutable release `3f42c73db6cbb1fbd751980f5ecb3cb0f42eff10` for normal interactive and authenticated mail Agent entry. The release contains 19,262 manifest-bound files; its release manifest SHA-256 is `415012a2183c40f80054fc5658e758898d698111f68463a945ccf4654f8ca692`. Phi final Handoff commit `ba39e757f7f753316dac6ae25585498671bd38de` records the completed rollback-bounded remediation.

The Cloudx-owned key transaction installed a distinct scoped Phi consumer bearer while retaining the existing Cloudx client credential byte-identically and retaining the previous Phi bearer for rollback. It restarted only the external gateway, which returned active with PID `1746294`, restart count `0`, HTTP `200`, and restored configuration watches. No Phi service was restarted by that transaction.

The Phi-owned boundary transaction then installed only the orchestrator and mail-command component targets. Interactive and mail diagnostics both reported:

- immutable release `3f42c73db6cbb1fbd751980f5ecb3cb0f42eff10`
- restricted orchestrator identity
- clean bounded environment
- fixed workspace
- Linux `NoNewPrivs`
- zero Cloudx administrative capabilities

Mail has only the exact restricted Phi sudo target. Identity acceptance denied broad sudo, root execution, and read/write access to Cloudx auth, archive, gateway configuration, import keys, release administration, and other protected roots. The activation restarted no Phi service, mail timer, local CPA, or Codex process. Its retained root-only rollback backup is `/var/lib/phi-cloudx-boundary/3f42c73db6cbb1fbd751980f5ecb3cb0f42eff10/1784469276136421321`.

A real `/v1/responses` request through the scoped Phi bearer returned HTTP `200` and `X-CPA-Max-Concurrent-API-Requests: 2`, then produced a fresh identity-free `available` pool observation at `2026-07-19T14:05:55.043868328Z`. The signed CPA-health, account-state, and formal-health one-shot publishers propagated that observation without probing or restarting CPA. `/run/cloudx/health.json` then reported protocol `1`, gateway healthy, import ready, one available account, freshness `fresh`, and age `26` seconds.

The immutable Phi boundary acceptance receipt passed exact revision, exact executable and manifest target, formal `cloudx.health.v1` state `healthy/all_ready`, disabled legacy repair timer, and permission denial for all four Cloudx-sensitive path classes. Cloudx strict checks then reported:

- release ordering: `compatible`, zero blockers
- legacy-health bridge: `runtime-accepted`, zero blockers
- Phi privileged boundary: `secure`, zero blockers
- Phi/Cloudx failure semantics: `accepted`, verified Phi snapshot, nine scenarios, zero blockers

Phi Roadmap items `INT/P1-1` and `CT/P1-3` remain truthfully blocked future Mesh work. Their status is informational to Cloudx M4A because the accepted runtime boundary, compatibility, and failure semantics do not require synchronized feature completion or cross-repository mutation authority.

The previous Phi credential, previous component targets, signed Cloudx N-1 releases, legacy-health rollback service, and both bridge rollback sets remain retained. Their removal or revocation requires a separate exact-confirmation retirement transaction.
