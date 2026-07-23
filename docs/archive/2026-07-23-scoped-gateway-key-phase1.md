# Scoped Gateway Key Phase 1

Date: 2026-07-23

## Immutable Operator Boundary

Both endpoints selected signed Cloudx `0.1.31/0.1.30` before the retry. The operator bundle was extracted only from annotated `v0.1.31`, source `0985802204f1d4d42e335c07181fdb41e032bf48`, and installed under root-private `/var/lib/cloudx/scoped-key-operator/0985802204f1d4d42e335c07181fdb41e032bf48`.

- installer SHA-256: `b4683ec0165a318ee8da2bef0e3447559bab2b9ebb41a8d4da8f5d637cfa87ee`
- revoker SHA-256: `db4de6268fc5758fe6db704272121645ba7ed616c0ddd2693db2cad39a1341a4`
- directory and both scripts: root-owned mode `0700`

The read-only plan returned only `cloudx.scoped-key-plan.v1`, exact `0.1.31` artifact binding, and `RESTART cliproxy.service FOR CLOUDX SCOPED KEY`. Immediately before apply, the local broker had zero leases, the cloud gateway had zero established port-8317 connections, the rotation root had zero transactions, and the gateway remained PID `1871934` with restart count `0`.

## Overlap Result

The exact confirmed transaction returned `cloudx.scoped-key-install.v1`, status `installed`, transaction `20260723T063726Z-485a416b`:

- gateway keys: `5 -> 6`
- gateway PID: `1871934 -> 1916887`, restart count `0`, active
- new credential HTTP status: `200`
- previous credential retained: `true`; independent status `200`
- unrelated key order preserved: `true`
- Phi consumer key matches before/after: exactly one; credential remains mode `0640`
- current client credential: exactly one match, appended entry, mode `0600`
- config/auth watches: `2`
- manifest and complete config backup: mode `0600`

No raw credential appears in this evidence. The secret-free manifest binds pre/post config digests, old/new credential digests, exact artifact, paths, process identities, backup, and rollback state.

## Client Cutover And Remaining Gate

Because the existing broker had zero leases, it was cleanly shut down and replaced. Fresh broker PID `91666`, SSH PID `91667`, and public port `28376` fetched the new remote client configuration and returned gateway HTTP `200`; leases returned to zero. Handshake reports Cloudx `0.1.31`, build `0985802204f1d4d42e335c07181fdb41e032bf48`, deployment `shadow-0.1.31`, and gateway `7.2.71` healthy. Fresh formal health reports gateway healthy and no available account.

The required real official-Codex `gpt-5.6-sol` request reached the new tunnel and authorized gateway path, then returned the already known business-capacity response `503 auth_unavailable: no auth available`. It did not return credential `401` and did not disconnect the tunnel. Phase 1 business acceptance is therefore incomplete even though rotation and cutover mechanics passed.

The old key remains active. Phase 2 exact-one revocation must not run until a fresh official-Codex-through-cloud model request succeeds. This gate does not authorize account import, shadow promotion, credential repair, CPA restart, or any unrelated gateway/network change.
