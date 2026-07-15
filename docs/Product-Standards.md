# Product Standards

## Supported Product Surface

Cloudx 0.x supports these durable behaviors:

1. Select native, `api`, `cloud`, or a named local Codex account mode with `codexx`.
2. Leave the official `codex` command untouched.
3. Hold a shell-owned broker lease for `codexx cloud`, then run the official Codex with plain `codex`.
4. Import local CPA credentials through the explicit migration adapter with `codexx import`.
5. Import cloud gateway credentials over SSH with `codexx cloud import`.
6. Install signed endpoint artifacts and the local shell source with `./install`.

`cloud codex` and `cloud import` remain supported compatibility commands during the migration window.

Remote handshake, health, release staging, and rollback exist to make those behaviors operable. They are not a general control plane.

## Product Invariants

- Single user and personal node first.
- Local execution remains local. `cloud codex` does not SSH into a remote Codex runtime.
- Account selection changes `CODEX_HOME`; it does not modify the official Codex executable.
- Cloud mode binds its tunnel lease to the selecting shell PID. `codexx exit`, another mode selection, or shell death releases that lease.
- The default local Codex profile and named profiles have independent authentication files.
- A single local broker owns the cloud SSH tunnel. Sessions acquire leases; they never monitor, kill, or rebuild the shared SSH process themselves.
- The broker uses a Cloudx-owned port distinct from the legacy bridge and never treats a transient HTTP probe failure as authority to kill an SSH tunnel.
- The existing legacy bridge remains a supported migration fallback until its removal has a separate, accepted roadmap item.
- Import and health code cannot require Phi.
- Local CPA import may delegate to the explicitly labeled legacy recovery adapter only while codex-plus retirement is incomplete; that dependency must not be hidden.
- Unsupported or shadow-only behavior must be labeled as such in command output and documentation.

## Explicit Non-Goals

- account pools or automatic account selection on the local client
- task, agent, queue, approval, workspace, or project control planes
- chat clients or multi-user hosted execution
- autonomous code repair, merge, deploy, or service restart
- ownership of Tailscale, mihomo, SSH, systemd, or CLIProxyAPI

## Compatibility

Local and cloud artifacts share a protocol range. A local artifact supports the current remote protocol and the immediately previous one. An absent helper is reported as `legacy_bridge`; it is not treated as permission to mutate the gateway.
