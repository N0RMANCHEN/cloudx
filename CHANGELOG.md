# Changelog

## Unreleased

- Add a default-read-only, exact-confirmation local operator transaction for stopping the legacy `codex-import.service`. Apply requires a fresh digest-bound stop-gate decision from the exact staged signed cloud artifact, verifies the complete remote rollback manifest, disables only the importer, proves port `8780` closed, repeats the real SSH dry-run import plus formal-health/Phi/gateway-model canaries, preserves gateway/selectors, and automatically re-enables the importer on any failure without removing runtime, unit, token, receipt, exporter, or rollback data.
- Add a default-read-only, exact-confirmation legacy-health bridge cutover rehearsal. Apply first requires the isolated canary, then uses overlap-first systemd transitions for candidate cutover, old-exporter rollback, and candidate restoration; every current timer is disabled only after the target timer and writer pass, failure recovery restores the old path, and Cloudx selectors plus gateway/importer processes must remain byte-for-byte state-identical.
- Add a signed, static legacy-health bridge canary unit plus a default-read-only exact-confirmation runner. The canary executes the exact staged artifact under the production hardening boundary, writes only a temporary `/run` document while masking the production legacy-health directory, validates the strict legacy contract, removes temporary state, and leaves the primary bridge disabled/inactive, the old exporter enabled/active, and release selectors unchanged.
- Add a default-read-only, exact-confirmation installer for the fixed-artifact legacy health bridge unit files. Apply accepts only the exact staged cloud artifact, extracts and validates the signed environment/canary/service/timer templates, requires the existing legacy timer to remain enabled and active, installs the candidate disabled and inactive, performs only `daemon-reload`, retains a root-only rollback set, and restores prior files on failure without starting/enabling the bridge, stopping/disabling the legacy exporter, or changing a release selector.
- Add an exact-confirmation, default-read-only Phi consumer gateway-key transaction bound to one staged signed cloud artifact and the fixed `scoped_phi_consumer` path/group contract. Apply preserves the existing Cloudx client credential, retains the previous Phi key during rotation, restarts only `cliproxy.service`, requires a model probe plus restored watches, rolls config/credential/service back on failure, emits no key material, and never restarts Phi or revokes the previous key automatically.
- Add a deterministic isolated legacy-bridge rollback rehearsal that builds the fixed `0.1.15` cloud candidate, drives the real Cloudx selector rollback transaction through `0.1.13/0.1.12 -> 0.1.12/0.1.13 -> 0.1.13/0.1.12`, requires byte-stable bridge output, and revalidates the exact Phi N-1 parser without granting production selector, publication, install, or service authority.
- Package a migration-only `legacy-health-bridge.v1` in the signed cloud source: strictly translate bounded formal `cloudx.health.v1` into the exact secret-free Phi N-1 contract, preserve unknown and unobserved facts, publish atomically, advertise the bridge in handshake/profile/release contracts, and provide fixed-artifact offline systemd templates. A machine checker executes the exact recorded Phi N-1 parser successfully while keeping signed publication, unit installation, and rollback rehearsal explicitly blocked and unauthorized.
- Add an end-to-end isolated release trust-recovery regression that rotates only a temporary source tree, builds and signs both `0.1.15` candidates plus the stable index with the replacement key, proves the old root rejects the new release, and uses the candidates' embedded replacement roots to stage local and cloud releases idempotently without creating activation selectors.
- Add an exact-confirmation release trust-recovery preparation tool that defaults to a non-authorizing plan, requires a clean repository and an absolute repository-external key path, creates only a mode-`0600` Ed25519 private key under a mode-`0700` directory, atomically synchronizes all three public trust roots with rollback, exposes no private path or key material, and grants no commit, tag, publication, staging, activation, or restart authority.
- Replace source `codexx import`'s `codexx-legacy` subprocess dependency with a Cloudx-native compatibility adapter for the external local CPA; preserve flat CPA, sub2api, bundle, JSON/JSONL/concatenated text, directory, stdin, and raw-card inputs while adding bounded reads, a ten-second import lock, atomic mode-0600 replacement with rollback, idempotent unchanged detection, `--dry-run`, `--json`, and explicit no-service-ownership/restart fields.
- Rehearse the `/Users/BofeiChen` local endpoint's exact physical-root transition from active `0.1.8/0.1.7` through ordered `0.1.12 -> 0.1.13`, release-matched N-1 rollback, reactivation, idempotent hook reconciliation, and fresh-shell official-Codex preservation while leaving the real selectors, external CPA PID, and listeners unchanged; also reproduce the known signed-`0.1.13` alias-root defect that source `0.1.14` fixes.
- Add a strict, secret-free Phi/Cloudx failure-semantics matrix covering gateway unavailable, capacity unknown/exhausted/stale, incompatible protocol, revoked credential, rate limit, Cloudx rollback, and independent release ordering; bind it to exact Phi canonical-file digests and keep cross-repository runtime acceptance explicitly blocked on the existing ordering, privilege, and Phi-owned fixture gaps.
- Stage signed `0.1.12` idempotently beside the already staged `0.1.13` on the `/Users/BofeiChen` endpoint, establishing the exact intended N-1 candidate while active `current=0.1.8`, `previous=0.1.7`, shell state, the external CPA PID, and closed port `18317` remain unchanged; activation remains separately unapproved.
- Add exact-confirmation `./install --stage-only` trust recovery for lagging local or cloud endpoints; it verifies an exact signed release with the repository trust root while leaving selectors, shell source, profiles, backups, services, processes, and the other endpoint unchanged. Use it to stage signed `0.1.13` idempotently on the `/Users/BofeiChen` endpoint while retaining active `0.1.8`, previous `0.1.7`, the existing CPA PID, and a closed port `18317`.
- Validate the existing root-only HTTP importer rollback snapshot against the unchanged live runtime, unit, token metadata, and sanitized failure receipts; attribute three later account-list requests to short-lived operator compatibility checks, establish a fresh zero-traffic baseline, and record a secret-free `preconditions-satisfied` stop-gate decision that still grants no automatic action or service-stop authorization.
- Add strict, secret-free Phi privileged-boundary evidence and an executable audit over the deployed interactive CLI, mail-command, and orchestrator Agent surfaces; current evidence remains explicitly blocked because Phi still uses an elevated Cloudx administrative gateway credential and interactive/mail Agent command execution can reach unrestricted root, while the `NoNewPrivileges`-confined orchestrator remains isolated from Cloudx mutation authority.
- Add secret-free `cloudx.api-diagnosis.v1` and consistent `codexx diagnose`, `codexx api diagnose`, and `codexx cloud diagnose` UX; classify explicit account deactivation, exhausted allowance, transient rate limiting, stale login credentials, access denial, gateway auth/network/server failures, and unknown evidence while retaining a definitive upstream root cause when later requests collapse to generic `no auth available`.
- Add a strict, secret-free Phi/Cloudx current-and-N-1 release-ordering evidence fixture and executable matrix audit covering all four release pairs, both upgrade orders, and each single-product rollback; current evidence remains explicitly blocked because Phi N-1 consumes the legacy health contract while Cloudx current/N-1 and Phi current use formal `cloudx.health.v1`.
- Enforce the Phi metadata boundary across every cloud-helper JSON/text/error output, health and account-state publication, and signed cloud release-manifest staging; fail closed on Phi Task/session/device/lease/approval/local-path/transfer/ContextRequest/LocalAction/Artifact fields, retain only literal-false credential non-representation declarations, and add an architecture gate against bypass output paths.
- Unify interactive `codexx import` and `codexx cloud import` UX around explicit status, destination, imported/skipped counts, verification scope, sanitized failure reasons, and nonzero failure exits; preserve redirected count output and add local/cloud `--json` forcing for automation.
- Add secret-free `cloudx.capacity.v1` runtime classification with distinct healthy, exhausted, unknown, stale, probe-failure, and incompatible-producer states, aggregate-only counts, explicit consumer protocol ranges, and no write or publication side effect.
- Define `cloudx.phi-cloud-consumer-traffic-policy.v1` with four in-flight logical requests, sixteen FIFO waiters, a thirty-per-minute/burst-four attempt budget, separated bounded timeouts, capped three-attempt retry semantics, fail-fast backpressure, and no Task, device, scheduler, or Cloudx queue ownership.
- Define `cloudx.phi-cloud-consumer-credential.v1` as a secret-free, gateway-inference-only Phi cloud credential policy with a distinct private path, no device representation or Cloudx administrative authority, overlap-first rotation, explicit revocation, and no implied install or restart authorization.
- Publish `cloudx.phi-mesh-compatibility-profile.v1` from the signed cloud artifact as a secret-free, read-only reference to the existing handshake, health, gateway, credential-bearing client configuration, signed-release, and rollback contracts, with no new runtime state or authorization.
- Freeze the initial Phi Personal Agent Mesh topology in the authoritative product contract and a machine-checked governance profile: trusted devices terminate at Phi cloud, Phi cloud is the only normal Cloudx Mesh consumer, and direct endpoint access remains separately gated.
- Plan a decoupled Phi Personal Agent Mesh companion boundary: trusted devices terminate at Phi cloud, Cloudx remains the gateway/capacity/credential dependency, and M4A gates compatibility, backpressure, failure semantics, data minimization, and independent rollback without making Cloudx a Task or device control plane.
- Attribute the post-cutover HTTP importer traffic to short-lived operator-driven legacy compatibility requests; no timer, cron, active installed client, later request, active transaction, or established connection remains, while service stop still awaits separate approval.
- Advance repository development to `0.1.15` after pushing the immutable `v0.1.14` tag, preventing later source changes from producing another artifact under that release identity while signed publication remains pending.
- Implement a release-packaged migration-only HTTP importer stop-gate evaluator with bounded strict evidence, deterministic blockers, evidence-digest binding, explicit non-authorization, versioned release contracts, and secret-free public output.
- Evaluate the sanitized current production snapshot with source `0.1.15`; the gate remains blocked only on fresh importer-runtime and failure-receipt rollback snapshots and still grants no stop authorization.

## 0.1.14 - 2026-07-16

- Accept the Phi-owned goal-watchdog formal-health migration after its pushed versioned release completed an install/rollback/reinstall round trip and 265 natural zero-action cycles with no systemd failures.
- Refresh the HTTP importer stop gate after the Phi goal-watchdog signal dependency was removed: the legacy service remains active and received new cloud-host HTTP account and import requests, so retirement stays separately blocked pending caller attribution and explicit rollback-safe approval.
- Preserve the true local N-1 selector on repeated same-version activation when the configured home or release root is reached through a filesystem symlink.
- Complete an isolated exact-signed `0.1.13 -> 0.1.12 -> 0.1.13` activation rehearsal and document the one-time same-version local apply that lets the newly current `0.1.13` updater canonicalize hook whitespace after cutover from `0.1.12`.

## 0.1.13 - 2026-07-15

- Make shell-hook installation whitespace-idempotent so repeated activation and rollback do not accumulate blank lines in `.zshrc`.
- Detach read-only SSH helper calls from inherited stdin while retaining explicit byte pipes for import and release-stage payloads, so scripted `codexx cloud` selection cannot consume the caller's remaining commands.
- Publish immutable signed `0.1.13`, verify its stable index and fresh remote clones, and stage both real endpoints idempotently without changing active or previous links or any protected process.
- Activate signed `0.1.13` cloud-first and local-second, reconcile the hook through the newly current updater, complete a dual-endpoint `0.1.13 -> 0.1.12 -> 0.1.13` rollback round trip, and validate initial plus final API/cloud model canaries without restarting protected services.
- Advance repository development to `0.1.14` after publication, staging, activation, and rollback acceptance, leaving signed `0.1.12` as N-1 on both endpoints.

## 0.1.12 - 2026-07-15

- Record the read-only HTTP importer stop-gate audit: the signed SSH adapter has no live port-`8780` client traffic, but the legacy health exporter and Phi goal watchdog still consume importer process state, so service retirement remains separately blocked and unapproved.
- Record a Phi-owned goal-watchdog readiness candidate that switches to formal Cloudx health ordering and permits only SQLite WAL shared-memory sidecars through the read-only home sandbox; focused tests, full Phi checks, mount-namespace execution, and exact component rollback pass without a Phi commit, release, deploy, or service change.
- Harden the `0.1.12` shell hook for reloads from active codex-plus environments by removing only account-local `.local/bin` entries from inherited `PATH`, preserving Codex temporary paths while keeping official Git and Codex resolution independent of the regenerated legacy `git-shim`.
- Publish immutable signed `0.1.12`, verify fresh remote clones and isolated local/cloud staging, and stage both real endpoints idempotently without changing either active link or any gateway, importer, local CPA, codex-plus, or Codex process.
- Activate signed `0.1.12` cloud-first and local-second, install its hardened local hook, complete a dual-endpoint `0.1.12 -> 0.1.11 -> 0.1.12` rollback rehearsal with release-matched hooks, and validate local API plus cloud model requests without restarting or replacing any protected process.
- Advance repository development to `0.1.13` after publication, staging, activation, and rollback acceptance, leaving signed `0.1.11` as N-1 on both endpoints.

## 0.1.11 - 2026-07-15

- Archive the already disabled legacy quota-monitor and unattended import-repair units, scripts, state, failure receipts, locks, and systemd evidence under root-only Cloudx state without removing their installed rollback paths or touching the active HTTP importer.
- Move two resolved legacy raw import inputs out of the failure-record tree and ordinary archive into a separate root-only secret-recovery area, leaving hash-only receipts and preserving SSH importer acceptance plus external service continuity.
- Add a signed-artifact `codex-gateway-import` compatibility adapter that preserves FILE/stdin and `--force`, adds `--dry-run`, and routes directly to `cloudx-remote import` without an HTTP token or port `8780` dependency.
- Publish immutable signed `0.1.11`, stage it through the normal active updater, activate cloud-first and local-second, and retain signed `0.1.10` as N-1 on both endpoints without restarting the gateway, HTTP importer, local CPA, or existing Codex processes.
- Install the signed importer compatibility adapter through an exact-confirmation atomic transaction with a root-only rollback set; an independent dry-run produced no HTTP importer journal entry and preserved its PID and zero restart count.
- Advance repository development to `0.1.12` after publishing and activating signed `0.1.11`; stopping the old HTTP importer remains a separate operator decision.

## 0.1.10 - 2026-07-15

- Publish immutable signed `0.1.10`, activate cloud-first and local-second, complete endpoint-only `0.1.10 -> 0.1.8 -> 0.1.10` rollback rehearsals, and validate complete local API plus isolated cloud model requests without changing legacy process identities.
- Replace only the production CPA-health service/timer with the signed native templates, preserve a root-only rollback set, and accept two distinct natural timer invocations with unchanged auth/archive inventories, aggregate-only healthy output, and no gateway or importer restart.
- Mirror the recovered release trust root into both endpoint artifacts and add a regression that requires repository, local, and cloud signer data to remain byte-identical.
- Advance to `0.1.10` without reusing the immutable `0.1.9` artifact ref after candidate cloud staging correctly rejected its stale embedded trust root.
- Advance repository development to `0.1.11` after publishing and activating signed `0.1.10`, leaving signed `0.1.8` as N-1 rollback on both endpoints.

## 0.1.9 - 2026-07-15

- Publish immutable `0.1.9` release artifacts, then restore signed stable `0.1.8` after the candidate cloud artifact rejected its bundle because the cloud-packaged trust root had not been updated; no cloud release directory, endpoint activation, unit change, or service restart occurred.
- Recover the unavailable `0.1.4` through `0.1.8` release private key with a new repository-external mode-0600 Ed25519 key and commit only its replacement public trust root; `0.1.9` must use candidate-verified out-of-band staging before ordinary signed updates resume.
- Make local activation create the documented private `codexx-legacy` recovery entrypoint and atomically detach backed-up account Git shims from the removed `codexx git-shim` internal command, preserving already-running codex-plus API sessions through cutover.
- Independently activate signed local `0.1.8` on the `/Users/hirohi` workstation, restore signed `0.1.7` as its N-1 rollback release, and validate local API plus isolated cloud model traffic while retaining the exact CLIProxyAPI and existing Codex process identities.
- Replace the signed CPA-health adapter's `/opt/codex-gateway/codexx_app` imports with standard-library Cloudx auth scanning and quota probing, size and symlink guards, atomic private refresh state, and same-filesystem reversible quarantine with transactional rollback.
- Add an exact-confirmation native quarantine restore command, sanitized production-shape fixtures, and regression coverage for direct, nested, and sub2api credentials, HTTP quota classification, secret-free failure records, and failed-manifest rollback.
- Validate the unsigned `0.1.9` cloud candidate against the active `0.1.8` adapter in read-only `--check` mode: both classified 15 logical accounts identically while auth and archive inventories remained unchanged; no release, activation, unit install, or restart was performed.
- Activate signed `0.1.8` cloud-first and local-second, then transactionally replace only the production CPA-health service/timer with the signed templates; preserve the old unit and private state rollback, validate two natural aggregate-only runs, and leave gateway, importer, Phi, legacy listeners, shell hook, native profile, and existing Codex processes unchanged.
- Advance repository development to `0.1.9` after publishing and staging signed `0.1.8`, leaving both active endpoints and every service unit on their prior selections.

## 0.1.8 - 2026-07-15

- Record the M5 dependency preflight without stopping legacy sessions or services; active Codex sessions, port `18317`, local CPA, old importer, quota consumers, and mutable-checkout health execution remain explicit retirement blockers.
- Carry a signed-release `cpa-health` compatibility adapter and systemd templates that move execution off the mutable codex-plus checkout, keep `/opt/codex-gateway/codexx_app` as a declared temporary dependency, and redact account paths from journal output.
- Remove calendar dates and fixed waiting periods from the roadmap; milestone advancement now depends on accepted evidence, rollback readiness, dependency order, and explicit operator confirmation.
- Activate signed `0.1.7` on both endpoints, install and enable the active account-state and `cloudx.health.v1` publishers with the legacy health contract retained, and validate repeated timer publication plus a complete cloud model request without restarting legacy, gateway, importer, or Phi services.
- Make active health unit output-path overrides part of `ExecStart` so they take precedence over the legacy environment file, preserve runtime directories across successful oneshot exits, schedule newly installed timers from activation time, and avoid a duplicate account-state run from the health unit; this removes the `0.1.7` deployment drop-in requirement in the next release.
- Advance repository development to `0.1.8` after publishing and staging signed `0.1.7`, leaving both active endpoints and all service units on their prior selections.

## 0.1.7 - 2026-07-15

- Carry active `cloudx.health.v1` account-state and health publisher templates inside the signed cloud artifact, with a read-only command for exact template inspection and no implicit installation or service action.
- Make health inspection observe the importer lock without creating its directory or lock file, keeping the health path read-only apart from its declared atomic health publication.
- Advance repository development to `0.1.7` after publishing `0.1.6`, so the immutable signed prompt-badge release is not rebuilt in place.
- Read the target release's shell hook before moving the local `current` symlink, preventing zipimport truncation when activation is launched through the stable `cloudx-update` entrypoint.

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
