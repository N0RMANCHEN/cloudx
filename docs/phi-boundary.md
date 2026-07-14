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

Cloudx never imports Phi modules and never requires Phi for routing, import, health, recovery, update, or rollback.

The legacy unattended repair timer that edits a checkout, deploys a parser, restarts the importer, and merges a branch is not a supported target behavior. Its replacement is diagnostic evidence plus an operator-reviewed pull request.
