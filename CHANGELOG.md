# Changelog

## Unreleased

## 0.1.6 - 2026-07-15

- Restore the codex-plus-style zsh right-prompt mode badge as `[cx:api]`, `[cx:cloud]`, or `[cx:<account>]`, preserving unrelated `RPROMPT` segments across switching, hook reload, and `codexx exit`.
- Advance repository development to `0.1.6` after publishing `0.1.5`, preventing later source changes from producing another artifact under the signed version.
- Prepare a credential-free `cloudx.repair-request` v1 handoff, exact base revision, and isolated Phi repair workspace without push, PR, merge, deploy, replay, or production writes.
- Record the verified Phi and legacy-service inventory as M4/M5 migration input without disabling or deleting any unit.

## 0.1.5 - 2026-07-15

- Publish and activate signed `0.1.5` on both endpoints, verify normal signed staging after trust-root recovery, complete dual-endpoint `0.1.5 -> 0.1.4 -> 0.1.5` rollback round trips, and preserve the legacy listener and service PIDs.
- Simplify the interactive model to `codexx api`, `codexx cloud`, `codexx <account>`, then plain official `codex`; cloud mode now holds a broker lease owned by the selecting shell and releases it on mode change, exit, or shell death.
- Route `codexx import` to the explicitly labeled local CPA compatibility adapter and `codexx cloud import` to the SSH cloud importer while keeping the former legacy dependency visible.
- Add reversible account rename/remove operations and an endpoint-aware `./install` that includes local shell-source installation instead of relying on a remembered manual `.zshrc` step.
- Report the actual retained local `previous` release on first and repeated activation, and advance the already published workflow batch to `0.1.5` rather than changing `0.1.4` in place.
- Advance the simplified workflow batch to `0.1.4` after the unpublished `v0.1.3` signing attempt failed; rotate the repository-external release key, commit only its replacement public trust root, and leave the failed tag unmoved.
- Preserve `codexx use <account>` in the minimal shell hook and add a private, size-limited recovery bundle for legacy local API/CPA entrypoints, profiles, launchd state, binary, configuration, and credentials before local activation.
- Register the highest staged N-1 artifact as `previous` during a first endpoint activation so rollback is available immediately instead of only after the second upgrade.
- Include the adjacent legacy `codexx_app` runtime package in the local recovery bundle so the archived launcher is independently executable instead of depending on the live installation.
- Document the accepted native/account/local-CPA/cloud/import/update command surface and label `codexx-legacy` as an observation-window recovery tool rather than a Cloudx product command.
- Preserve the account-scoped legacy Git shim and detach it from the removed `codexx git-shim` internal command so already-running API sessions keep working after local activation.
- Activate signed local `0.1.2`, seed the native profile from `soul0`, preserve `api` and `cpa` selection, validate local CPA and cloud model traffic, and complete real N-1 rollback round trips on both endpoints without stopping legacy services.
- Bind scoped-key installation to an exact staged release, verify the cloud artifact version before any gateway mutation, and write a matching shadow deployment identity.
- Cover local file, directory, missing-path, and symlink behavior for the SSH-backed `cloud import` source reader, and document why a local path cannot be passed directly to `ssh cloud import`.
- Add a confirmation-gated first-cloud-activation bootstrap that creates the initial `current` and `cloudx-remote` links atomically and rolls both back on failed verification.
- Restage signed local `0.1.1` and `0.1.2` artifacts on the current macOS endpoint while preserving its account-scoped legacy `codexx`, official `codex`, shell configuration, and port `18317` listener.
- Feed shadow account health from the active Cloudx CPA aggregate state instead of the disabled legacy quota-monitor file, restoring fresh health without exposing account identities or credentials.
- Complete M2 with the approved scoped gateway key, fresh shadow health, a real local-path SSH import canary, an idempotent shadow write, and a full scoped-key model request while preserving the legacy listener.
- Harden the first active `cloudx-remote` entrypoint with root-owned launchers and a validated sudo policy: normal runtime/import commands execute as `cloudx`, while only signed release mutations can execute as root.
- Activate the signed cloud `0.1.2` helper without a service restart, validate formal SSH import and full model traffic, and prove one GitHub release stages idempotently on both endpoints while the local endpoint remains inactive.
- Stage signed cloud `0.1.2` beside `0.1.1` while leaving `current`, the shadow artifact selection, gateway/import services, and production auth metadata unchanged.
- Stage signed local `0.1.2` beside `0.1.1` while preserving the legacy `codexx` file, official `codex` resolution, shell configuration, current sessions, and inactive release link.
- Align M2/M3 acceptance text with the separately confirmed scoped-key restart and the already completed local side-by-side staging.

## 0.1.2 - 2026-07-14

- Advance source to `0.1.2`, expose a read-only validated cloud release status, and require activation or rollback to target exactly one endpoint per confirmed command.
- Stage the signed cloud `0.1.1` artifact side-by-side without creating `current`, restarting gateway/import services, or changing production auth metadata.
- Run shadow service templates from an explicitly configured versioned artifact instead of requiring the inactive `/opt/cloudx/current` symlink.
- Install the restricted shadow identity and versioned environment, and run the read-only aggregate account-state adapter beside the unchanged gateway and importer.
- Replay all eight accepted importer envelope formats as the restricted shadow identity, verify normalized output and idempotence, and clean the shadow auth root afterward.
- Stage the signed local `0.1.1` artifact without creating `current`, installing entrypoints, changing command resolution, or touching the legacy port.
- Replace the fixed 24-hour M2 sampling gate with focused repeated checks while retaining the health, classification, continuity, and no-production-write exit conditions.
- Complete repeated legacy-to-shadow classification checks while preserving the exact local Codex PID set, legacy port state, gateway/import processes, and production auth metadata.
- Install and verify the distinct shadow health unit files while keeping both service and timer disabled until the scoped client credential is active.
- Add an explicit-confirmation gateway key installer that restarts only the external gateway, validates the scoped key and restored watches, and rolls back files and service state on failure.

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
