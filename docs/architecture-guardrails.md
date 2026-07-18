# Architecture Guardrails

Machine-enforced rules live in `config/governance/architecture_rules.json` and `scripts/check_architecture.py`.

## Dependency Direction

```text
local entrypoints -> local implementation -> shared contracts
cloud entrypoint  -> cloud implementation -> shared contracts
Phi devices      -> Phi cloud control plane
Phi cloud        -> Cloudx gateway + versioned health contracts
```

Forbidden directions:

- local importing cloud implementation modules
- cloud importing local implementation modules
- Cloudx importing or invoking Phi runtime code
- Cloudx receiving Phi Device, Task, lease, approval, local-path, transfer-content, or Artifact metadata
- a Phi device using Mesh membership as a Cloudx gateway credential
- Phi privileged automation reading Cloudx auth or invoking Cloudx import, gateway mutation, or release mutation
- Phi probing CPA credentials, deciding archive eligibility, consuming private failure receipts, or moving/restoring Cloudx auth files
- shared contracts importing either endpoint
- release code reading runtime credentials or session state

The initial Mesh direction is frozen in `config/governance/phi_mesh_topology.v1.json`. The architecture gate rejects direct device-to-Cloudx access, any additional normal Mesh consumer, Cloudx control-plane ownership, synchronized release coupling, or removal of the separate approval requirements for future direct endpoint access.

The Phi privilege boundary is recorded separately in `config/governance/phi_cloudx_privileged_boundary.v1.json` and evaluated by `scripts/check_phi_cloudx_privileged_boundary.py`. The audit binds deployed Phi source refs to a secret-free credential class, identity elevation model, and the effective capabilities of each normal Agent instruction surface. A syntactically valid `blocked` result preserves an observed external gap without weakening verification; only `--require-secure` accepts the M4A boundary.

Cloud runtime stdout, stderr, and published public state must use `cloudx_cloud.public_metadata`; direct `print` or `sys.stdout`/`sys.stderr` writes outside that module fail the architecture gate.

## Runtime Separation

Release directories are immutable code. Configuration and state live outside them. Activation changes an atomic `current` symlink only after explicit confirmation. Existing processes continue using the release from which they started.

CLIProxyAPI remains an external dependency. Exact-version policy patches live only under `third_party/cliproxyapi`, are excluded from Cloudx release runtime code, and must bind a clean upstream commit, patch digest, Go version, target platform, and deterministic candidate digest. Building or staging such a candidate grants no launcher, unit, process, listener, credential, or archive authority; external CPA activation requires its own exact confirmation and rollback transaction.

CPA outage diagnosis remains inside the Cloudx endpoint implementation. Proxied business API admission has one process-global maximum of two; diagnosis concurrency is a separate bounded resource. A full account sweep requires a fresh identity-free aggregate `auth_unavailable` trigger, gates on the declared external HTTPS/proxy dependency, deduplicates identical credentials, publishes only aggregate classifications, and performs digest-bound reversible archive itself. Network probes do not hold the archive lock. A conclusive private per-account receipt instead triggers an immediate network-free local LaunchAgent or cloud systemd-path consumer. Periodic maintenance only consumes missed triggers, watcher activation is separately confirmed, and Phi observes the versioned aggregate health contract only; it is never an archive worker or credential oracle.

Local CPA policy activation is a separate external-service boundary. Before any launcher write or stop, a signed-version gate, real baseline Codex canary, private original-launcher snapshot, independently executable recovery tool, exact manual command, and repeated zero-established-connection proof must all pass. Automatic recovery and operator recovery are one implementation; they restore the baseline launcher, stabilize launchd unload/bootstrap transitions, verify health and communication separately, retain safe receipts, and never terminate Codex processes.

## File Size

Watched Python and shell files are limited to 800 lines. A temporary exception must be listed with an exact ceiling and split plan in the governance config.

## Prompt Boundary

Prompts may classify evidence or propose a patch. They do not authorize writes, service changes, merges, or release activation. Those decisions stay in deterministic code and operator actions.
