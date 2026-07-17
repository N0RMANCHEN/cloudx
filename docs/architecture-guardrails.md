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
- shared contracts importing either endpoint
- release code reading runtime credentials or session state

The initial Mesh direction is frozen in `config/governance/phi_mesh_topology.v1.json`. The architecture gate rejects direct device-to-Cloudx access, any additional normal Mesh consumer, Cloudx control-plane ownership, synchronized release coupling, or removal of the separate approval requirements for future direct endpoint access.

Cloud runtime stdout, stderr, and published public state must use `cloudx_cloud.public_metadata`; direct `print` or `sys.stdout`/`sys.stderr` writes outside that module fail the architecture gate.

## Runtime Separation

Release directories are immutable code. Configuration and state live outside them. Activation changes an atomic `current` symlink only after explicit confirmation. Existing processes continue using the release from which they started.

## File Size

Watched Python and shell files are limited to 800 lines. A temporary exception must be listed with an exact ceiling and split plan in the governance config.

## Prompt Boundary

Prompts may classify evidence or propose a patch. They do not authorize writes, service changes, merges, or release activation. Those decisions stay in deterministic code and operator actions.
