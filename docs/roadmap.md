# Roadmap

Updated: 2026-07-15

This roadmap is the delivery order for Cloudx. Dates below are earliest planning windows, not automatic deployment dates. Every activation, service change, credential migration, and legacy removal still requires an explicit operator decision.

## Current State

- Signed `0.1.1` and `0.1.2` artifacts are staged side-by-side on both endpoints. The cloud `current` link selects signed `0.1.2`; the local endpoint remains inactive.
- The root-owned cloud helper and restricted runtime/release dispatch boundary are active and verified. No local Cloudx entrypoint or shell hook is active.
- The current legacy `codexx cloud` path, local port `18317`, CLIProxyAPI, importer, monitors, Phi services, and shell hook remain unchanged.
- The `v0.1.0` workflow attempt failed before artifact publication because its configured signing material was unavailable; it produced no release refs, assets, staging, or activation.
- Signed `0.1.1` artifacts were built from commit `2fc4c0a8ecc9a60e3858d721d070a36fffa04ed6`, published to immutable `release-artifacts/v0.1.1`, and remain staged beside `0.1.2`; neither version is activated.
- Signed `0.1.2` artifacts were built from commit `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e` and published to immutable `release-artifacts/v0.1.2`; the signed stable ref now selects `0.1.2`.
- A restricted `cloudx` identity, versioned shadow environment, scoped client credential, shadow auth directory, and read-only account-state timer are installed.
- The distinct shadow health service and timer are enabled and publish fresh, secret-free health from the active Cloudx CPA aggregate state.

## Release Train

| Window | Milestone | State | Activation |
|---|---|---|---|
| 2026-07-14 | M0 safety baseline | Complete | None |
| 2026-07-14 | M1 repository and minimal product implementation | Complete | None |
| 2026-07-14 | M2 versioned shadow deployment and focused validation | Complete | Shadow paths only |
| After M2 evidence review | M3 manual Cloudx activation | In progress: cloud active | Explicit operator confirmation |
| At least 7 stable days after M3 | M4 Phi consumer migration | Pending | One Phi service per window |
| At least 14 stable days after M3 | M5 legacy retirement | Pending | Separate maintenance window |
| No earlier than 30 stable days after M3 | M6 optional gateway/network boundary changes | Deferred | Separate design and approval |

## M0: Safety Baseline

Status: complete.

- [x] Record the active communication chain and forbidden actions.
- [x] Create a repository-external local Codex rescue path.
- [x] Verify a cloud-independent `soul0` canary and exact session resume.
- [x] Archive local cloud hardening on `codex-plus` branch `archive/cloudx-command-20260714`.
- [x] Archive remote importer fixes on `codex-plus` branch `archive/cloudx-import-parser-20260714`.
- [x] Capture the installed Phi runtime and unit drift without changing production.
- [x] Generate a dedicated Cloudx Ed25519 release key and commit only its public trust root.

## M1: Minimal Product Implementation

Status: complete in source, not activated.

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

Evidence: `docs/archive/2026-07-14-foundation-canary.md`.

## M2: Versioned Shadow Deployment

Window: complete. Status: accepted on 2026-07-15.

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

Release evidence: `docs/archive/2026-07-14-release-0.1.1.md`.

Cloud staging evidence: `docs/archive/2026-07-14-cloud-shadow-stage-0.1.1.md`.

Shadow identity and account-state evidence: `docs/archive/2026-07-14-shadow-account-state.md`.

Shadow importer replay evidence: `docs/archive/2026-07-14-shadow-importer-replay.md`.

Local staging evidence: `docs/archive/2026-07-14-local-shadow-stage-0.1.1.md`.

Current endpoint restaging evidence: `docs/archive/2026-07-15-local-shadow-restage.md`.

Focused classification and continuity evidence: `docs/archive/2026-07-14-focused-shadow-validation.md`.

Staged shadow health unit evidence: `docs/archive/2026-07-14-shadow-health-units-staged.md`.

Scoped-key, fresh health, real SSH import, and model-canary evidence: `docs/archive/2026-07-15-m2-scoped-key-shadow-acceptance.md`.

### M2 Exit Gate

- fresh, secret-free health evidence from focused repeated checks
- no unexpected account classification differences
- no raw import source retained after success or failure
- the only production service restart or gateway-config credential write is the separately confirmed scoped-key transaction, with rollback evidence; the production auth directory remains unchanged
- local and cloud staged artifact SHA values match the signed manifest
- offline rescue and N-1 rollback reverified

## M3: Manual Cloudx Activation

Window: active. Status: cloud endpoint accepted; local endpoint pending.

### Repository Preparation

- [x] Expose a read-only cloud release status that validates `current` and `previous` targets and reports the active artifact hash.
- [x] Require every updater activation and rollback command to select exactly one endpoint; combined cloud-and-local mutation is rejected.
- [x] Build, sign, and publish `0.1.2` from the exact committed source SHA.
- [x] Stage cloud `0.1.2` without changing `/opt/cloudx/current`.
- [x] Stage local `0.1.2` without installing entrypoints or changing the local `current` link.

Cloud `0.1.2` staging evidence: `docs/archive/2026-07-14-cloud-shadow-stage-0.1.2.md`.

Local `0.1.2` staging evidence: `docs/archive/2026-07-14-local-shadow-stage-0.1.2.md`.

Signed `0.1.2` release evidence: `docs/archive/2026-07-14-release-0.1.2.md`.

Cloud helper activation, topology, formal import/model canary, and GitHub dual-stage evidence: `docs/archive/2026-07-15-m3-cloud-helper-activation.md`.

### Activation Progress

- [x] Activate the compatible cloud helper and validated runtime/release identity boundary.
- [x] Verify handshake, fresh health, scoped client credential access, formal SSH import dry-run, independent tunnel, and a complete model request.
- [x] Reverify the signed GitHub release through a formal dual-endpoint `already-staged` transaction.
- [ ] Reverify and activate the local artifact, native profile, minimal shell hook, and local command links under a separate confirmation.
- [ ] Run local rollback rehearsal and begin the M3 observation window while retaining the legacy listener and processes.

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

Earliest window: seven stable days after M3. Status: pending.

Phi remains a separate repository and release train. Migrations occur one service per maintenance window.

1. Recover the installed `/usr/local/bin/phi` continuity changes into the Phi repository with regression coverage.
2. Give Phi a scoped identity that can read `cloudx.health.v1` but cannot read Cloudx credentials or auth files.
3. Move DeepSeek balance monitoring to a Phi-owned versioned release.
4. Move mail command credentials and execution to a restricted Phi service identity.
5. Retain goal recovery as an optional, experimental Phi integration; it cannot be a Cloudx availability dependency.
6. Replace unattended import repair with sanitized diagnostics and a PR-only Phi playbook.
7. Remove Phi's direct `sudo awk` access to the gateway key after its scoped client migration passes a real request.

No M4 item may merge Cloudx code, deploy Cloudx artifacts, restart Cloudx services, or mutate Cloudx auth state.

## M5: Legacy Retirement

Earliest window: fourteen stable days after M3. Status: pending.

- [ ] Confirm there are no legacy local sessions, tunnels, import transactions, or rollback dependencies.
- [ ] Retire the old HTTP importer only after SSH import has production acceptance evidence.
- [ ] Replace the legacy quota monitor writer only after Cloudx health and reversible quarantine have an observation window.
- [ ] Disable and archive the unattended import repair timer.
- [ ] Remove the old codex-plus shell hook and installed package only after native `codex`, account switching, and rollback pass in a fresh shell.
- [ ] Move `cloudx-cpa-health.service` off the mutable codex-plus checkout and into a signed Cloudx cloud release before removing that checkout.
- [ ] Remove `legacy_bridge` in its own release after N/N-1 protocol support no longer requires it.
- [ ] Preserve recovery archives and service manifests outside release directories.

Legacy removal must not be combined with gateway bind, Tailscale, mihomo, SSH, or CLIProxyAPI changes.

## M6: Deferred Gateway And Network Work

Earliest window: thirty stable days after M3. Status: deferred and unapproved.

Potential work includes loopback-only gateway binding, removal of direct Tailscale gateway exposure, restricted sudo policy, gateway key rotation, or CLIProxyAPI upgrades. Each item needs its own threat model, maintenance window, rollback rehearsal, and approval. None is required for Cloudx `0.1.x`.

## Permanent Non-Goals

- account pools or local automatic account selection
- agent, task, queue, workspace, project, or approval control planes
- multi-user or multi-tenant execution
- hosted chat clients
- automatic production merge, deploy, restart, or credential deletion
- Cloudx dependence on Phi
- production deployment from a mutable Git checkout
