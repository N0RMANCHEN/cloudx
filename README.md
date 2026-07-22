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
codexx import credentials.json --dry-run
codexx import credentials.json
codexx import credentials.json --json
codexx cloud import credentials.json --dry-run
codexx cloud import credentials.json
codexx cloud import credentials.json --json

# Explain the most recent retained local/cloud API failure without exposing raw requests or credentials.
codexx diagnose
codexx api diagnose
codexx cloud diagnose
codexx diagnose --json

# Upgrade exactly one Cloudx endpoint from the signed stable release.
# When both endpoints need an update, upgrade cloud first.
codexx cloud upgrade --check
codexx cloud upgrade
codexx upgrade --check
codexx upgrade

# Return to the native profile.
codexx exit

# Endpoint-aware signed installation; the plan prints its exact confirmation.
./install

# Trust-recovery staging for a lagging endpoint; selectors and runtime stay unchanged.
./install local --version <signed-version> --stage-only
```

`codexx` deliberately stays small: account selection/lifecycle, explicit local/cloud import, explicit signed endpoint upgrades, and read-only API failure diagnosis. Pool management, task governance, agents, remote clients, and the former control plane are outside this product.

Interactive local and cloud imports share one readable result summary with explicit status, destination, counts, verification scope, and safe failure reasons. Local and cloud `--json` expose their versioned import contracts for automation. The local adapter writes only to the configured external CPA auth directory; it does not manage or restart that service.

Tokenless Sub2API `agentIdentity` input is fail-closed on both destinations: Cloudx validates its Ed25519 signing metadata, fingerprints each runtime/key pair independently, and discards synthetic bearer/task state. Local import requires `cloudx.local-cpa-capabilities.v1` plus the live loopback header; cloud import requires `cloudx.cloud-cpa-capabilities.v1` plus the same `codex-agent-identity-v1` header on the configured gateway `/healthz`. Each check binds the exact external binary digest and repeats on every import, so an external CPA update automatically invalidates stale evidence. Import itself never builds, patches, replaces, or restarts the service that performs task registration and `AgentAssertion` signing.

API diagnosis distinguishes explicit deactivation, exhausted allowance, transient rate limiting, relogin, access denial, gateway failures, and unknown evidence. It never rewrites the official Codex command or gateway response, and a later generic `no auth available` response does not erase a recent definitive root cause.

## Repository Layout

- `local/`: macOS client, `codexx`, `cloud`, and local updater
- `cloud/`: Linux remote helper, importer, health publisher, and deployment templates
- `shared/contracts/`: versioned JSON contracts
- `prompts/`: reviewed operational and engineering prompt templates
- `docs/`: product truth, architecture, operations, migration, and release policy

Build both artifacts with `./build.sh`. Validate the repository with `./verify.sh`.

No background check or staging command activates a release. `codexx upgrade`, `codexx cloud upgrade`, and an exactly confirmed installer invocation are explicit operator activation actions. See `docs/operations.md` for side-by-side staging and recovery.

See `docs/command-surface.md` for the accepted `codexx`, local CPA, cloud gateway, legacy recovery, and signed-update interactions during migration.
