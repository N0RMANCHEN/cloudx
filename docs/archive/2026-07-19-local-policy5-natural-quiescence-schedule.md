# Local Policy5 Natural-Quiescence Schedule

Date: 2026-07-19

The local `.policy.5` activation remains prohibited while any port-`8317` connection exists. A new detached monitor was scheduled from immutable pushed commit `ec24256dbe10c83833818e9e58c7e8f7967b368a`; no production code ran from the Git checkout.

## Immutable Inputs

- Scheduler SHA-256: `bf37569e6fd7996212a053187641a3dc2221a6e3f588901f9380d207cf56bd7f`.
- Installer SHA-256: `368106e639b5f9eba11aca8aeddd5d8dec0ed15d634e5f573f5d4ad72fed5bc9`.
- Recovery tool SHA-256: `214ccf4ef6f14929903a4fbba5b5bf14fa3275b6441a47a692ea50aa6b8a519a`.
- Deployment contract SHA-256: `4d8e40cc37d81122b49f9ce22879e9d1f90977020f3fa9af7973ea7d63fe0046`.
- Candidate: `7.0.1-codexx-fast-service-tier-cloudx-policy.5`, SHA-256 `bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3`.

## Job

- Job ID: `20260719T160250Z-9a24174c`.
- Exact activation confirmation: `ACTIVATE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.5 bb6fe9cfcc26`.
- Initial delay: 180 seconds.
- Maximum natural-quiescence wait: 604800 seconds.
- Poll interval: 60 seconds.
- Required final gate: five consecutive zero-established-connection samples, repeated again by the installer before launcher mutation.

The mode-`0700` job contains exact copies of the installer, recovery tool, scheduler, deployment contract, original launcher snapshot, job manifest, and `RECOVERY.txt`. The independent recovery plan validated the current baseline PID `61859` and printed its exact confirmation without changing service state.

After the initial delay, the worker entered `quiescence-wait`. There were still 66 established socket rows, so the candidate was not selected, the launcher was not changed, and CPA PID `61859` remained healthy on port `8317`. The worker performs only bounded socket observation during this state. It never terminates Codex processes to manufacture quiescence.

If the seven-day window expires, the job records `connections_present` with no activation or recovery action. If natural quiescence occurs, the existing installer runs its baseline real-Codex canary, repeats the five-sample gate, activates the exact candidate, requires health, policy header `2`, and real communication, and invokes the same manual recovery tool on any failure.
