# Vision

Cloudx should make a personal cloud Codex connection feel as unsurprising as a local command without pretending the network is local or infallible.

The product is successful when:

- `codex` is the official local Codex and remains independent of Cloudx.
- `cloud codex` is a small, inspectable adapter with clear tunnel, gateway, and upstream failure reporting.
- `cloud import` has one canonical parser and a transactional write path.
- either endpoint can be upgraded or rolled back without destroying sessions or credentials.
- the active communication path can always be recovered without model API access.
- Phi and other automation consume stable signals instead of sharing secrets or production write authority.

Cloudx values continuity, narrow ownership, and honest support boundaries over feature count. It will not grow a general control plane, task ontology, multi-tenant server, or autonomous repair loop.
