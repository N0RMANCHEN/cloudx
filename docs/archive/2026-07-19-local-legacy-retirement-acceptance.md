# Local Legacy Retirement Acceptance

Date: 2026-07-19

Source commit `2d13923043be7e88f78729fadb3de2529f50c9f9` was pushed before production use. The three operator scripts were extracted into a private immutable bundle and matched the committed SHA-256 values. No production transaction ran from the Git checkout.

## Stale Exec Retirement

- Decision digest: `sha256:b6007e6b15dc10d2a22af41bc8eb12c62ffe66c6411e1e2df8fb96fb4508c956`.
- Two PPID-1 legacy exec parents and their two official Codex children met the thirty-day, revoked-stdio, zero-socket, and sustained-CPU evidence contract.
- Both groups exited from `SIGTERM`; `SIGKILL` was not sent.
- No file changed and no service restarted.

## Idle Control Migration

- Decision digest: `sha256:9bf5f1410d307bb2d074d48fdf93c106f84aae98bf8ac8120778edbb3afeb03b`.
- The legacy control service had zero active connections and more than the required thirty-day state-idle window.
- One bounded restart moved it from PID `729` to PID `48303` on the verified retained recovery runtime.
- Port `8765` returned the expected unauthenticated `401`; retained and live recovery checks both passed before package quarantine.
- Private rollback backup: `20260719T150309Z`.

## Package Quarantine

- Private quarantine backup: `20260719T150428Z`.
- Exactly the legacy runtime, launcher, and recovery entrypoint moved into same-filesystem private quarantine after a final no-process/CPA continuity recheck.
- Native import dry-run, fresh-shell API/native return, official Codex/Git, Cloudx entrypoints/hook, and signed `0.1.21/0.1.20` selectors passed.
- The standalone package recovery check passed. The retained control recovery remains ready; live-mode control recovery now correctly requires restoring the package first.
- No process was terminated and no service restarted by package quarantine.

## Communication Continuity

The external local CPA remained PID `61859` with port `8317` listening throughout all three transactions. Real official-Codex-through-CPA canaries passed before retirement, after control migration, and after package quarantine. Port `8765` remained healthy after the one intentional control-service reload. No CPA launcher, binary, configuration, account, credential, Cloudx selector, or active Codex communication path changed.
