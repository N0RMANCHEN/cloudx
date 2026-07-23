# Cloud Active Pool Recovery Promotion

Date: 2026-07-23

Immutable `v0.1.33` operator transaction `20260723T071131Z-0b669f3c` accepted the exact private request SHA-256 `384c342b61c766e4e9ada5290da0f510c855f254a36728388fc2fa59f243f3c4` against unavailable active baseline count `11`.

- written/distinct Agent Identities: `12`
- active count: `11 -> 23`
- isolated canaries: `12` requests in `13` attempts
- final combined-pool canary: `1`
- archive entries: `45`
- failure inputs: `0`
- sweep trigger: absent
- CPA PID/restarts: `1916887/0`
- service restart/raw credential retention: false

Fresh broker/client-config routing returned gateway HTTP `200`. Official Codex `gpt-5.6-sol` then returned exact marker `CLOUDX_PHASE1_ACCEPTED_0_1_33_OK`. This closes the remaining Phase 1 business-traffic gate without changing the scoped key transaction. The previous gateway key remains active pending the separately confirmed exact-one Phase 2 revocation.
