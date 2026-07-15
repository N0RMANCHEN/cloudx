# Phi Boundary

Phi is a separate product and repository.

## Cloudx-Owned

- gateway integration and readiness
- credential import and account health classification
- reversible credential quarantine with an audit trail
- `cloudx.health.v1`

## Phi-Owned

- mail commands and replies
- Codex goal recovery or watchdog behavior
- DeepSeek and other Phi provider balance monitoring
- human-facing notifications
- an explicit repair assistant that may prepare a branch or pull request

## Shared Rule

Phi may read `/run/cloudx/health.json` or execute `cloudx-remote health --json` with a scoped identity. The signal contains counts and status only. Phi must not read Cloudx keys, auth files, account identities, or release directories.

The M4 target is the exact `cloudx.health.v1` schema produced by a signed Cloudx artifact. The older `/var/lib/cloudx/health/v1.json` document with `contract: cloudx.health` and `schemaVersion: 1` is sanitized migration evidence, but it is not the Cloudx runtime contract and cannot satisfy the final consumer gate.

Cloudx never imports Phi modules and never requires Phi for routing, import, health, recovery, update, or rollback.

The legacy unattended repair timer that edits a checkout, deploys a parser, restarts the importer, and merges a branch is not a supported target behavior. Its replacement is diagnostic evidence plus an operator-reviewed pull request.
