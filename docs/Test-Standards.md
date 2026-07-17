# Test Standards

## Required Layers

- Unit tests cover command parsing, profile state, tunnel lifecycle, import normalization, atomic writes, health redaction, and release verification.
- Governance and unit tests require every cloud-runtime stdout/stderr path and published public document to pass the Phi metadata boundary, including negative fixtures for Task, session, device, lease, approval, local path, transfer content, ContextRequest, LocalAction, and Phi Artifact fields.
- Contract tests validate every example against the versioned shared schema.
- Integration tests exercise local and cloud entrypoints with fake SSH, gateway, Codex, and filesystem boundaries.
- Live canaries are manual and use a non-production local port and shadow cloud paths.

## Safety Requirements

Tests must never depend on port `18317`, the production auth directory, a production API key, or an active systemd unit. Network and process boundaries are injected or redirected to fixtures.

Every regression test must assert public behavior or a persisted contract. Tests that assert implementation details need a written reason.

The default closeout command is:

```bash
./verify.sh
```

Release changes additionally run signature rejection, hash mismatch, downgrade, offline bundle, and rollback tests.
