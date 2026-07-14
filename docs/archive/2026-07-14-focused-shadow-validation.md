# 2026-07-14 Focused Shadow Validation

This document records repeated classification checks and before/after continuity evidence without a fixed-duration sampling gate.

## Repeated Classification Checks

The read-only adapter was checked against at least two distinct legacy observations:

1. Total 65, available 40, limited 0, unavailable 0, unobserved 25.
2. Total 65, available 39, limited 0, unavailable 0, unobserved 26, observed at `2026-07-14T15:11:45.189247Z`.

For both observations:

- adapted total equaled legacy total;
- adapted available equaled legacy ready plus warning;
- adapted limited equaled legacy limited;
- legacy failed remained unobserved and was not guessed to be unavailable;
- no account identity or credential entered the aggregate output.

The timer remained enabled and active, and a manual oneshot run completed with result `success` and exit status `0`.

## Local Continuity

Before and after the focused action, the running Codex PID set was exactly:

`45333, 74770, 79772, 86256, 88768`

Local port `18317` had no listener before or after. No Codex session or process was terminated.

## Cloud Continuity

Before and after the focused action:

- `cliproxy.service` retained PID `586892`, restart count `0`, and active timestamp `98063220486`.
- `codex-import.service` retained PID `133756`, restart count `0`, and active timestamp `43952803944`.
- The production auth directory retained metadata `131173:1783989250:1783989250:700:cliproxy:cliproxy`.

No production auth write, gateway restart, importer restart, release activation, or legacy listener change occurred.
