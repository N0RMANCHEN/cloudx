# Architecture

## Local Component

The local artifact owns two entrypoints:

- `codexx`: named `CODEX_HOME` selection and account lifecycle
- `cloud`: cloud tunnel, remote health check, cloud Codex launch, credential import, and update administration

`cloud codex` resolves the official Codex binary, negotiates the remote protocol when possible, acquires a lease from the single local tunnel broker, and launches Codex with an isolated Cloudx `CODEX_HOME`. The scoped gateway credential is stored only in that profile's mode-0600 `auth.json`; sessions, session index, and skills are shared by explicit symlink. No prompt or behavior instructions are injected.

The broker is the only tunnel owner. A filesystem lock prevents competing brokers, lease records track active Codex processes, and stale leases are reclaimed. The broker rebuilds only when its SSH child exits or the local forward is no longer listening. HTTP health uses a wider timeout and reports degradation without terminating the tunnel.

## Cloud Component

The cloud artifact owns:

- a version and capability handshake
- the canonical credential parser and transactional importer
- secret-free gateway and account health publication
- a secret-free, read-only Phi Mesh compatibility profile that references existing public contracts
- a secret-free Phi cloud consumer credential policy with a gateway-only audience and no Cloudx administrative authority
- a migration-only, non-authorizing HTTP importer stop-gate evidence evaluator
- versioned install, stage, activate, and rollback helpers

CLIProxyAPI remains the gateway runtime. Cloudx checks its contract but does not bundle or silently upgrade it.

## Shared Contracts

JSON contracts in `shared/contracts/` are the only cross-endpoint source dependency. Runtime communication uses JSON over SSH command stdout/stdin. HTTP is not required for Cloudx administration.

## Failure Domains

User-facing errors preserve four distinct domains:

- local Codex process
- SSH tunnel or remote helper
- gateway HTTP response, including 502
- upstream account or provider availability

Retry policy is bounded. Rebuilding a tunnel cannot conceal a confirmed gateway response.
