# Cloudx

Cloudx keeps local Codex local while providing a minimal, recoverable connection to a personal cloud gateway.

```text
official local Codex
        |
        | codexx cloud; codex
        v
singleton tunnel broker -> Cloudx remote helper -> CLIProxyAPI

codexx cloud import -> SSH stdin -> Cloudx importer -> configured auth directory
```

## Commands

```bash
# The official local product remains unchanged.
codex

# Select a local Codex account home in the current shell.
codexx soul0
codex

# Select local CPA mode, then run official Codex.
codexx api
codex

# Select cloud mode, then run official Codex.
codexx cloud
codex

# Import credentials into local CPA or the cloud gateway.
codexx import credentials.json
codexx cloud import credentials.json --dry-run
codexx cloud import credentials.json
codexx cloud import credentials.json --json

# Explain the most recent retained local/cloud API failure without exposing raw requests or credentials.
codexx diagnose
codexx api diagnose
codexx cloud diagnose
codexx diagnose --json

# Return to the native profile.
codexx exit

# Endpoint-aware signed installation; the plan prints its exact confirmation.
./install
```

`codexx` deliberately stays small: account selection/lifecycle, explicit local/cloud import, and read-only API failure diagnosis. Pool management, task governance, agents, remote clients, and the former control plane are outside this product.

Interactive local and cloud imports share one readable result summary with explicit status, destination, counts, verification scope, and safe failure reasons. Cloud `--json` exposes the underlying versioned import contract for automation.

API diagnosis distinguishes explicit deactivation, exhausted allowance, transient rate limiting, relogin, access denial, gateway failures, and unknown evidence. It never rewrites the official Codex command or gateway response, and a later generic `no auth available` response does not erase a recent definitive root cause.

## Repository Layout

- `local/`: macOS client, `codexx`, `cloud`, and local updater
- `cloud/`: Linux remote helper, importer, health publisher, and deployment templates
- `shared/contracts/`: versioned JSON contracts
- `prompts/`: reviewed operational and engineering prompt templates
- `docs/`: product truth, architecture, operations, migration, and release policy

Build both artifacts with `./build.sh`. Validate the repository with `./verify.sh`.

No install command in this repository activates a release automatically. See `docs/operations.md` for side-by-side staging and recovery.

See `docs/command-surface.md` for the accepted `codexx`, local CPA, cloud gateway, legacy recovery, and signed-update interactions during migration.
