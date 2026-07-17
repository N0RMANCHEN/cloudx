# Test Standards

## Required Layers

- Unit tests cover command parsing, profile state, tunnel lifecycle, import normalization, atomic writes, health redaction, and release verification.
- API diagnosis tests cover explicit deactivation, quota exhaustion, transient rate limiting, relogin, access denial, generic pool failure, reset-time normalization, request-body exclusion, successful-response false positives, and preservation of a definitive root cause across later `no auth available` responses.
- Governance and unit tests require every cloud-runtime stdout/stderr path and published public document to pass the Phi metadata boundary, including negative fixtures for Task, session, device, lease, approval, local path, transfer content, ContextRequest, LocalAction, and Phi Artifact fields.
- The default verifier evaluates the committed Phi/Cloudx current-and-N-1 evidence across all four release pairs, Cloudx-first and Phi-first upgrades, and both independent rollback directions. A valid audit may report `blocked`; only `compatible` can satisfy the M4A ordering gate.
- The default verifier validates the migration-only legacy health bridge against a strict example, immutable-artifact systemd boundary, and three separate runtime-acceptance gates. An optional checkout-aware run executes the exact recorded Phi N-1 parser against generated bridge output; source readiness cannot substitute for signed publication, unit acceptance, and rollback rehearsal.
- The bridge rollback regression must build the candidate artifact, keep it independent from the endpoint selector, drive the real Cloudx rollback function in both directions under an isolated release root, and require byte-identical output before and after each selector change.
- Legacy bridge unit-installer tests cover non-authorizing planning, exact confirmation, staged-artifact binding, signed-template extraction, bounded non-symlink inputs, root-owned fixed paths, active legacy rollback availability, inactive/disabled target enforcement, idempotence, systemd verification, daemon reload, secret-free receipts, and full file rollback without any start/enable/stop/disable or selector operation.
- Phi consumer credential installer tests cover read-only planning, exact confirmation, staged-artifact binding, fixed path/group contracts, symlink and size rejection, private existing Cloudx credential continuity, overlap-first rotation, secret-free receipts, gateway canary/watch acceptance, and full config/credential rollback after failure.
- The default verifier also evaluates the committed Phi privileged-boundary evidence across the normal interactive CLI, mail-command, and orchestrator Agent surfaces. It derives effective auth-read, import, gateway-mutation, and release-mutation capability from direct tools, runtime identity, privilege elevation, `NoNewPrivileges`, and path masking. A valid audit may report `blocked`; only `secure` can satisfy the M4A privilege gate.
- Installer tests require stage-only trust recovery to use a distinct exact confirmation and to leave activation links, shell source, native profiles, legacy backups, services, and processes unchanged.
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
