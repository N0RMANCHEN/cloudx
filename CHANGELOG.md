# Changelog

## Unreleased

- Stage the signed cloud `0.1.1` artifact side-by-side without creating `current`, restarting gateway/import services, or changing production auth metadata.
- Run shadow service templates from an explicitly configured versioned artifact instead of requiring the inactive `/opt/cloudx/current` symlink.
- Install the restricted shadow identity and versioned environment, and run the read-only aggregate account-state adapter beside the unchanged gateway and importer.
- Replay all eight accepted importer envelope formats as the restricted shadow identity, verify normalized output and idempotence, and clean the shadow auth root afterward.
- Stage the signed local `0.1.1` artifact without creating `current`, installing entrypoints, changing command resolution, or touching the legacy port.
- Replace the fixed 24-hour M2 sampling gate with focused repeated checks while retaining the health, classification, continuity, and no-production-write exit conditions.
- Complete repeated legacy-to-shadow classification checks while preserving the exact local Codex PID set, legacy port state, gateway/import processes, and production auth metadata.
- Install and verify the distinct shadow health unit files while keeping both service and timer disabled until the scoped client credential is active.

## 0.1.1 - 2026-07-14

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
- Require local and cloud artifact self-check versions to match the signed manifest and add a dual-endpoint offline stage, tamper, downgrade, and rollback matrix.
- Harden the GitHub release workflow with tag and source-SHA verification, built-artifact stable-index checks, and safe propagation of ephemeral checkout authentication to release-ref pushes.
- Recover the release trust root after the unpublished `v0.1.0` signing failure and advance the release candidate to `0.1.1` without moving the failed tag.
