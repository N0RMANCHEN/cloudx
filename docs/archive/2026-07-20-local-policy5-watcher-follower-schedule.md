# Local Policy5 Watcher Follower Schedule

Date: 2026-07-20 CST (`2026-07-19` UTC)

The local dual-input failure watcher remains inactive until the exact `.policy.5` producer is accepted. A separate follower was scheduled from immutable pushed Cloudx commit `f2d3762fa7e80a10a49b29a76a9e5577f65cf50b`; no production action ran from the Git checkout.

## Immutable Inputs

- Follower scheduler SHA-256: `46ba487865e293681fc8942307b2f44ed9e653233aae76c3870eeb416ca53b1f`.
- Watcher installer SHA-256: `1d58dac580d7f843bcc1b7a1ed0ced2a571f1edac00c5bd89acc81cd08ed3aab`.
- Policy scheduler dependency SHA-256: `bf37569e6fd7996212a053187641a3dc2221a6e3f588901f9380d207cf56bd7f`.
- Deployment contract SHA-256: `4d8e40cc37d81122b49f9ce22879e9d1f90977020f3fa9af7973ea7d63fe0046`.
- Required producer: `7.0.1-codexx-fast-service-tier-cloudx-policy.5`, SHA-256 `bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3`.

## Follower Job

- Activation job ID: `20260719T160250Z-9a24174c`.
- Exact separate confirmation: `ACTIVATE LOCAL CPA FAILURE WATCHER 0.1.21`.
- Follower worker PID at schedule acceptance: `3561`.
- Poll interval: 60 seconds.
- Final receipt deadline: `2026-07-26T17:05:50Z`, one hour after the policy activation deadline.

The mode-`0700` follower job contains mode-`0600` copies of every executable input and the exact contract. Its worker accepted all copied digests and entered `activation-receipt-wait`. Both policy and follower receipts were absent at acceptance.

The follower accepts only a v2 policy receipt with the same job ID, `status=accepted`, exact policy version and digest, `communicationCanary=passed`, and `serviceAvailable=true`. Every failed, expired, mismatched, communication-failed, or unavailable result writes a failed follower receipt and invokes no watcher command. An accepted result invokes only the copied local watcher transaction, which retains its own private launcher backup and automatic rollback and has no external-CPA restart authority.

## Continuity Evidence

The policy worker remains alive in `quiescence-wait`; its latest read-only audit reported 62 established port-`8317` socket rows and `serviceChanged=false`. Therefore no policy activation was attempted. The maintenance launcher still has its original 900-second interval and no watcher paths. External CPA remains on the retained baseline as PID `61859`, and `/healthz` remains accepted. No CPA, Codex, Cloudx, or Phi process or service was stopped or restarted by follower scheduling.

The existing policy activation job retains its exact `RECOVERY.txt`, job-local baseline recovery tool, launcher snapshot, and automatic recovery path. The watcher transaction remains independently rollback-protected and cannot run before that policy recovery boundary reports accepted communication.
