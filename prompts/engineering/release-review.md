# Release Review Prompt

Owner: Cloudx release engineering

## Purpose

Review fresh release evidence before an operator decides whether to activate.

## Input

- signed manifest verification result
- source commit and clean-tree evidence
- local, cloud, contract, downgrade, tamper, and rollback test results
- staged endpoint handshake
- canary plan and offline rescue verification

## Instructions

Report missing or stale evidence as a blocker. Treat automatic activation, an unverified artifact, unknown protocol compatibility, production service restart, or unavailable rollback as blockers. This review is advisory and cannot authorize activation.

## Output

Return JSON with `schema`, `verdict`, `blockers`, `warnings`, `evidence`, and `operatorDecisionRequired`. Schema is `cloudx.prompt.release-review.v1`; `operatorDecisionRequired` is always `true`.
