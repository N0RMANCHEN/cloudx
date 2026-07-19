# Cloud Legacy Runtime Retirement Acceptance

Date: 2026-07-19

The final cloud M5 runtime transaction ran from root-only operator bundle commit `1afa591d09b993fc35bb31507a485641a54acfce`. The deployed `quarantine_cloud_legacy_runtime.py` SHA-256 was `5c5fe401e51fe514d8bab848223727c318173fdf62e8aab687c6a03ba6a47299`, matching the pushed source before production use.

## Decision

- Decision digest: `sha256:d0400006c2f8e47840717ff04bf7618f32f55671b4bad9e3fbf978451536db4a`.
- The bounded live tree contained 281 regular files, 4,409,780 bytes, and aggregate tree SHA-256 `93bbc3b2243fc9ad15a5ea5babe1780b1b4efc1cc3a64da6b9c3e5074145aad1`.
- Live process references and cron references were zero.
- Exactly five retained legacy source files referenced the package, and their only systemd consumers were the three declared dormant importer/repair/quota services. Their timers and services were inactive/disabled or inactive/static as required.
- The complete root-only HTTP-importer stop archive passed its SHA-256 manifest and contained the full `codexx_app` runtime.
- Signed cloud self-check, public health/handshake, gateway, selectors, signed bridge timer, old-exporter timer state, and Phi formal-health timer passed the decision gate.

## Quarantine

The transaction moved only `/opt/codex-gateway/codexx_app` into root-only quarantine `20260719T152638Z` on the same filesystem. It wrote and verified a standalone recovery tool before the move. The recovery `--check` passed afterward with all 281 files.

The live path is absent but the runtime is not deleted. The existing importer runtime archive remains intact as a second recovery source. Restoring either code copy grants no authority to start or enable an old service.

## Continuity

- Gateway PID `1746294`, restart count `0`, and active state were unchanged.
- Cloud selectors remained signed `0.1.21/0.1.20`.
- `codex-import.service` remained inactive/disabled with PID zero and port `8780` closed.
- `cloudx-legacy-health-bridge.timer` remained active/enabled; `cloudx-health-contract.timer` remained inactive/disabled; `phi-cloudx-health.timer` remained active/enabled.
- Public health continued to report gateway healthy and importer ready; handshake continued to report gateway healthy on product `0.1.21`.
- No service lifecycle command or daemon reload ran. No credential, account, gateway, CPA, Phi, release selector, or rollback archive changed.
- A real local official-Codex-through-CPA canary passed after cloud retirement with local CPA PID `61859` unchanged.
