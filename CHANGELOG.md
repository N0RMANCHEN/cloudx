# Changelog

## Unreleased

- Split Cloudx into independently built local and cloud components.
- Restore the official `codex` command as the local runtime entrypoint.
- Define minimal `codexx`, `cloud codex`, and `cloud import` command surfaces.
- Add versioned handshake, import, health, and release contracts.
- Add side-by-side release staging, signed manifest tooling, offline bundles, and rollback policy.
- Define the Cloudx and Phi ownership boundary and prohibit automated production repair.
- Replace the legacy per-session shared-tunnel supervisor with a locked singleton broker, PID-backed leases, and a stable relay listener.
- Ensure transient HTTP failures never terminate the SSH child; rebuild only after the SSH process exits.
- Preserve `payload.accounts` and `result.accounts` importer compatibility in the canonical cloud parser.
- Add signed GitHub release refs, manual dual-endpoint staging, explicit activation, and downgrade rejection.
- Complete a side-by-side shadow importer, tunnel recovery, and full model canary without production activation.
- Add a read-only legacy quota adapter that publishes only aggregate account state, preserves unobserved failures, and cannot make stale observations appear fresh.
- Add isolated `cloudx-shadow-account-state` systemd templates for the M2 shadow deployment.
- Add an M2 importer fixture replay tool with exact shadow-root confirmation, deterministic normalized-output comparison, idempotence checks, and automatic cleanup.
- Record SSH backend reconnect duration in broker state and cover child termination while concurrent streams occupy the stable relay.
