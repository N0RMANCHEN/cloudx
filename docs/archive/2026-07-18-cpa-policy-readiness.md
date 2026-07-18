# CPA Credential Failure And Concurrency Policy Readiness

## Scope

This batch addresses two operator-requested behaviors on the existing external local and cloud CPA revisions:

1. never allow more than two proxied API requests to execute concurrently in one CPA process
2. reversibly archive an auth record only after confirmed permanent authentication failure, never because of weekly quota or another transient failure

It does not upgrade CLIProxyAPI, replace the official `codex` command, activate a Cloudx release, durably stage a CPA candidate, edit a launcher or unit, move a production auth file, or restart a production service.

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

- Cloudx `./verify.sh`: architecture gates passed, 352 tests passed, local/cloud 0.1.16 artifacts built.
- CPA focused Go tests passed for both exact revisions: global two-slot middleware, control-endpoint exclusion, permanent-auth receipt confirmation, weekly-quota exclusion, success cleanup, repeated no-refresh 401 handling, and local fast-tier mapping.
- The cloud Linux candidate was copied only to remote `/tmp`; its remote SHA-256 and `-h` runtime identity matched. Active `cliproxy.service` retained PID `977036`, restart count `0`, and active/running state.
- The local Darwin candidate ran only on `127.0.0.1:18427` with an empty temporary auth directory and a temporary API key. Two incomplete authenticated requests occupied both slots. A third request with a complete body produced no response while those slots remained occupied; after the first request completed, the third proceeded. All three responses reported `X-CPA-Max-Concurrent-API-Requests: 2`. The temporary process was stopped and no listener remained.
- Production local CPA retained PID `38189`. No production account, archive, launcher, config, port, Cloudx selector, broker, Codex process, or service was changed.

## Remaining Gates

1. publish and activate the signed Cloudx release containing both receipt consumers and retain signed N-1
2. durably stage local and cloud CPA candidates using the separate exact `STAGE ... CPA POLICY ...` confirmations
3. activate cloud first and local second using the distinct exact `ACTIVATE ... CPA POLICY ...` confirmations
4. accept natural-traffic evidence for maximum-two concurrency, quota non-archive, permanent-failure archive, and exact restore

No build, test, `/tmp` copy, or readiness evidence above grants those later actions.
