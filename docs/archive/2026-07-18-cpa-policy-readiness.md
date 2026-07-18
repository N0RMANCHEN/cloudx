# CPA Credential Failure And Concurrency Policy Readiness

## Scope

This batch addresses two operator-requested behaviors on the existing external local and cloud CPA revisions:

1. never allow more than two proxied API requests to execute concurrently in one CPA process
2. reversibly archive an auth record only after confirmed permanent authentication failure, never because of weekly quota or another transient failure

This evidence now includes the separately confirmed durable side-by-side staging of both exact CPA candidates and a later separately authorized cloud credential import. The policy stage itself did not change credentials. The later import atomically wrote ten normalized records without activating a Cloudx release or CPA candidate, editing a launcher or unit, or restarting a production service.

## Exact Runtime Baseline

- local CPA: v7.0.1 custom fast-service-tier build, upstream commit `15ac7fb9324095330e60f522147b8a8e81f16ab5`, active binary SHA-256 `cf9641b3e50ae486aec1698dec88f735589680f9ae98558c29cde184daac3a96`, PID `38189`
- cloud CPA: v7.2.71, upstream commit `5b7f2361ee27d195f6514dde08656f6e4773a9a4`, active binary SHA-256 `1d0abbc6316b1869f74896109c0efb5e19c8197b8226f48a74212ed0a6f5a39d`, PID `977036`, systemd restart count `0`

Upstream standalone CPA exposes retry, cooldown, routing, and refresh-worker controls but no enforced global inference-request ceiling. The open upstream concurrency request is [issue 4031](https://github.com/router-for-me/CLIProxyAPI/issues/4031); the related provider limiter remains an unmerged [pull request 4032](https://github.com/router-for-me/CLIProxyAPI/pull/4032). Cloudx therefore pins policy patches to the two exact deployed commits rather than silently upgrading either endpoint.

## Failure Semantics

The CPA patch never moves or deletes credentials. It can emit a private `cloudx.cpa-auth-failure.v1` receipt only when two pieces of evidence occur within ten minutes and at least one is a conclusive permanent authentication signal. The receipt contains only a top-level auth filename, exact file SHA-256, enumerated reason, evidence count, fixed `permanentAuthFailure=true`, fixed `weeklyQuota=false`, and observation time.

Cloudx independently rejects stale, malformed, symlinked, oversized, nested, non-confirmed, quota-marked, or digest-mismatched receipts. Accepted records move atomically into a private same-filesystem archive with a rollback-safe manifest. Exact restore requires repeating the archived filename.

The following never grant archive authority:

- weekly allowance or quota exhaustion
- ordinary HTTP 429 or transient rate limiting
- network failure or timeout
- HTTP 5xx
- an expired access token when a refresh token remains
- one provisional 401 with a refresh credential

## Deterministic Candidates

- local Darwin/arm64: `7.0.1-codexx-fast-service-tier-cloudx-policy.1`, SHA-256 `70439565f25307c22fd93c8aa897871489dc32b1700ebc2390c07896e7b6de01`, 41,468,178 bytes
- cloud Linux/amd64: `7.2.71-cloudx-policy.1`, SHA-256 `67baab69ecc507c794f1336197a78e52c0126679a780e1c064cae453966c6a67`, 45,314,210 bytes

Each candidate was rebuilt independently from a fresh clean exact checkout with Go 1.26.0, the committed patch digest, fixed build identity, focused Go tests, `CGO_ENABLED=0`, `-trimpath`, and no VCS build metadata. Both independent builds matched the pinned bytes exactly. The local patch also retains the existing `fast -> priority` Codex service-tier mapping.

## Acceptance Evidence

- Final source and CI verification: architecture gates passed, 360 tests passed, and local/cloud 0.1.16 artifacts built from exact release source `ec77369a990418f2a990874d1d7bd4b9d2c7fe04`.
- CPA focused Go tests passed for both exact revisions: global two-slot middleware, control-endpoint exclusion, permanent-auth receipt confirmation, weekly-quota exclusion, success cleanup, repeated no-refresh 401 handling, and local fast-tier mapping.
- The cloud Linux candidate was copied only to remote `/tmp`; its remote SHA-256 and `-h` runtime identity matched. Active `cliproxy.service` retained PID `977036`, restart count `0`, and active/running state.
- The local Darwin candidate ran only on `127.0.0.1:18427` with an empty temporary auth directory and a temporary API key. Two incomplete authenticated requests occupied both slots. A third request with a complete body produced no response while those slots remained occupied; after the first request completed, the third proceeded. All three responses reported `X-CPA-Max-Concurrent-API-Requests: 2`. The temporary process was stopped and no listener remained.
- During build, isolated canary, and durable-stage acceptance, production local CPA retained PID `38189`. No production account, archive, launcher, config, port, Cloudx selector, broker, Codex process, or service was changed by those actions.
- After the exact `STAGE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.1 70439565f253` confirmation, the local candidate was durably staged at `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.1/cli-proxy-api`. Its manifest records 41,468,178 bytes and SHA-256 `70439565f25307c22fd93c8aa897871489dc32b1700ebc2390c07896e7b6de01`; stage output reported `externalServiceRestarted=false`, and PID `38189` continued to execute the baseline `/Users/hirohi/.local/bin/cli-proxy-api`.
- After the exact `STAGE CLOUD CPA POLICY 7.2.71-cloudx-policy.1 67baab69ecc5` confirmation, the cloud candidate was durably staged at `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.1/cli-proxy-api`. Its manifest records 45,314,210 bytes and SHA-256 `67baab69ecc507c794f1336197a78e52c0126679a780e1c064cae453966c6a67`; stage output reported `externalServiceRestarted=false`, and `cliproxy.service` remained active/running with PID `977036`, restart count `0`, and baseline `/usr/local/bin/cli-proxy-api` selection.
- After the exact `PUBLISH CLOUDX 0.1.16 SIGNED RELEASE WITHOUT ACTIVATION` confirmation, annotated tag `v0.1.16` and workflow `29640659405` published immutable artifact ref `9513ff87b3b2e45d2b3609f0746248a7422d34b2` and stable ref `bba9f619fc2d3e57cbd1b2808fe97ac58e805aef`. Fresh clones and seven downloaded GitHub assets passed current-root verification, previous-root rejection, byte comparison, both component self-checks, stable-index acceptance, and selector-free `staged -> already-staged` transactions. No real endpoint was staged or activated.
- After the exact `INSTALL CLOUDX CLOUD 0.1.16` confirmation, the canonical installer staged and activated the immutable cloud artifact from a complete hash-verified offline Git bundle after direct cloud-host GitHub fetch failed without mutation. Cloud now retains `current=0.1.16`, `previous=0.1.13`; self-check, release status, and handshake passed. A natural CPA-health timer invocation exited `0` with truthful aggregate `probe_error`. CPA PID `977036`, restart count `0`, 45 auth files, zero archived files, and the absent pre-policy failure-receipt directory were preserved.

## Communication Continuity And Cloud Import Evidence

- The exact OpenAI OAuth CPA-export wrapper was first rejected by installed Cloudx `0.1.13` because the outer `type=oauth` was treated as a provider. An in-memory, non-persistent normalization to Codex records produced an accepted dry-run for ten writes; the separately authorized atomic import then wrote ten records, and the repeated dry-run reported ten skipped with zero writes.
- The ten imported token records are bound to one `k12` workspace, contain no refresh token, and have access JWTs whose cryptographic expiry is still in the future. Real cloud traffic produced explicit upstream `deactivated_workspace` and then the scheduler-level `auth_unavailable` mask. At this readiness checkpoint they were not manually removed or archived. A later operator-authorized sequential probe classified all 45 cloud records through the declared proxy as explicit `deactivated_workspace` and reversibly archived all 45; see `2026-07-18-cloud-cpa-sequential-archive.md`.
- Cloud import and canary activity left `cliproxy.service` at PID `977036`, restart count `0`, and its baseline binary. A successful direct `soul0` official-Codex canary proves an independent non-CPA recovery path. A separate real official-Codex request through the current local `api` profile also passed before any local service action.
- Source now recognizes only the exact `platform=openai`, `type=oauth`, nested-credentials wrapper and retains rejection for another platform. Local activation now requires a real `api` Codex request before restart and after candidate selection; failure restores the original launcher/binary and requires the real request again. The default scheduler remains non-authorizing, delays an exactly confirmed local activation by 180 seconds, and runs from a private detached job so the CPA-backed authorizing turn can finish before restart.

## Remaining Gates

1. publish and activate signed Cloudx `0.1.17` cloud-first and local-second while retaining signed N-1
2. separately stage revised `.policy.2` candidates; retain the inactive staged `.policy.1` candidates as superseded evidence
3. activate `.policy.2` cloud first and local second using the distinct exact `ACTIVATE ... CPA POLICY ...` confirmations only after matching Cloudx `0.1.17` activation
4. accept natural-traffic evidence for maximum-two concurrency, quota non-archive, direct conclusive permanent-failure archive, and exact restore

No build, test, publication, `/tmp` copy, or readiness evidence above grants those later actions.
