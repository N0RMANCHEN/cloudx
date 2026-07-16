# Roadmap

This roadmap is the dependency order for Cloudx. Every activation, service change, credential migration, and legacy removal requires accepted evidence and an explicit operator decision.

## Current State

- Signed `0.1.1`, `0.1.2`, `0.1.4`, `0.1.5`, `0.1.6`, `0.1.7`, `0.1.8`, `0.1.10`, `0.1.11`, `0.1.12`, and `0.1.13` artifacts are staged side-by-side on both endpoints. Both `current` links select signed `0.1.13`, and both `previous` links select signed `0.1.12`; immutable `0.1.9` remains local-only failed-release evidence and was never activated.
- The root-owned cloud helper, local entrypoints, minimal shell hook, native profile, runtime/release identity boundary, and rollback paths are active and verified.
- Signed `0.1.5` activates the simplified mode UX (`codexx api`, `codexx cloud`, named accounts, plain `codex`), split local/cloud import routing, endpoint-aware `./install`, and truthful idempotent activation status.
- Signed `0.1.6` restores the non-invasive zsh right-prompt mode badge as `[cx:api]`, `[cx:cloud]`, or `[cx:<account>]` while preserving unrelated `RPROMPT` content and removing only its own segment on exit.
- Signed `0.1.7` introduced the active account-state and `cloudx.health.v1` publishers. Signed `0.1.10` introduced the native CPA implementation, while signed `0.1.13` now executes the enabled publishers and repeatedly publishes `/run/cloudx-account-state/accounts.json` and `/run/cloudx/health.json`; signed `0.1.12` is N-1 and the legacy health contract remains active as rollback.
- Repository development is now `0.1.15`. The immutable annotated `v0.1.14` tag pins release source `75c27446f0a1386a6fbe52a364aff0203c099467`, but no `release-artifacts/v0.1.14` ref or `0.1.14` stable selection exists yet, so signed publication, staging, and activation remain pending. Advancing source identity before further changes prevents a second artifact from being built under `0.1.14`; source `0.1.15` retains the alias-root N-1 regression fix.
- The initial Phi Personal Agent Mesh topology is frozen by the authoritative product contract and a machine-checked governance profile: devices terminate at Phi cloud, only Phi cloud is a normal Cloudx Mesh consumer, Cloudx remains a gateway/capacity dependency, and both products retain independent control planes and releases. No runtime contract, credential, service, or activation change is authorized by this topology item.
- An isolated exact-signed `0.1.13 -> 0.1.12 -> 0.1.13` dual-endpoint rehearsal passed with final `current=0.1.13`, `previous=0.1.12`, canonical idempotent hook bytes, and a signed scripted cloud-mode canary. Because the first local cutover runs under current `0.1.12`, the production plan must immediately repeat the same-version local `0.1.13` apply so the newly current updater removes inherited blank-line drift. A `/tmp` path alias also exposed an N-1 comparison defect that does not affect canonical production `/Users` or `/opt` roots; tagged source `0.1.14` preserves `previous` across aliased same-version apply and has regression coverage.
- Phi's first consumer migration is active: `phi-cloudx-health` runs from its own versioned release, reads `/run/cloudx/health.json` with its restricted identity, and repeats on its timer without credential access. It previously accepted producer `0.1.11`; the Cloudx producer now selects protocol-compatible `0.1.13`, and no Phi service was restarted during Cloudx activation.
- The native CPA-health unit installed from signed `0.1.10` remains active and executes the current signed `0.1.13` artifact from `/opt/cloudx/current/cloudx-cloud.pyz` without `/opt/codex-gateway/codexx_app` in its service contract. Its accepted `0.1.10` observation returned aggregate-only healthy state with 15 total, 10 ready, 5 limited, 0 failed, and 0 archived; auth/archive inventories remained unchanged. The old unit and private state remain in root-only rollback snapshot `/var/lib/cloudx/cpa-health-service-backups/20260715T130117Z-0.1.10`.
- M5 dependency preflight still finds the legacy `18317` listener on the other macOS endpoint, this workstation's local CPA and existing Codex sessions, the old cloud HTTP importer, legacy health exporter, and `/opt/codex-gateway/codexx_app`. Cloudx CPA health and the installed `codex-gateway-import` compatibility path no longer use that runtime, but the active `/opt/codex-gateway/cloud_import_api.py` process still imports `codexx_app.cloud_import_server`; the runtime cannot be retired before the importer is separately stopped and its rollback consumers are handled. The quota-monitor and import-repair timers remain disabled. No broad deletion gate is accepted yet.
- The disabled legacy quota-monitor and unattended import-repair paths are archived under `/var/lib/cloudx/legacy-service-archives/20260715T131538Z` with mode-`0700` root and mode-`0600` files. Two resolved raw import inputs were removed from the failure tree and ordinary archive into root-only `/var/lib/cloudx/secret-recovery/import-resolved-20260715T131953Z`; current failure records retain no `.input` source, while the active importer and SSH dry-run remain healthy.
- Signed `0.1.11` supplies the installed `/usr/local/bin/codex-gateway-import` compatibility adapter, which routes FILE/stdin imports directly to `cloudx-remote import`, preserves `--force`, adds `--dry-run`, and contains no HTTP token or port `8780` dependency. The exact-confirmation transaction retained a root-only rollback set at `/var/lib/cloudx/http-import-compat-backups/20260715T133412Z-0.1.11`; stopping the still-active HTTP importer remains a separate gate.
- Phi commit `b9f66844` is pushed on Phi `origin/main` and installed from the root-owned versioned release `b9f668444ebc8f0258b152d3225df14e113860bf`, with `17d3e42e61fb2d88bf47c25497c05f0b3bb47438` retained as the component N-1 release. The installed goal-watchdog unit reads only `/run/cloudx/health.json`, orders after `cloudx-health.service`, keeps `ProtectHome=read-only`, and grants write access only to the two SQLite `-shm` coordination files required by WAL-mode reads. Its release completed an install/rollback/reinstall round trip and then 265 natural successful zero-action cycles with no systemd failure before the Phi-owned timer was stopped; goal recovery remains optional and is not a Cloudx availability dependency.
- The goal-watchdog migration removes its legacy health-contract signal dependency. A refreshed importer audit found five cloud-host HTTP requests between `08:36` and `08:39` CST, then correlated every request to a short-lived operator-driven SSH compatibility call and an explicit legacy admin-key read. Active unit, cron, installed Phi release, and `/usr/local/bin` scans found no background HTTP caller; the last request remains `08:39:33`, and repeated `13:38` checks found no active import lock or established connection. `codex-import.service` remains enabled and active on port `8780` pending a separate explicit stop/rollback decision, while the legacy health exporter remains active as rollback evidence.
- Fresh-shell acceptance on this workstation confirms active signed `0.1.13` keeps real `HOME=/Users/hirohi`, removes only inherited account-local `.local/bin` entries, preserves Codex temporary paths, resolves official Git and Codex directly, and supports `codexx api`, compatibility `codexx use api`, named accounts, scripted cloud mode, and `codexx exit`. The exact `0.1.13 -> 0.1.12 -> 0.1.13` rollback reinstalled release-matched hooks, and the final same-version reconciliation is byte-idempotent. The regenerated API Git shim and active codex-plus parents remain untouched, so deletion is still unsafe.
- The legacy local port `18317`, local CPA, cloud CLIProxyAPI, old importer, monitors, Phi services, and private codex-plus recovery bundle remain available; the active local shell source is now the Cloudx hook.
- The `/Users/hirohi` macOS workstation now runs signed local `0.1.13` with signed `0.1.12` as `previous`. Its external local CPA remains PID `38189` on `127.0.0.1:8317`; initial and final local API plus cloud model canaries passed, all pre-existing codex-plus and Codex processes survived activation and rollback, and the private recovery command remains healthy. This does not satisfy the broad M5 deletion gate while those legacy parents remain active.
- The `v0.1.0` workflow attempt failed before artifact publication because its configured signing material was unavailable; it produced no release refs, assets, staging, or activation.
- The `v0.1.3` workflow attempt likewise failed before artifact publication because the current trust-root private key was unavailable; its tag remains immutable, no `0.1.3` artifact ref exists, and recovery advances to `0.1.4` with a replacement public trust root.
- Signed `0.1.1` artifacts were built from commit `2fc4c0a8ecc9a60e3858d721d070a36fffa04ed6`, published to immutable `release-artifacts/v0.1.1`, and remain staged beside `0.1.2`; neither version is activated.
- Signed `0.1.2` artifacts were built from commit `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e` and remain available at immutable `release-artifacts/v0.1.2`; they were the active release before the simplified-mode rollout.
- Signed `0.1.4` recovered the unavailable release key from source commit `370aa4904cf143f9ed87b3fff37e8f76155819aa` without moving `v0.1.3`; its immutable artifact ref remains available as the final rollback release.
- Signed `0.1.5` was built from commit `db05c9004fee0def4ca73553f28a255423aea133`, published to immutable `release-artifacts/v0.1.5`, and remains staged as an older rollback artifact.
- Signed `0.1.6` was built from commit `907d1746e0d76dfada579a77454d4efbc3ce69c4`, published to immutable `release-artifacts/v0.1.6`, and remains an older staged rollback artifact.
- Signed `0.1.7` was built from commit `fb4d7e7e4094a90e0edea3e09aeca9802e980f25`, published to immutable `release-artifacts/v0.1.7`, and remains staged as an older rollback artifact.
- Signed `0.1.8` was built from commit `cbd561ef1146b289f66b0e07e696687632b0277c`, published to immutable `release-artifacts/v0.1.8`, selected by the signed stable ref, activated cloud-first and local-second, and retains its signed `0.1.7` N-1 evidence.
- Signed `0.1.10` was built from commit `d495808539c18c2acb416c73d048844a9935bcd6`, published to immutable `release-artifacts/v0.1.10`, selected by the signed stable ref, activated cloud-first and local-second, and retains its signed `0.1.8` N-1 evidence.
- Signed `0.1.11` was built from commit `7aae7b9986bce95f08dc6e3c2a6723109c0c948f`, published to immutable `release-artifacts/v0.1.11`, selected by the signed stable ref, activated cloud-first and local-second, and retains its signed `0.1.10` N-1 evidence.
- Signed `0.1.12` was built from commit `1f94816d7effc62bb3199158066c1ed0b6ef38a6`, published to immutable `release-artifacts/v0.1.12`, selected by the signed stable ref, activated cloud-first and local-second, and remains paired with signed `0.1.11` after a complete dual-endpoint rollback round trip.
- Signed `0.1.13` was built from commit `d50c7d7b3d1cc390dde7e443fdff05f317a65e54`, published to immutable `release-artifacts/v0.1.13`, selected by the signed stable ref, activated cloud-first and local-second, and remains paired with signed `0.1.12` after a complete dual-endpoint rollback round trip.
- A restricted `cloudx` identity, versioned shadow environment, scoped client credential, shadow auth directory, and read-only account-state timer are installed.
- The distinct shadow health service and timer are enabled and publish fresh, secret-free health from the active Cloudx CPA aggregate state.

## Delivery Order

| Milestone | State | Advancement gate |
|---|---|---|
| M0 safety baseline | Complete | Baseline accepted |
| M1 repository and minimal product implementation | Complete | Source and tests accepted |
| M2 versioned shadow deployment and focused validation | Complete | Shadow evidence accepted |
| M3 manual Cloudx activation | Complete; observation active | Explicit activation completed |
| M4 Phi consumer migration | In progress | Formal health and goal-watchdog consumers accepted; remaining Phi-owned migrations stay independently gated |
| M4A Phi Agent Mesh dependency readiness | Planned | Boundary profile, scoped credential, capacity/backpressure semantics, compatibility fixtures, and independent rollback accepted |
| M5 legacy retirement | Pending | Dependency audit, rollback readiness, and separate approval |
| M6 optional gateway/network boundary changes | Deferred | Threat model, rollback rehearsal, and separate approval |

## M0: Safety Baseline

Status: complete.

- [x] Record the active communication chain and forbidden actions.
- [x] Create a repository-external local Codex rescue path.
- [x] Verify a cloud-independent `soul0` canary and exact session resume.
- [x] Archive local cloud hardening as historical evidence.
- [x] Archive remote importer fixes as historical evidence.
- [x] Capture the installed Phi runtime and unit drift without changing production.
- [x] Generate a dedicated Cloudx Ed25519 release key and commit only its public trust root.

## M1: Minimal Product Implementation

Status: complete.

### Local Component

- [x] Keep `codex` as the official local Codex executable.
- [x] Reduce `codexx` to account selection and `add`, `login`, `status`, `logout`, `list`, `current`, and `exit`.
- [x] Keep named accounts under `~/.codex-accounts/<name>/.codex` and switch only `CODEX_HOME`.
- [x] Add an explicit native-profile seed operation that copies `soul0` auth and config as independent files with a backup.
- [x] Isolate the Cloudx Codex profile while sharing only sessions, session index, and skills.
- [x] Implement `cloud codex`, `cloud codex --check`, and `cloud import`.
- [x] Preserve explicit `legacy_bridge` fallback when the remote helper is absent.
- [x] Implement one on-demand persistent tunnel broker with a filesystem singleton lock and PID-backed leases.
- [x] Keep a stable local relay listener while the SSH backend restarts, preventing the known shared-port `connection refused` race.
- [x] Remove HTTP health probes from tunnel ownership. Only SSH process exit can trigger backend rebuild.
- [x] Use 5-second HTTP checks with three attempts for diagnostics without tunnel termination.

### Cloud Component

- [x] Implement `cloudx-remote handshake`, `client-config`, `health`, `import`, and `self-check`.
- [x] Support flat auth, `accounts`, `payload.accounts`, `result.accounts`, sub2api credentials, bundles, concatenated JSON, and raw-card input.
- [x] Enforce a 16 MiB import limit, request hash, lock, deterministic filenames, mode-0600 files, idempotence, atomic replacement, and rollback.
- [x] Default the importer and health publisher to shadow paths.
- [x] Publish only the secret-free `cloudx.health.v1` contract.
- [x] Add versioned stage, activate, and rollback commands that never restart CLIProxyAPI.

### Repository And Release

- [x] Add product, quality, test, architecture, operation, migration, release, and Phi-boundary standards.
- [x] Add reviewed prompt templates with proposal-only authority.
- [x] Add machine-checked architecture rules and the default `./verify.sh` closeout.
- [x] Build deterministic local and cloud zipapps.
- [x] Add signed manifests, a signed stable index, immutable artifact refs, offline bundles, manual stage/apply, and rollback.
- [x] Add macOS and Linux CI plus a release workflow that publishes GitHub artifacts but never deploys a host.
- [x] Pass 29 unit, contract, broker, import, and release tests on Python 3.9.

Evidence is retained under `docs/archive/`.

## M2: Versioned Shadow Deployment

Status: complete and accepted.

This milestone stages committed artifacts only. It must not change the active local command symlinks, shell hook, production auth directory, gateway unit, or legacy tunnel.

### Repository Preparation

- [x] Add a versioned read-only adapter from the legacy quota summary to secret-free aggregate account state.
- [x] Preserve unobserved legacy failures without guessing that they are unavailable, and derive freshness from the original observation time.
- [x] Add distinct `cloudx-shadow-account-state` service and timer templates with no access to credential directories.
- [x] Add an isolated importer fixture replay that compares normalized files, verifies idempotence, and proves raw input cleanup across eight accepted envelope formats.
- [x] Add concurrent fake-stream recovery coverage and expose the measured SSH backend reconnect time without changing the stable relay port.
- [x] Add a dual-endpoint release matrix for offline bundle staging, tamper and downgrade rejection, embedded-version attestation, and N-1 rollback.
- [x] Harden tag-triggered signed publication with tag/SHA preflight, stable-index verification, inherited ephemeral checkout authentication, immutable artifact refs, and replaceable stable refs.
- [x] Recover from the unpublished `v0.1.0` signing failure by generating a repository-external replacement key, committing only its public trust root, and advancing the candidate to `0.1.1`.
- [x] Make shadow units execute an explicitly configured staged artifact without creating or reading `/opt/cloudx/current`.
- [x] Add an operator-confirmed scoped-key restart playbook with config, credential, environment, service, probe, and watcher rollback.
- [x] Bind the scoped-key transaction to an exact staged release and reject artifact/deployment version drift before any gateway mutation.
- [x] Add local-path and directory-envelope regression coverage for the SSH-backed `cloud import` interface and document the raw SSH stdin equivalent.
- [x] Add an explicit, version-attested, rollback-safe bootstrap for the first cloud helper activation so M3 does not depend on a command that is not installed yet.
- [x] Point shadow freshness at the active Cloudx CPA aggregate state rather than the disabled legacy quota-monitor state.
- [x] Split the active remote helper boundary so normal runtime/import commands execute as `cloudx` and only explicit signed release mutations can execute as root.

### Required Work

- [x] Build and sign `0.1.1` from the committed Git SHA and publish the GitHub release refs.
- [x] Stage the cloud artifact under `/opt/cloudx/releases/0.1.1` without changing `/opt/cloudx/current`.
- [x] Install a scoped client credential owned by a restricted Cloudx service identity.
- [x] Configure a versioned shadow environment under `/etc/cloudx` and `/var/lib/cloudx/shadow-auth`.
- [x] Run the shadow health publisher under a distinct `cloudx-shadow-*` unit name.
- [x] Feed the new publisher a read-only account-state adapter; do not classify unobserved accounts by guessing.
- [x] Compare new and legacy account classifications across focused repeated checks.
- [x] Replay accepted importer fixtures into the shadow auth directory and compare normalized output.
- [x] Verify signed GitHub check, offline bundle stage, tamper rejection, downgrade rejection, and rollback on both endpoints.
- [x] Repeat tunnel child termination under concurrent fake streams and capture reconnect timing.
- [x] Confirm current legacy sessions and port `18317` remain unchanged before and after focused validation actions.

Release, staging, shadow identity, importer replay, classification, health-unit, scoped-key, and canary evidence is retained under `docs/archive/`.

### M2 Exit Gate

- fresh, secret-free health evidence from focused repeated checks
- no unexpected account classification differences
- no raw import source retained after success or failure
- the only production service restart or gateway-config credential write is the separately confirmed scoped-key transaction, with rollback evidence; the production auth directory remains unchanged
- local and cloud staged artifact SHA values match the signed manifest
- offline rescue and N-1 rollback reverified

## M3: Manual Cloudx Activation

Status: both endpoints accepted; observation active.

### Repository Preparation

- [x] Expose a read-only cloud release status that validates `current` and `previous` targets and reports the active artifact hash.
- [x] Require every updater activation and rollback command to select exactly one endpoint; combined cloud-and-local mutation is rejected.
- [x] Build, sign, and publish `0.1.2` from the exact committed source SHA.
- [x] Stage cloud `0.1.2` without changing `/opt/cloudx/current`.
- [x] Stage local `0.1.2` without installing entrypoints or changing the local `current` link.

Cloud/local staging, signed release, helper activation, topology, canary, recovery, command acceptance, and rollback evidence is retained under `docs/archive/`.

### Activation Progress

- [x] Activate the compatible cloud helper and validated runtime/release identity boundary.
- [x] Verify handshake, fresh health, scoped client credential access, formal SSH import dry-run, independent tunnel, and a complete model request.
- [x] Reverify the signed GitHub release through a formal dual-endpoint `already-staged` transaction.
- [x] Reverify and activate the local artifact, native profile, minimal shell hook, and local command links under a separate confirmation.
- [x] Run dual-endpoint N-1 rollback rehearsal and begin M3 observation while retaining the legacy listener and processes.
- [x] Publish and roll out signed `0.1.5` so the simplified mode UX replaces the `cloud codex`-first interaction while retaining it as compatibility.

Signed publication, simplified-mode canaries, installer acceptance, service continuity, and rollback evidence is retained under `docs/archive/`.

Before local activation, preserve the existing `codexx use api` and local CPA recovery path under private Cloudx state. The minimal account selector retains both `api` and `cpa` profiles; Cloudx does not take ownership of the local CLIProxyAPI launchd service.

First activation also registers the highest staged N-1 release as `previous`, making rollback available before the first post-activation upgrade.

Activation is split into separate operator-confirmed steps.

1. Activate the compatible cloud helper symlink.
2. Verify handshake, health, client credential scope, and importer dry-run.
3. Reverify the already staged local artifact against the same manifest.
4. Seed the native local Codex profile from `soul0`, preserving a timestamped backup.
5. Install the minimal shell hook so `codex` resolves directly to official Codex and `codexx <name>` changes only `CODEX_HOME`.
6. Activate local `codexx`, `cloud`, and `cloudx-update` symlinks for new invocations.
7. Run `cloud codex --check`, a complete model request, import dry-run, and rollback rehearsal.
8. Keep the old `codexx cloud` implementation and active processes available through the observation period.

### M3 Stop Conditions

- remote protocol mismatch or unexpected fallback
- scoped credential unavailable or over-privileged
- new broker attempts to bind the legacy port
- transient HTTP failure changes the SSH PID
- gateway 5xx is misclassified as a tunnel failure
- official local `codex` still resolves through a legacy wrapper
- any current Codex or Phi session is terminated by activation

## M4: Phi Consumer Migration

Status: in progress.

Phi remains a separate repository and release train. Migrations occur one service per operator-confirmed change.

### Prerequisites

- [x] Audit the installed Phi health consumer identity, filesystem sandbox, source contract, and timer state without running or restarting it.
- [x] Add signed-artifact templates for an active `/run/cloudx/health.json` publisher and aggregate account-state adapter without installing or enabling them.
- [x] Publish and stage signed `0.1.7` on both endpoints while leaving `current` and all services unchanged.
- [x] In a separately confirmed Cloudx maintenance action, activate `0.1.7`, install the versioned health units, validate repeated `cloudx.health.v1` publication, and preserve the legacy contract as rollback.
- [x] Complete the first Phi service migration with fresh stability evidence, rollback readiness, explicit operator confirmation, formal-contract reads, and repeated healthy timer results.
- [x] Diagnose the remaining goal-watchdog legacy-contract and SQLite WAL sandbox drift, then validate a Phi-owned formal-health candidate without committing, publishing, deploying, or restarting a service.
- [x] Commit, publish, and install the goal-watchdog component in Phi's own release train after explicit approval, then accept repeated natural runs before using it as HTTP importer retirement evidence.

The current inventory confirms Phi `0.80.6`, aliases `phi-api`, `phi-deepseek`, and `pi`, plus active goal, Cloudx-health, provider-health, roadmap-driver, and mail services. Classification for later changes is:

- `phi-cloudx-health` remains a read-only Cloudx-health consumer and must not gain deployment authority.
- `phi-goal-watchdog`, `phi-roadmap-*`, `phi-provider-health-deepseek`, and `phi-mail-command` remain Phi-owned; each is migrated or retired only in its own operator-confirmed Phi change.
- `codex-import`, `codex-import-phi-repair`, `codex-quota-monitor`, and direct gateway-key access are legacy integration candidates, not Cloudx runtime features.
- `/opt/codex-gateway/codexx_app` and the old HTTP importer remain M5 retirement candidates after their consumers and rollback dependencies are gone.
- Tailscale, SSH, mihomo, systemd, CLIProxyAPI, and firewall policy remain external infrastructure boundaries and are not deleted as part of Phi migration.

1. Recover the installed `/usr/local/bin/phi` continuity changes into the Phi repository with regression coverage.
2. Give Phi a scoped identity that can read `cloudx.health.v1` but cannot read Cloudx credentials or auth files.
3. Move DeepSeek balance monitoring to a Phi-owned versioned release.
4. Move mail command credentials and execution to a restricted Phi service identity.
5. Retain goal recovery as an optional, experimental Phi integration; it cannot be a Cloudx availability dependency.
6. Replace unattended import repair with sanitized diagnostics and a PR-only Phi playbook.
7. Remove Phi's direct `sudo awk` access to the gateway key after its scoped client migration passes a real request.

No M4 item may merge Cloudx code, deploy Cloudx artifacts, restart Cloudx services, or mutate Cloudx auth state.

## M4A: Phi Agent Mesh Dependency Readiness

Status: planned; no runtime, credential, service, release, or activation change is authorized.

This milestone is the Cloudx companion to Phi `INT/P1-1` and `CT/P1-3`. It does not make Cloudx an Agent Mesh control plane. It makes the existing gateway and health dependency explicit, compatible, capacity-aware, and independently recoverable before Phi enables cross-device provider-dependent journeys.

### Cloudx-Owned Work

- [x] Freeze the initial topology so trusted devices connect to Phi and only Phi cloud is a normal Cloudx Mesh consumer.
- [ ] Publish a versioned compatibility profile referencing the existing handshake, health, gateway, credential, release, and rollback contracts; add a new runtime schema only if existing contracts cannot express a required state without ambiguity.
- [ ] Define a scoped, revocable, rotatable Phi cloud consumer credential that cannot import accounts, mutate gateway configuration, activate releases, or represent a Phi device.
- [ ] Define bounded concurrency, rate-limit, queue/backpressure, timeout, and retry semantics for a single Phi cloud consumer without adding Task or device concepts to Cloudx.
- [ ] Make capacity output distinguish healthy capacity, exhausted capacity, unknown observation, stale contract, probe failure, and incompatible producer without leaking account identity.
- [ ] Verify current and previous protocol compatibility and independent Phi/Cloudx upgrade and rollback ordering.
- [ ] Verify Cloudx logs, health, receipts, release state, and public errors contain no Phi Task, session, device, lease, approval, local path, transfer content, or Artifact metadata.
- [ ] Verify the Phi privileged boundary cannot read Cloudx auth or invoke import, gateway mutation, or Cloudx release mutation as an Agent capability.

### Explicitly Not Cloudx Work

- Device registration, presence, naming, trust, revocation, or target selection.
- Session writer lease, device execution lease, Task, approval, ContextRequest, LocalAction, transfer, Artifact, Reminder, or notification truth.
- macOS directory, TCC, Keychain, local policy, target approval, or local execution.
- Agent planning, runtime prompts, semantic routing, cross-device scheduling, or user-facing Mesh UI.
- Direct endpoint-to-Cloudx access for local inference; that requires a separate approved milestone.

### Acceptance Gate

- The matching Phi owner matrix and Cloudx boundary document agree on every responsibility and prohibited data field.
- Cross-repository fixtures cover gateway unavailable, capacity unknown, exhausted, stale health, incompatible protocol, revoked credential, rate limit, Cloudx rollback, and independent release ordering.
- Provider-dependent Phi phases wait, degrade, or fail without changing Phi Device, Task, lease, approval, revocation, or completed local-action truth.
- Cloudx remains fully operable when Phi is unavailable, and Phi retains Task truth when Cloudx is unavailable.
- No acceptance evidence requires synchronized release, production credentials in Git, a shared database, or cross-repository mutation authority.

### Rollback

Disable only the new compatibility capability/profile and retain the current single Phi cloud consumer plus `cloudx.health.v1`. Roll back Phi and Cloudx independently to the last compatible releases; do not change account, Device, or Task truth.

## M5: Legacy Retirement

Status: pending.

- [ ] Confirm there are no legacy local sessions, tunnels, import transactions, or rollback dependencies.
- [ ] Retire the old HTTP importer only after SSH import has production acceptance evidence.
- [x] Replace the installed `codex-gateway-import` HTTP client with the signed SSH compatibility adapter while retaining an atomic rollback set and leaving the old service running.
- [x] Complete a read-only stop-gate audit covering port activity, request history, systemd reverse dependencies, installed callers, legacy health output, and Phi consumers without stopping or disabling the importer.
- [x] Recheck the stop gate after the Phi goal-watchdog formal-health cutover; confirm that its legacy signal dependency is gone but fresh cloud-host HTTP account and import requests independently keep retirement unapproved.
- [x] Attribute every post-cutover HTTP request to short-lived operator-driven compatibility calls and verify that no active timer, cron job, installed client, later request, import transaction, or established connection remains.
- [x] Implement a release-packaged migration-only stop-gate evaluator with bounded strict evidence, deterministic secret-free blockers, evidence-digest binding, and explicit `serviceStop=false` non-authorization for a later signed rollout.
- [x] Evaluate the sanitized current production snapshot and confirm that only fresh importer-runtime and failure-receipt rollback snapshots remain as machine-reported precondition blockers.
- [x] Replace the legacy quota monitor writer only after Cloudx health and reversible quarantine have accepted observation evidence.
- [x] Disable and archive the unattended import repair timer.
- [ ] Remove the old codex-plus shell hook and installed package only after native `codex`, account switching, and rollback pass in a fresh shell.
- [x] Validate native return, API compatibility selection, named-account selection, official Codex resolution, cloud mode, private recovery, and release-matched rollback in isolated fresh shells; publish and activate the hardened signed hook without editing the regenerated active shim.
- [x] Publish and stage signed `0.1.13` so repeated hook installation is whitespace-idempotent and read-only SSH probes detach from caller stdin while import and release-stage payloads retain explicit byte pipes; activation remains separate.
- [x] Rehearse exact signed `0.1.13` activation, release-matched rollback, reactivation, post-cutover hook reconciliation, scripted cloud selection, and source `0.1.14` alias-root N-1 protection in isolated roots without moving production selectors.
- [x] Activate signed `0.1.13` in production, repeat the local same-version hook reconciliation, complete the formal dual-endpoint N-1 round trip, and accept initial plus final API/cloud model canaries with all protected identities unchanged.
- [x] Publish and stage signed `0.1.8` with a CPA health command and unit templates that remove the mutable-checkout execution path while declaring the temporary `/opt/codex-gateway/codexx_app` compatibility dependency.
- [x] In a separately approved maintenance action, install the versioned `cloudx-cpa-health` units, validate aggregate output and reversible quarantine, and retain the old unit as rollback before removing the mutable checkout.
- [x] Implement the native Cloudx quota probe, bounded auth scanner, atomic private state, reversible quarantine, and exact-confirmation restore path with sanitized fixtures and old/new read-only parity.
- [x] Publish and activate the signed native CPA-health release, replace only its unit in a separately confirmed maintenance action, and accept repeated observation before retiring `/opt/codex-gateway/codexx_app`.
- [ ] Remove `legacy_bridge` in its own release after N/N-1 protocol support no longer requires it.
- [x] Preserve recovery archives and service manifests outside release directories.

Legacy removal must not be combined with gateway bind, Tailscale, mihomo, SSH, or CLIProxyAPI changes.

## M6: Deferred Gateway And Network Work

Status: deferred and unapproved.

Potential work includes loopback-only gateway binding, removal of direct Tailscale gateway exposure, restricted sudo policy, gateway key rotation, or CLIProxyAPI upgrades. Each item needs its own threat model, separate maintenance action, rollback rehearsal, and approval. None is required for Cloudx `0.1.x`.

## Permanent Non-Goals

- account pools or local automatic account selection
- agent, task, queue, workspace, project, or approval control planes
- multi-user or multi-tenant execution
- hosted chat clients
- automatic production merge, deploy, restart, or credential deletion
- Cloudx dependence on Phi
- production deployment from a mutable Git checkout
