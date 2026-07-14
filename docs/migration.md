# Migration From codex-plus

The legacy product remains the communication bridge during initial development.

## Preserved Inputs

- current local cloud hardening branch and tests
- remote importer parser fixes
- current gateway endpoint and retry behavior
- local account profiles and official Codex installation
- installed Phi continuity behavior as migration evidence

## First Cut

The first Cloudx release connects to the existing gateway and uses `legacy_bridge` when no remote helper is installed. Its singleton broker selects a Cloudx-owned local port, never binds `18317`, and cannot stop or replace the old tunnel.

The new importer writes only to a shadow auth directory until its normalized output and failure behavior match accepted fixtures. The new health publisher runs read-only beside the old quota monitor.

## Cutover Gates

- offline local Codex canary and exact resume pass
- remote helper handshake and protocol selection pass
- full model request succeeds through the isolated Cloudx broker port
- a killed Cloudx canary SSH child is replaced by the single broker without affecting legacy sessions
- transient gateway probe failures do not terminate a tunnel carrying active streams
- HTTP 502 is reported as a gateway response, not a tunnel failure
- import is idempotent, locked, atomic, size-limited, and secret-safe
- Phi can consume scoped health without reading gateway configuration

No legacy service is removed in the same change that activates its replacement.
