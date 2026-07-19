# Local Legacy Retirement Acceptance

Date: 2026-07-19

Source commit `2d13923043be7e88f78729fadb3de2529f50c9f9` was pushed before the first three production transactions. Their scripts were extracted into a private immutable bundle and matched the committed SHA-256 values. Final control retirement ran from separately pushed commit `c747b96f95cd350e49e33b6355d6c1beaa57660f`; its exact script SHA-256 was `858a3dcb4bafb18741eafeccf35ba142b6489aa13d0dfa8f813ca624bee4db3d`. No production transaction ran from the Git checkout.

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

## Final Control Retirement

- Decision digest: `sha256:c0b54fd46466fbbb3fe317c18ea1f19711c981acde1e646492249917a27b8301`.
- The still-zero-connection control PID `48303` matched retained bundle `20260715T122545Z` and migration backup `20260719T150309Z`.
- A new recovery tool was prepared before `launchctl bootout`.
- Only `com.codexx.control` was unloaded, and only its LaunchAgent plist entered private quarantine `20260719T154900Z`.
- Port `8765` is closed, the LaunchAgent is not loaded, the live plist is absent, and the recovery `--check` reports ready.
- `SIGKILL` was not sent, no official Codex process was terminated, and no account or Cloudx selector changed.

## Communication Continuity

The external local CPA remained PID `61859` with port `8317` listening throughout all four transactions. Real official-Codex-through-CPA canaries passed before retirement, after control migration, after package quarantine, after cloud runtime quarantine, and after final control retirement. Port `8765` remained healthy during the migration phase and is intentionally closed after final retirement. No CPA launcher, binary, configuration, account, credential, Cloudx selector, or active Codex communication path changed. Final audit found zero live codex-plus processes, closed ports `18317` and `8765`, and a free local import advisory lock.
