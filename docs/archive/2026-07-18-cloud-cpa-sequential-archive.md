# Cloud CPA Sequential Probe And Archive

Date: 2026-07-18

## Operator Intent And Boundary

The operator first authorized archiving the cloud CPA account inventory, then clarified the intended durable mechanism: when the overall HTTPS/API path is unusable, Cloudx must probe accounts one at a time and archive only account-specific permanent failures. Quota exhaustion must be retained, and Phi must not become coupled to credential probing or mutation.

This authorized reversible cloud credential archive only after the sequential classification. It did not authorize credential deletion, CPA restart, CPA candidate activation, Cloudx release publication/activation, mihomo mutation, Phi mutation, or local-account mutation.

## Preflight

- active Cloudx cloud release: `0.1.16`, previous `0.1.13`
- active cloud CPA: PID `977036`, restart count `0`, baseline `/usr/local/bin/cli-proxy-api`
- active auth inventory: 45 top-level regular JSON files, zero symlinks
- archive inventory: zero credential JSON files, zero manifest entries, zero symlinks
- logical auth contexts: 45 across 45 files
- refresh-capable contexts: zero
- non-refreshable contexts: 45

## Root Cause

An interactive direct probe without the declared cloud proxy returned transport `ENETUNREACH` for both provider usage endpoints. The external CPA configuration and active dependency contract declare mihomo at loopback HTTP proxy `127.0.0.1:7890`; the installed CPA-health systemd unit also exports HTTP/HTTPS proxy variables.

Using that same proxy path produced this sanitized account-scoped result:

- ChatGPT usage endpoint: HTTP `402`, marker `deactivated_workspace`
- Codex usage fallback endpoint: HTTP `404`, no permanent or quota marker

Cloudx `0.1.16` recognized only HTTP `401` and `429` at this boundary. It discarded the bounded `402` error body, tried the fallback, and returned an unclassified probe. Its account scan also used a worker pool rather than the operator-requested one-at-a-time diagnosis. The earlier aggregate `probe_error` and zero archive were therefore a real implementation gap.

## Sequential Classification

A read-only diagnostic then used the declared mihomo path with account probe concurrency exactly one. It checked all 45 contexts and emitted aggregate progress only; no account name, credential, token, response body, or file path was printed.

Final classification:

- checked: 45
- explicit permanent invalid: 45
- reason: `deactivated_workspace` for all 45
- quota/weekly limited: 0
- usable: 0
- transport/provider/unknown: 0

Because every account had explicit account-specific permanent evidence and no refresh credential, all 45 met the corrected archive rule.

## Reversible Archive Transaction

The apply transaction held the existing CPA-health monitor lock for the complete classification and move sequence. For every account it:

1. read only a bounded regular top-level auth file;
2. recorded its SHA-256 before the HTTPS probe;
3. classified through the declared proxy with concurrency one;
4. revalidated the exact digest immediately before mutation;
5. used the installed Cloudx quarantine lock, same-filesystem atomic move, private manifest, directory fsync, and automatic per-entry rollback path.

The aggregate transaction result was:

- checked: 45
- eligible: 45
- archived: 45
- retained: 0
- reason: `sequential-probe-deactivated-workspace`
- reversible: true

No raw secret or account filename entered output or Git.

## Acceptance

- active auth inventory: zero regular JSON files, zero symlinks
- archive inventory: 45 credential JSON files, zero symlinks
- archive directory mode: `0700`
- every archived credential mode: `0600`
- manifest schema: `cloudx.cpa-quarantine.v1`
- manifest mode: `0600`
- manifest entries: 45
- all 45 original source paths absent
- cloud CPA: PID `977036`, restart count `0`, active/running on the baseline binary
- Cloudx cloud self-check: `0.1.16`, status `ok`
- release status: current `0.1.16`, previous `0.1.13`, status `active`
- handshake: gateway healthy, version `7.2.71`
- refreshed CPA-health aggregate: total `0`, archived in that later run `0`, no pending candidate

The later aggregate correctly describes the now-empty active pool; the retained private archive manifest is the source of truth for the 45 reversible moves.

## Source Correction And Revised Candidates

Repository development `0.1.17` now:

- accepts an explicit declared proxy URL and keeps the systemd proxy contract;
- gates account decisions on a no-account infrastructure/provider probe;
- skips all account archive decisions on transport/provider failure;
- probes accounts sequentially with concurrency one;
- reads bounded HTTP error bodies and recognizes `deactivated_workspace` plus the enumerated permanent-auth reasons;
- archives immediately after one conclusive account-scoped permanent result;
- retains quota/429, provisional refreshable 401, network/TLS/DNS/timeout/5xx, and unknown failures;
- revalidates the exact probed auth-file digest before reversible archive;
- accepts a fresh digest-bound permanent receipt with `failureCount=1`.

The exact CPA patches were revised without changing either upstream commit or the global two-request inference ceiling. Two independent clean builds produced identical bytes:

- local `7.0.1-codexx-fast-service-tier-cloudx-policy.2`: SHA-256 `f288838053f43a82c50d2ab23bcb096c627a848fdf662413544a483f908f236d`, 41,468,178 bytes
- cloud `7.2.71-cloudx-policy.2`: SHA-256 `7c9603a380f9fbd7bdbe1c8ecbf938504f6055677ba4d4de2cd7004398a02229`, 45,314,210 bytes

The previously staged `.policy.1` binaries remain inactive and retained as historical evidence. The `.policy.2` candidates are built only; they are not staged or active. Their activation contract requires signed Cloudx `0.1.17` on the matching endpoint.

## Phi Boundary

Cloudx owns infrastructure gating, account probing, failure classification, receipt consumption, archive, restore, and aggregate health. Phi may read `cloudx.health.v1` and notify the operator. Phi cannot read credentials, run the account probe, decide archive eligibility, consume private receipts, move/restore auth files, deploy Cloudx, or restart CPA.
