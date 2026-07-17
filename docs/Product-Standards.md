# Product Standards

## Supported Product Surface

Cloudx 0.x supports these durable behaviors:

1. Select native, `api`, `cloud`, or a named local Codex account mode with `codexx`.
2. Leave the official `codex` command untouched.
3. Hold a shell-owned broker lease for `codexx cloud`, then run the official Codex with plain `codex`.
4. Import local CPA credentials through the explicit migration adapter with `codexx import`.
5. Import cloud gateway credentials over SSH with `codexx cloud import`.
6. Install signed endpoint artifacts and the local shell source with `./install`.
7. Diagnose retained local or cloud API failure evidence without replacing `codex`, changing the gateway response, or exposing a credential or account identity.

`cloud codex` and `cloud import` remain supported compatibility commands during the migration window.

Remote handshake, health, release staging, and rollback exist to make those behaviors operable. They are not a general control plane.

The migration-only HTTP importer stop-gate evaluator accepts a bounded sanitized evidence contract and returns deterministic precondition blockers. It does not collect privileged host state, stop or disable a service, or grant authorization; every result keeps `serviceStop=false` and requires a separate operator-confirmed transaction.

## Product Invariants

- Single user and personal node first.
- Local execution remains local. `cloud codex` does not SSH into a remote Codex runtime.
- Account selection changes `CODEX_HOME`; it does not modify the official Codex executable.
- Cloud mode binds its tunnel lease to the selecting shell PID. `codexx exit`, another mode selection, or shell death releases that lease.
- The default local Codex profile and named profiles have independent authentication files.
- A single local broker owns the cloud SSH tunnel. Sessions acquire leases; they never monitor, kill, or rebuild the shared SSH process themselves.
- The broker uses a Cloudx-owned port distinct from the legacy bridge and never treats a transient HTTP probe failure as authority to kill an SSH tunnel.
- The broker may passively classify response bytes already crossing the cloud relay, but it stores only the secret-free diagnosis fields and never changes forwarded bytes. Local CPA diagnosis reads only bounded response sections from external gateway logs. A generic no-usable-account response cannot overwrite a recent definitive upstream cause, and insufficient evidence is never guessed to be quota exhaustion or deactivation.
- The existing legacy bridge remains a supported migration fallback until its removal has a separate, accepted roadmap item.
- Import and health code cannot require Phi.
- In the initial Personal Agent Mesh, trusted devices terminate at Phi cloud and only the Phi cloud runtime is a normal Cloudx gateway consumer. Cloudx never stores Phi device, Task, lease, approval, local-path, transfer-content, or Artifact metadata.
- Phi uses a revocable least-privilege Cloudx consumer credential that cannot import accounts, mutate gateway or release state, or represent a Phi device identity.
- Direct endpoint-to-Cloudx access for future local inference requires a separate accepted milestone and credential contract; Mesh membership alone never grants gateway access.
- Local CPA import may delegate to the explicitly labeled legacy recovery adapter only while codex-plus retirement is incomplete; that dependency must not be hidden.
- Interactive local and cloud imports use one outcome vocabulary that identifies the destination, imported and skipped counts, verification scope, and safe failure reasons. Cloud write acceptance must never be presented as proof of live account usability.
- Local and cloud API diagnosis use one outcome vocabulary that separates account deactivation, exhausted allowance, transient rate limiting, relogin, permission denial, gateway failure, and unknown evidence. A successful model-list probe must never be presented as proof of remaining upstream quota.
- Cloud helper JSON, static text, health publication, receipts, release state, logs, and public errors pass through one fail-closed metadata boundary. Phi Task, session, device, lease, approval, local-path, transfer-content, ContextRequest, LocalAction, and Phi Artifact fields are rejected; the scoped credential policy may only state `device`, `task`, and `session` as literal `false` representation constraints.
- Unsupported or shadow-only behavior must be labeled as such in command output and documentation.

## Explicit Non-Goals

- account pools or automatic account selection on the local client
- task, agent, queue, approval, workspace, or project control planes
- Phi device registration, target selection, execution leases, LocalAction routing, or cross-device approval
- chat clients or multi-user hosted execution
- autonomous code repair, merge, deploy, or service restart
- ownership of Tailscale, mihomo, SSH, systemd, or CLIProxyAPI

## Compatibility

Local and cloud artifacts share a protocol range. A local artifact supports the current remote protocol and the immediately previous one. An absent helper is reported as `legacy_bridge`; it is not treated as permission to mutate the gateway.

The read-only `cloudx.phi-mesh-compatibility-profile.v1` document references the existing handshake, health, gateway, client-configuration, signed-release, and rollback contracts. The profile is secret-free and grants no credential, import, gateway-mutation, release-mutation, service, or activation authority.

The secret-free `cloudx.phi-cloud-consumer-credential.v1` policy defines a distinct gateway-only bearer for the Phi cloud service. Its only allowed operation is provider inference through `/v1`; it is not an SSH identity, cannot invoke `cloudx-remote`, read Cloudx auth or release state, import accounts, mutate gateway configuration, stage/activate/rollback a release, or assert a Phi Device, Task, or session identity. Installation, rotation, revocation, and any required gateway restart remain separately confirmed operations.

The read-only `cloudx.phi-cloud-consumer-traffic-policy.v1` contract bounds the one Phi cloud consumer to four in-flight logical requests, a sixteen-entry FIFO queue, thirty gateway attempts per minute with burst four, explicit admission and request timeouts, and at most three attempts. Every retry retains its logical request's in-flight slot and consumes rate budget; no response is retried after response bytes are observed. This is a consumer interoperability policy, not a Cloudx queue or scheduling service.

`cloudx.capacity.v1` is the secret-free runtime capacity classification. It reports exactly one of healthy capacity, exhausted capacity, unknown observation, stale contract, probe failure, or incompatible producer. A missing or partially unobserved aggregate is never guessed to be exhausted, and the document contains aggregate counts only.
