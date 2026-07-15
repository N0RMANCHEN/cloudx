# Cloudx

Cloudx keeps local Codex local while providing a minimal, recoverable connection to a personal cloud gateway.

```text
official local Codex
        |
        | cloud codex
        v
singleton tunnel broker -> Cloudx remote helper -> CLIProxyAPI

cloud import -> SSH stdin -> Cloudx importer -> configured auth directory
```

## Commands

```bash
# The official local product remains unchanged.
codex

# Select a local Codex account home in the current shell.
eval "$(codexx soul0)"
codex

# Run local Codex through the cloud gateway.
cloud codex
cloud codex --check

# Import gateway credentials without exposing an HTTP import endpoint.
cloud import credentials.json --dry-run
cloud import credentials.json
```

`codexx` deliberately has only account selection and account lifecycle commands. Pool management, task governance, agents, remote clients, and the former control plane are outside this product.

## Repository Layout

- `local/`: macOS client, `codexx`, `cloud`, and local updater
- `cloud/`: Linux remote helper, importer, health publisher, and deployment templates
- `shared/contracts/`: versioned JSON contracts
- `prompts/`: reviewed operational and engineering prompt templates
- `docs/`: product truth, architecture, operations, migration, and release policy

Build both artifacts with `./build.sh`. Validate the repository with `./verify.sh`.

No install command in this repository activates a release automatically. See `docs/operations.md` for side-by-side staging and recovery.

See `docs/command-surface.md` for the accepted `codexx`, local CPA, cloud gateway, legacy recovery, and signed-update interactions during migration.
