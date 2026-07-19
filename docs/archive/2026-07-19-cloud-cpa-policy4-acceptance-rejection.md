# Cloud CPA policy.4 acceptance rejection

Date: 2026-07-19

Transaction `20260719T090507Z-14915b32` repeated the rollback-bounded M4B production acceptance against active cloud CPA `7.2.71-cloudx-policy.4`. The isolated phases again accepted three real weekly-limit retentions, one provisional refreshable-401 retention, one conclusive non-refreshable-401 archive, and digest-exact restore. Natural all-candidate traffic then returned HTTP `429 model_cooldown`, but the expected identity-free aggregate trigger was absent, so the transaction rejected with `aggregate_not_triggered`.

The prebuilt recovery path completed automatically. It restored the one useful active credential, all 45 prior archive entries, an empty failure directory, an absent sweep trigger, real HTTP `200` model traffic with policy `2`, cloud CPA PID `1693505` with restart count `0`, local CPA PID `61859`, the 37-file local auth aggregate, and all captured Codex processes. No CPA, importer, Cloudx, Phi, or local process was restarted by acceptance or recovery.

The exact upstream cause is a type mismatch, not a timing or watcher defect. `model_cooldown` is returned as the private `modelCooldownError` type in `sdk/cliproxy/auth/selector.go`; it is not `*coreauth.Error`. The `.policy.4` handler first required `errors.As(err, *coreauth.Error)`, making its later string-code branch unreachable for a real cooldown. Its test constructed a synthetic `coreauth.Error{Code: "model_cooldown"}` that the upstream selector never produces.

Source `.policy.5` fixes only this producer path. The real private error exposes `CloudxPoolUnavailable() bool`; the handler checks that typed capability before the `coreauth.Error` cast, emits the existing identity-free `auth_unavailable` trigger, and returns the original error unchanged. The ordinary `auth_unavailable` path remains supported. No error-text parsing, provider/model identity, quota archive authority, credential move, or CPA lifecycle authority was added.

The shared supplemental patch has SHA-256 `2101b12519607ab022fd0780069d3f75207a1d2046114450420df4906dc0ded8`. Focused Go regressions pass on both exact upstream commits and exercise the real `newModelCooldownError` constructor plus a typed handler fixture. Three independent deterministic builds are byte-identical for each target:

- Local `7.0.1-codexx-fast-service-tier-cloudx-policy.5`: SHA-256 `bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3`, size `41484978`.
- Cloud `7.2.71-cloudx-policy.5`: SHA-256 `5f83b1821d2be7cf5b7615973e4e6130d477386e16eae3a50af46e99bf7af7f8`, size `45322402`.

These are source candidates only. At this evidence point, `.policy.5` is not published, staged, selected, or active, and no production service or credential state changed.
