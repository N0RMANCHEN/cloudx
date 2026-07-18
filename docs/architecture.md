# Architecture

## Local Component

The local artifact owns two entrypoints:

- `codexx`: named `CODEX_HOME` selection and account lifecycle
- `cloud`: cloud tunnel, remote health check, cloud Codex launch, credential import, and update administration

`cloud codex` resolves the official Codex binary, negotiates the remote protocol when possible, acquires a lease from the single local tunnel broker, and launches Codex with an isolated Cloudx `CODEX_HOME`. The scoped gateway credential is stored only in that profile's mode-0600 `auth.json`; sessions, session index, and skills are shared by explicit symlink. No prompt or behavior instructions are injected.

The broker is the only tunnel owner. A filesystem lock prevents competing brokers, lease records track active Codex processes, and stale leases are reclaimed. The broker rebuilds only when its SSH child exits or the local forward is no longer listening. HTTP health uses a wider timeout and reports degradation without terminating the tunnel. A passive response observer classifies only bounded gateway-to-client bytes and retains enumerated, secret-free failure evidence; it never changes forwarding or stores request content. Generic pool exhaustion cannot replace a recent definitive upstream cause.

Local API/CPA diagnosis uses the external gateway's retained error files as a compatibility boundary. It reads only bounded response sections, not request bodies or headers. Both local and cloud modes emit `cloudx.api-diagnosis.v1`; when evidence is absent, reachability remains distinct from upstream account usability.

Local CPA maintenance scans only top-level auth JSON. It retains expired access tokens when a refresh token exists, consumes only fresh `cloudx.cpa-auth-failure.v1` receipts bound to the current file digest, and moves accepted records into a private same-filesystem archive with a rollback-safe manifest. `codexx api restore` requires the exact archived filename. The external CPA is neither restarted nor managed by these commands.

Receipt consumption has a fast path independent of full account probing. The local maintenance LaunchAgent watches both the private receipt directory and the aggregate sweep trigger, with a two-minute missed-trigger fallback. Cloud uses distinct signed systemd path/oneshot pairs: the receipt consumer is network-isolated, while the aggregate `auth_unavailable` consumer is network-capable and first gates the declared HTTPS/proxy dependency. Full sweeps never run periodically without a trigger, use a separately bounded high-concurrency probe pool rather than the two-request business limiter, deduplicate identical credentials, and release the archive lock while waiting on the network. Watcher activation is a separate exact-confirmation transaction and never restarts CPA, Codex, or Phi.

## Cloud Component

The cloud artifact owns:

- a version and capability handshake
- the canonical credential parser and transactional importer
- secret-free gateway and account health publication
- secret-free capacity classification with explicit stale, unknown, probe-failure, and compatibility states
- a secret-free, read-only Phi Mesh compatibility profile that references existing public contracts
- a secret-free Phi cloud consumer credential policy with a gateway-only audience and no Cloudx administrative authority
- a bounded single-consumer traffic policy without Task, scheduling, or queue ownership
- a migration-only, non-authorizing HTTP importer stop-gate evidence evaluator
- versioned install, stage, activate, and rollback helpers

CLIProxyAPI remains the gateway runtime. Cloudx checks its contract but does not bundle or silently upgrade it.

The optional operator-built CPA policy patch is pinned independently to each already deployed upstream commit. Its process-global middleware holds at most two proxied API requests until each handler, including streaming handlers, returns. Its account failure observer writes no token, request, response, email, or account label; it emits only the top-level auth filename, SHA-256, enumerated permanent reason, evidence count, fixed non-quota flags, and observation time into a private directory. A final aggregate `auth_unavailable` emits a separate identity-free trigger, and successful traffic emits an identity-free available observation. Cloudx revalidates every field before reversible archive and owns all probing outside CPA's business semaphore.

## Shared Contracts

JSON contracts in `shared/contracts/` are the only cross-endpoint source dependency. Runtime communication uses JSON over SSH command stdout/stdin. HTTP is not required for Cloudx administration.

## Failure Domains

User-facing errors preserve four distinct domains:

- local Codex process
- SSH tunnel or remote helper
- gateway HTTP response, including 502
- upstream account or provider availability

Within the upstream domain, explicit account deactivation, allowance exhaustion, transient rate limiting, login invalidation, and permission denial remain distinct. A generic 503 with no usable account is a masking condition, not authority to infer one of those causes.

Retry policy is bounded. Rebuilding a tunnel cannot conceal a confirmed gateway response.
