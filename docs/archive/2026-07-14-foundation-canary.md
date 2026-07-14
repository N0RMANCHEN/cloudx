# 2026-07-14 Foundation Canary

This document records fresh evidence for the initial Cloudx repository implementation. It does not declare a production activation.

## Repository Verification

- Architecture gate: passed.
- Python regression suite: 29 tests passed on the local Python 3.9 runtime.
- Deterministic local and cloud zipapp builds: passed.
- Ed25519 release manifest verification: passed.
- Signed stable-index check: passed and did not stage or activate a release.

## Shadow Cloud Evidence

- The cloud helper ran only from `/tmp` with a `/tmp` auth directory, lock, health path, and scoped credential.
- Handshake selected protocol v1 and reported the existing gateway healthy.
- `cloud import --dry-run` accepted a fake `payload.accounts` fixture.
- A shadow write created one deterministic mode-0600 file.
- Repeating the same request wrote zero files and reported one skipped record.
- No production auth directory or service unit was changed.

## Tunnel Broker Evidence

- The Cloudx broker selected public port `23091`; the legacy port `18317` was not bound or changed.
- Two unit-test leases shared one broker and one SSH owner.
- Repeated HTTP probe failures left the SSH PID and generation unchanged.
- A real canary SSH child was terminated deliberately.
- The stable relay listener still accepted a TCP connection while the SSH backend was down.
- The next lease rebuilt only the SSH backend, advanced generation from 1 to 2, retained the public listener, and returned gateway HTTP 200.

## Complete Model Request

The first request identified that official Codex requires the scoped key in its isolated `CODEX_HOME/auth.json`, not only in process environment. After adding an atomic mode-0600 Cloudx auth file, the complete request returned exactly:

```text
CLOUDX_BROKER_CANARY_OK
```

## Cleanup

The canary broker was stopped with no active leases. Local temporary state, the fake import fixture, the cloud `/tmp` helper, scoped credential, and shadow auth directory were removed. The legacy tunnel and production cloud services were not restarted or modified.
