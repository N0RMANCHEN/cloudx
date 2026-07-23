# M4B Natural-Traffic Completion

Date: 2026-07-23

This audit closes the remaining M4B production-behavior matrix without changing a process, service, listener, release selector, credential, archive, watcher input, or proxy configuration. It combines one new read-only natural-traffic observation with the retained secret-free receipt from accepted rollback-bounded transaction `20260719T102932Z-aee5d40f`.

## Natural Business Concurrency

The current cloud CPA is exact policy8 SHA-256 `4dfa561451662ca5deae566f6fcfdc32bec7f42590439fa053000c4b84f915c0`. Policy8 composes the accepted process-global two-slot middleware and has run continuously as PID `1871934`, restart count `0`, since 2026-07-22 19:04:40.

The CPA journal records a websocket `client connected` event only after `/v1/responses` has entered the proxied business handler and a matching `upstream execution session closed` event before that handler releases its slot. Aggregate lifecycle analysis from process start found:

- opened natural websocket business sessions: `40`
- closed sessions: `40`
- maximum simultaneously admitted sessions: `2`
- duplicate opens: `0`
- unmatched closes: `0`
- sessions still open at the end of observation: `0`

No request body, account identity, credential filename, token, response content, or websocket identifier entered the result. This is direct production observation of admitted business concurrency, not inference from the public policy header alone.

## Retained M4B Matrix

The root-only accepted transaction receipt and its individual evidence documents prove the remaining requirements:

| Requirement | Production evidence |
| --- | --- |
| Idle maintenance creates no probes | `probeGate=not_triggered`, `probeConcurrency=0`, trigger absent, CPA unchanged. |
| Aggregate failure calibrates above business concurrency two | Three real weekly-limited credentials naturally converged to upstream `model_cooldown` within three business attempts; policy5 emitted the stable identity-free trigger, the watcher consumed it, and incident probing reached concurrency `3` while public business policy remained `2`. |
| Weekly quota creates no archive | Three real weekly-limited samples classified limited `3`, archived `0`; the aggregate sweep again archived `0`. |
| Provisional refreshable 401 creates no archive | Isolated real network probe reported provisional 401 with archived `0`. |
| One conclusive permanent result archives exactly one digest match | Isolated non-refreshable 401 reported `permanentArchived=1` and `digestMatched=true`. |
| Exact restore is safe | The same receipt reported `restored=1`, active and archive state restored, a real HTTP `200` policy-`2` canary passed in one attempt, and CPA PID/restart state remained unchanged. |

The accepted transaction elapsed aggregate phase was `9.045` seconds, retained raw credential data nowhere in transaction output/state, restored the useful baseline, returned the archive manifest to `45`, and ended with empty failure input and absent trigger.

## Decision

M4B's natural-traffic policy matrix is accepted. The production runtime has directly demonstrated a maximum of two admitted business sessions, while the independently triggered incident sweep can exceed that ceiling without granting business traffic more slots. Quota and provisional evidence remain non-authorizing; one conclusive permanent result archives exactly one digest-bound record; exact restore returns it safely.

This decision is independent of current capacity. The separately recorded 2026-07-23 active-pool diagnosis found no presently observed usable capacity in the eleven-record pool. M4B acceptance neither promotes any of the 45 shadow records nor authorizes a credential, service, or release mutation.
