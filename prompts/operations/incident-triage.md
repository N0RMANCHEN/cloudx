# Incident Triage Prompt

Owner: Cloudx operations

## Purpose

Classify a sanitized `cloud codex --check` report without changing the system.

## Input

- local process exit and timing
- SSH tunnel state and sanitized stderr category
- remote handshake and health documents
- gateway HTTP status and request correlation ID
- recent secret-free service state

Never include API keys, tokens, account names, email addresses, auth file paths, raw request bodies, or session content.

## Instructions

1. Separate local process, tunnel, remote helper, gateway, and upstream evidence.
2. State only conclusions directly supported by supplied evidence.
3. Identify the earliest failed boundary.
4. Propose reversible diagnostic actions. Do not propose restarts, key rotation, auth deletion, release activation, or tunnel termination.
5. Stop and request an operator when evidence is stale, contradictory, or would require a production write.

## Output

Return JSON with `schema`, `classification`, `evidence`, `unknowns`, `safeChecks`, and `operatorRequired`. Use schema value `cloudx.prompt.incident-triage.v1`.
