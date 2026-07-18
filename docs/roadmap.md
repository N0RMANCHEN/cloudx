# Roadmap

This roadmap is the dependency order for Cloudx. Every activation, service change, credential migration, and legacy removal requires accepted evidence and an explicit operator decision.

## Current State

- Signed `0.1.1`, `0.1.2`, `0.1.4`, `0.1.5`, `0.1.6`, `0.1.7`, `0.1.8`, `0.1.10`, `0.1.11`, `0.1.12`, `0.1.13`, `0.1.16`, and `0.1.17` artifacts are retained side-by-side across the accepted endpoints. Cloud selects signed `0.1.17` with signed `0.1.16` as `previous`; this workstation now selects signed local `0.1.17` with signed `0.1.13` as `previous`. Immutable `0.1.9` remains local-only failed-release evidence and was never activated. A separately audited `/Users/BofeiChen` local endpoint was not part of that acceptance; it still selects `0.1.8/0.1.7` and has signed `0.1.12` plus `0.1.13` staged side-by-side for an explicitly approved later activation sequence.
- The root-owned cloud helper, local entrypoints, minimal shell hook, native profile, runtime/release identity boundary, and rollback paths are active and verified.
- Signed `0.1.5` activates the simplified mode UX (`codexx api`, `codexx cloud`, named accounts, plain `codex`), split local/cloud import routing, endpoint-aware `./install`, and truthful idempotent activation status.
- Signed `0.1.6` restores the non-invasive zsh right-prompt mode badge as `[cx:api]`, `[cx:cloud]`, or `[cx:<account>]` while preserving unrelated `RPROMPT` content and removing only its own segment on exit.
- Signed `0.1.7` introduced the active account-state and `cloudx.health.v1` publishers. Signed `0.1.10` introduced the native CPA implementation, while signed `0.1.13` now executes the enabled publishers and repeatedly publishes `/run/cloudx-account-state/accounts.json` and `/run/cloudx/health.json`; signed `0.1.12` is N-1 and the legacy health contract remains active as rollback.
- Repository development is now `0.1.18`. Immutable annotated `v0.1.17` pins source `0bf7461c9c421b55031c8d17c0951bc8321a0ba9`; successful tag workflow `29646167279` published artifact ref `d720979dc46ff5a7b4cb1ba121aca92849e0e09a`, moved stable to `82a35ff57ae97c4fd655d14ce2bf28c4304cd31b`, and created a non-draft/non-prerelease GitHub Release with seven assets. Fresh clones accepted the current signer, rejected the previous signer, matched every asset and offline-bundle member, passed both self-checks, and staged local/cloud bundles idempotently in selector-free isolated roots. Publication changed no real endpoint: local remains `0.1.13/0.1.12` with CPA PID `38189`, while cloud remains `0.1.16/0.1.13` with CPA PID `977036` and restart count `0`. Immutable signed `v0.1.16` remains the prior published release.
- The unavailable legacy release key has now been replaced after the exact `ROTATE CLOUDX RELEASE TRUST 0.1.15` operator confirmation. The transaction generated a repository-external mode-`0600` Ed25519 key under a mode-`0700` directory and atomically synchronized the repository, local-artifact, and cloud-artifact public roots to fingerprint `SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o`; all three committed signer files have SHA-256 `b1c18acca5e619b52489bef8b9b2948ac0b5842b14627a30c015d801598d85fc`. Full verification passed before commit. No tag, release artifact, stable move, endpoint stage/activation, service restart, or legacy mutation was combined with the rotation.
- Source `0.1.15` includes a default-offline, exact-confirmation transaction for synchronizing the replacement key into the fixed GitHub `release` environment and proving it through a non-publishing `workflow_dispatch`. After GitHub authentication and the exact confirmation, the previously absent environment secret was created and run `29579236303` completed successfully on pushed commit `f245186f62f298dba015f7a122a63eb2db177b33`; repository verification, signed build, and release-evidence checks passed, while tag verification and both publication steps were skipped. Stable remained unchanged and no tag, artifact ref, endpoint stage/activation, or service change occurred. The later evidence commit requires one final pushed-HEAD dispatch before a separate tag decision.
- The trust-recovery path has an end-to-end isolated regression. It rotates only a temporary source copy, builds and signs both `0.1.15` candidates and a stable index with the replacement key, verifies the old root rejects the release, and then invokes the candidate local and cloud zipapps so their embedded replacement roots accept idempotent staging. Both isolated endpoints remain selector-free. That test itself discards its temporary key and roots without mutation; the separately approved real rotation and publication are recorded above.
- Source `0.1.15` now gives interactive local-CPA and cloud imports one truthful result summary with destination, outcome, counts, verification scope, and sanitized failure reasons while preserving redirected count output for compatibility. The local path no longer invokes `codexx-legacy`: a Cloudx-native adapter preserves the accepted CPA/sub2api/bundle/text/directory/stdin/raw-card formats, adds `cloudx.local-cpa-import.v1`, `--dry-run`, and `--json`, and enforces bounded reads, locking, atomic mode-`0600` replacement, verification, rollback, unchanged detection, and protected-directory rejection without managing or restarting the external CPA. Read-only dry-runs against the two operator-selected JSON files already imported on `/Users/BofeiChen` each parsed one credential, reported it unchanged, retained all 44 external auth JSON bytes, and left CPA PID `17165` unchanged. This source change is not installed or activated by repository verification; active `0.1.8` still uses the private `codexx-legacy` rollback adapter.
- Source `0.1.15` now also provides a default-read-only, exact-confirmation quarantine/restore transaction for the `/Users/BofeiChen` live local codex-plus package. It moves only `codexx_app`, `codexx.py`, and `codexx-legacy` into retained private state after exact active-release, recovery-manifest, process/listener, native-import, fresh-shell, selector, hook, entrypoint, and external-CPA checks; any failure restores the live paths. The read-only audit found zero independent legacy processes, closed port `18317`, the unchanged external CPA PID `17165` on port `8317`, one Cloudx hook and no old hook, plus the valid 169-record private recovery manifest. Actual apply remains blocked because this endpoint still selects `0.1.8/0.1.7`, so no package, hook, entrypoint, process, service, account, selector, or recovery data changed and the broad deletion item remains open.
- Source `0.1.15` now also fail-closes all cloud-helper JSON/text/error output and health/account-state publication on prohibited Phi control-plane metadata or local paths. A machine-checked architecture rule prevents later cloud runtime output from bypassing that boundary; signed Cloudx release artifact records remain explicitly distinct from Phi user Artifacts. This repository change performs no runtime publication or activation.
- Source `0.1.15` now carries a read-only, secret-free API failure diagnosis contract and consistent local/cloud commands. Local CPA diagnosis reads only bounded response sections from retained external gateway error logs; cloud mode observes returned tunnel bytes without modifying them or retaining request content. Explicit deactivation, exhausted allowance, transient rate limiting, relogin, access denial, gateway failure, and unknown evidence stay distinct, and a later generic `no auth available` response cannot erase a recent definitive root cause. A source-tree read-only check classified this workstation's current evidence as HTTP `429` `usage_limit_reached`, not deactivation; no installed artifact, broker, gateway, service, credential, or release selector was changed.
- Signed `0.1.17` carries the corrected CPA credential-failure and concurrency safety batch and is active on both accepted endpoints with signed N-1 retained. Its superseded `.policy.1` candidates remain durably staged but inactive, while `.policy.2` was never staged. The signed release retains the process-global maximum of two proxied business API requests and local fast-service-tier mapping, while a final aggregate `auth_unavailable` emits an identity-free incident trigger. Only that trigger starts an infrastructure-gated, duplicate-deduplicated account sweep with separate adaptive concurrency up to 32. Direct conclusive permanent receipts still archive immediately through a network-free path, and quota/429, provisional refreshable 401, transport/provider/5xx, and unknown failures remain in place. The exact cloud `.policy.3` candidate is now durably staged and inactive with SHA-256 `453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b`; local SHA-256 `1cff3152e34666d2753add54ce7f5f96dbd643e607c1f136a9052cd28eba9ecd` remains unstaged. The unchanged cloud health unit still invokes the pre-watcher command, but with zero active accounts its accepted natural run performed zero probes; trigger-aware timer fallback must be installed with the separate watcher transaction before usable capacity is imported.
- A separately authorized cloud import normalized the exact OpenAI OAuth CPA-export wrapper and atomically wrote ten mode-`0600` records; an idempotent repeat reported ten skipped and zero writes. Later outage diagnosis used the declared cloud mihomo path and probed all 45 current records sequentially. Every account returned explicit HTTP `402 deactivated_workspace`, with zero quota, transport, provider, or unknown classifications. The operator-authorized transaction therefore reversibly archived all 45 through the existing monitor/quarantine locks, digest revalidation, atomic moves, and private manifest. The active auth directory is empty; the archive has 45 private credentials and 45 manifest entries. Cloud CPA remains PID `977036`, restart count `0`, on its baseline binary. A separate direct `soul0` official-Codex canary had already proved a non-CPA recovery path, and the current local `api` profile baseline also passed.
- A strict release-ordering evidence fixture evaluates Cloudx `0.1.13`/`0.1.12` against the recorded Phi current/N-1 across four release pairs, two upgrade orders, and both rollback directions. Phi current supports both Cloudx releases directly. Signed `0.1.15` now publishes the bounded, secret-free formal-to-legacy health bridge fixed to its immutable artifact; its generated example is accepted by the exact Phi N-1 parser at release `17d3e42`, while unknown process/failure facts remain unknown. Source also includes the isolated selector rehearsal, inactive unit installer, production-path-isolated canary, and final overlap-first primary/legacy/primary transaction. The audit still identifies `legacy_bridge_pending` on the two remaining production gates—unit installation and runtime rollback/cutover acceptance—so the M4A ordering checkbox remains open.
- A separate strict Phi privileged-boundary fixture now binds deployed Agent refs, the active consumer credential class, runtime identity elevation, and surface-specific command/`NoNewPrivileges`/path-mask evidence. The audit truthfully remains `blocked`: Phi still sources its Cloudx provider credential from an elevated administrative gateway key, and the normal interactive and authenticated mail Agent paths can reach unrestricted root Cloudx authority. The confined orchestrator passes, no production state was changed, and the M4A privilege checkbox stays open pending a Phi-owned permission and credential migration.
- Signed `0.1.15` provides a default-read-only, exact-confirmation installer for the dedicated `scoped_phi_consumer` gateway bearer. It binds apply to an exact staged artifact and fixed path/group/mode, preserves the current Cloudx client credential, retains any previous Phi key for overlap, restarts only the gateway, canaries HTTP 200 plus restored watches, and rolls back on failure without restarting Phi or revoking the previous key. The real host still lacks the `phi-cloudx-consumer` group, credential directory, credential, and staged `0.1.15` artifact, so only the non-authorizing plan ran and the privilege checkbox remains open.
- The initial Phi Personal Agent Mesh topology is frozen by the authoritative product contract and a machine-checked governance profile. The signed cloud artifact publishes the compatibility, credential, and traffic policies plus live `cloudx.capacity.v1`. Capacity now preserves healthy, exhausted, unknown, stale, probe-failure, and incompatible-producer states using only protocol, gateway, freshness, and aggregate count fields. These contracts install no credential or limiter and authorize no runtime, service, release, restart, or activation change.
- A strict, secret-free failure-semantics fixture now binds the Cloudx capacity, scoped-credential, traffic, compatibility, release-ordering, and privilege evidence to exact digests from Phi source `3f125abf16fec1e7c17d2ccff0f6ce0a2414193e`. Its nine cases cover gateway unavailable, capacity unknown/exhausted/stale, incompatible protocol, revoked credential, rate limit, Cloudx rollback, and independent release ordering while forbidding Phi truth or Cloudx runtime mutation. The Cloudx contract matrix is ready and the real sibling-checkout snapshot verifies, but cross-repository acceptance remains `blocked` on incompatible current/N-1 ordering, the insecure privileged boundary, blocked Phi `INT/P1-1` and `CT/P1-3`, and missing Phi runtime fixtures.
- An isolated exact-signed `0.1.13 -> 0.1.12 -> 0.1.13` dual-endpoint rehearsal passed with final `current=0.1.13`, `previous=0.1.12`, canonical idempotent hook bytes, and a signed scripted cloud-mode canary. Because the first local cutover runs under current `0.1.12`, the production plan must immediately repeat the same-version local `0.1.13` apply so the newly current updater removes inherited blank-line drift. A `/tmp` path alias also exposed an N-1 comparison defect that does not affect canonical production `/Users` or `/opt` roots; tagged source `0.1.14` preserves `previous` across aliased same-version apply and has regression coverage.
- Phi's first consumer migration is active: `phi-cloudx-health` runs from its own versioned release, reads `/run/cloudx/health.json` with its restricted identity, and repeats on its timer without credential access. It previously accepted producer `0.1.11`; the Cloudx producer now selects protocol-compatible `0.1.13`, and no Phi service was restarted during Cloudx activation.
- The native CPA-health unit installed from signed `0.1.10` remains active and executes the current signed `0.1.13` artifact from `/opt/cloudx/current/cloudx-cloud.pyz` without `/opt/codex-gateway/codexx_app` in its service contract. Its accepted `0.1.10` observation returned aggregate-only healthy state with 15 total, 10 ready, 5 limited, 0 failed, and 0 archived; auth/archive inventories remained unchanged. The old unit and private state remain in root-only rollback snapshot `/var/lib/cloudx/cpa-health-service-backups/20260715T130117Z-0.1.10`.
- M5 dependency preflight still finds the legacy `18317` listener on the other macOS endpoint, this workstation's local CPA and existing Codex sessions, the old cloud HTTP importer, legacy health exporter, and `/opt/codex-gateway/codexx_app`. Cloudx CPA health and the installed `codex-gateway-import` compatibility path no longer use that runtime, but the active `/opt/codex-gateway/cloud_import_api.py` process still imports `codexx_app.cloud_import_server`; the runtime cannot be retired before the importer is separately stopped and its rollback consumers are handled. The quota-monitor and import-repair timers remain disabled. No broad deletion gate is accepted yet.
- The disabled legacy quota-monitor and unattended import-repair paths are archived under `/var/lib/cloudx/legacy-service-archives/20260715T131538Z` with mode-`0700` root and mode-`0600` files. Two resolved raw import inputs were removed from the failure tree and ordinary archive into root-only `/var/lib/cloudx/secret-recovery/import-resolved-20260715T131953Z`; current failure records retain no `.input` source, while the active importer and SSH dry-run remain healthy.
- Signed `0.1.11` supplies the installed `/usr/local/bin/codex-gateway-import` compatibility adapter, which routes FILE/stdin imports directly to `cloudx-remote import`, preserves `--force`, adds `--dry-run`, and contains no HTTP token or port `8780` dependency. The exact-confirmation transaction retained a root-only rollback set at `/var/lib/cloudx/http-import-compat-backups/20260715T133412Z-0.1.11`; stopping the still-active HTTP importer remains a separate gate.
- Phi commit `b9f66844` is pushed on Phi `origin/main` and installed from the root-owned versioned release `b9f668444ebc8f0258b152d3225df14e113860bf`, with `17d3e42e61fb2d88bf47c25497c05f0b3bb47438` retained as the component N-1 release. The installed goal-watchdog unit reads only `/run/cloudx/health.json`, orders after `cloudx-health.service`, keeps `ProtectHome=read-only`, and grants write access only to the two SQLite `-shm` coordination files required by WAL-mode reads. Its release completed an install/rollback/reinstall round trip and then 265 natural successful zero-action cycles with no systemd failure before the Phi-owned timer was stopped; goal recovery remains optional and is not a Cloudx availability dependency.
- The goal-watchdog migration removes its legacy health-contract signal dependency. A refreshed importer audit found five cloud-host HTTP requests between `08:36` and `08:39` CST, then correlated every request to a short-lived operator-driven SSH compatibility call and an explicit legacy admin-key read. Active unit, cron, installed Phi release, and `/usr/local/bin` scans found no background HTTP caller; the last request remains `08:39:33`, and repeated `13:38` checks found no active import lock or established connection. `codex-import.service` remains enabled and active on port `8780` pending a separate explicit stop/rollback decision, while the legacy health exporter remains active as rollback evidence.
- A `2026-07-17` recheck validates the already-created root-only importer runtime, unit, token-metadata, failure-receipt, and restore-plan snapshot against unchanged live bytes. Three later account-list requests were attributed to two short-lived operator compatibility checks; using the final `13:26:44` request as the refreshed baseline, the final audit found no later request, established connection, import lock, active caller, unattributed request, raw failure input, adapter drift, or reverse unit dependency. The machine gate is `preconditions-satisfied` but non-authorizing. Source now also provides an exact-confirmation stop/restore transaction with fresh signed-gate parity, manifest verification, port closure, real SSH dry-run import, formal-health/Phi/gateway canaries, and automatic recovery; its read-only canaries passed while importer PID `133756` and gateway PID `977036` remained unchanged. The importer remains enabled and active pending an explicitly approved stop window.
- Fresh-shell acceptance on this workstation confirms active signed `0.1.13` keeps real `HOME=/Users/hirohi`, removes only inherited account-local `.local/bin` entries, preserves Codex temporary paths, resolves official Git and Codex directly, and supports `codexx api`, compatibility `codexx use api`, named accounts, scripted cloud mode, and `codexx exit`. The exact `0.1.13 -> 0.1.12 -> 0.1.13` rollback reinstalled release-matched hooks, and the final same-version reconciliation is byte-idempotent. The regenerated API Git shim and active codex-plus parents remain untouched, so deletion is still unsafe.
- The legacy local port `18317`, local CPA, cloud CLIProxyAPI, old importer, monitors, Phi services, and private codex-plus recovery bundle remain available; the active local shell source is now the Cloudx hook.
- The `/Users/hirohi` macOS workstation now runs signed local `0.1.13` with signed `0.1.12` as `previous`. Its external local CPA remains PID `38189` on `127.0.0.1:8317`; initial and final local API plus cloud model canaries passed, all pre-existing codex-plus and Codex processes survived activation and rollback, and the private recovery command remains healthy. This does not satisfy the broad M5 deletion gate while those legacy parents remain active.
- The separately audited `/Users/BofeiChen` macOS endpoint had no port-`18317` listener, active Cloudx broker, or visible legacy Codex session, but remained on signed `0.1.8/0.1.7`; its installed old updater could not verify the current stable-index signature. The new exact-confirmation stage-only recovery used the repository trust root to stage signed `0.1.13`, then signed `0.1.12` as the intended N-1 candidate, and returned `already-staged` idempotently for both. A canonical physical-root rehearsal then passed the exact `.8/.7 -> .12/.8 -> .13/.12`, rollback `.12/.13`, and final `.13/.12` sequence with release-matched hooks, byte-idempotent 0.1.13 reconciliation, healthy self-check, and fresh-shell official Codex preservation. A deliberately invalid symlinked-release-root attempt reproduced signed `0.1.13`'s known alias defect and was rejected at rollback; source `0.1.14` retains the fix. The real `current`/`previous` links, port-`8317` CPA PID, and closed port `18317` remained unchanged. Production activation and old-package retirement stay separately gated.
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
- [x] Unify interactive local and cloud import results without hiding the local legacy adapter or presenting cloud write acceptance as live credential verification.
- [x] Preserve explicit `legacy_bridge` fallback when the remote helper is absent.
- [x] Implement one on-demand persistent tunnel broker with a filesystem singleton lock and PID-backed leases.
- [x] Keep a stable local relay listener while the SSH backend restarts, preventing the known shared-port `connection refused` race.
- [x] Remove HTTP health probes from tunnel ownership. Only SSH process exit can trigger backend rebuild.
- [x] Use 5-second HTTP checks with three attempts for diagnostics without tunnel termination.
- [x] Distinguish local and cloud API failure causes with bounded secret-free evidence, preserve definitive root causes across later generic pool failures, and keep the official `codex` executable and gateway responses unchanged.

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
- [x] Publish a versioned compatibility profile referencing the existing handshake, health, gateway, credential, release, and rollback contracts; add a new runtime schema only if existing contracts cannot express a required state without ambiguity.
- [x] Define a scoped, revocable, rotatable Phi cloud consumer credential that cannot import accounts, mutate gateway configuration, activate releases, or represent a Phi device.
- [x] Add a rollback-protected exact-confirmation installer for the dedicated Phi consumer gateway key, preserving the existing Cloudx client credential and keeping Phi service restart plus previous-key revocation separate and unauthorized.
- [x] Define bounded concurrency, rate-limit, queue/backpressure, timeout, and retry semantics for a single Phi cloud consumer without adding Task or device concepts to Cloudx.
- [x] Make capacity output distinguish healthy capacity, exhausted capacity, unknown observation, stale contract, probe failure, and incompatible producer without leaking account identity.
- [x] Add a strict Cloudx-side failure-semantics matrix for gateway, capacity, credential, rate-limit, rollback, and independent-ordering failures; bind it to an exact Phi canonical snapshot while keeping cross-repository runtime acceptance truthfully blocked.
- [x] Package an explicit migration-only legacy health bridge in the signed cloud source, bind its conservative mapping to a strict schema/example and the exact Phi N-1 parser digest, and provide fixed-artifact offline templates without authorizing publication, installation, service start, or rollback.
- [x] Rehearse the bridge against the real Cloudx rollback implementation in an isolated release root, proving fixed-artifact and byte-stable behavior across `0.1.13/0.1.12` rollback and restoration while keeping production runtime acceptance false.
- [x] Add a default-read-only exact-confirmation installer for the signed bridge unit files that retains a rollback set, performs only `daemon-reload`, keeps the candidate disabled/inactive, and preserves the enabled active legacy exporter.
- [x] Package a signed production-path-isolated systemd canary and a default-read-only exact-confirmation runner that validates and removes temporary output without starting the primary bridge or changing the legacy path.
- [x] Add a default-read-only exact-confirmation overlap-first cutover transaction that rehearses primary-to-legacy rollback and primary restoration without a publisher gap, selector change, or gateway/importer restart.
- [ ] Verify current and previous protocol compatibility and independent Phi/Cloudx upgrade and rollback ordering.
- [x] Verify Cloudx logs, health, receipts, release state, and public errors contain no Phi Task, session, device, lease, approval, local path, transfer content, or Artifact metadata.
- [ ] Verify the Phi privileged boundary cannot read Cloudx auth or invoke import, gateway mutation, or Cloudx release mutation as an Agent capability.

The Cloudx metadata verification is enforced in code rather than recorded as a one-time scan: every cloud-runtime stdout/stderr path is centralized, published health/account state is checked before atomic write, signed cloud release manifests are checked before staging, versioned contract schemas/examples are audited, and prohibited-field/error fixtures fail before bytes are emitted. The scoped credential policy's literal-false non-representation fields and signed Cloudx release artifact records are the only explicit distinctions.

The ordering verification now has an explicit compatibility path rather than a declaration: `config/governance/phi_cloudx_release_ordering.v1.json` binds exact Cloudx and Phi release refs, and `scripts/check_phi_cloudx_release_ordering.py` evaluates the complete pair/order matrix. `config/governance/phi_cloudx_legacy_health_bridge.v1.json` separately binds published `0.1.15` source, artifact-ref commit, manifest digest, signer fingerprint, fixed primary/canary templates, installer/canary/cutover contracts, exact Phi N-1 consumer digest, and isolated selector round trip. Its checker requires the annotated release tag to resolve to the recorded source, executes all three read-only operator plans against the immutable `0.1.15` artifact path, keeps every authorization bit false, and rejects any canary capable of writing `/var/lib/cloudx/health`. The first unchecked item remains open on two production gates: bridge unit runtime acceptance and independent runtime rollback rehearsal.

The privileged-boundary verification now has the same fail-closed form: `config/governance/phi_cloudx_privileged_boundary.v1.json` binds exact deployed Phi refs to a secret-free credential, identity, and Agent-surface permission snapshot, and `scripts/check_phi_cloudx_privileged_boundary.py` derives effective Cloudx auth/import/gateway/release authority. Current interactive and mail surfaces remain blocked by reachable unrestricted elevation and the non-scoped administrative gateway credential; the `NoNewPrivileges`-confined orchestrator evaluates safe. The credential installer closes a source/tooling gap only: the second unchecked item remains open until the dedicated group/credential are installed and all normal Agent surfaces prove no Cloudx authority.

The failure-semantics verification is separately executable: `config/governance/phi_cloudx_failure_semantics.v1.json` freezes the matching owner/truth invariants, nine required failure cases, exact Phi canonical-file digests, and the current Phi Roadmap statuses. `scripts/check_phi_cloudx_failure_semantics.py` checks those cases against the actual Cloudx capacity, credential, traffic, and compatibility contracts, then incorporates the release-ordering and privileged-boundary results. Its optional `--phi-root` mode verified the recorded commit, file digests, and Roadmap statuses without changing the Phi checkout. The matrix is complete, but `--require-accepted` correctly remains nonzero until all five external/runtime blockers are resolved.

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

## M4B: CPA Credential Failure And Concurrency Safety

Status: signed Cloudx `0.1.17` is active on cloud and local with signed N-1 retained. The staged `.policy.1` candidates and never-staged `.policy.2` source candidates are superseded. Cloud `.policy.3` is durably staged and inactive; local `.policy.3` remains unstaged. The revised policies separate the two-request business ceiling from trigger-only high-concurrency incident diagnosis, retain the immediate direct-permanent receipt path, and add identity-free aggregate pool observations. Policy activation and dual watchers remain separately unapproved.

This milestone implements the operator-requested external CPA safety boundary without upgrading either installed upstream revision or making Cloudx the CPA lifecycle owner.

- [x] Audit the exact local v7.0.1 custom build and cloud v7.2.71 build, their auth scheduler, refresh paths, launchd/systemd contracts, and current process identities; confirm upstream standalone CPA has no enforced inference-concurrency ceiling.
- [x] Define strict `cloudx.cpa-auth-failure.v1` evidence with one conclusive enumerated permanent-auth result, fixed `weeklyQuota=false`, a fresh observation window, exact auth-file digest binding, and no archive authority for provisional refreshable failures.
- [x] Add local top-level-only and cloud exact-parent receipt consumers with bounded non-symlink reads, private state, same-filesystem reversible archive, atomic manifest rollback, aggregate-only output, and exact-confirmation restore.
- [x] Restore source `codexx api refresh --apply` compatibility for the existing local maintenance LaunchAgent without taking ownership of the external CPA service.
- [x] Pin revised exact CPA patches and deterministic `.policy.3` identities for Darwin/arm64 and Linux/amd64; recognize `deactivated_workspace`, emit on the first conclusive permanent failure, emit an identity-free trigger only for final aggregate `auth_unavailable`, preserve the local `fast -> priority` service-tier compatibility, and enforce one process-global two-request business ceiling with waiting backpressure.
- [x] Add default-read-only build and deployment plans with separate stage/activation confirmations, side-by-side candidate paths, retained baseline binaries, private rollback snapshots, health/policy canaries, and automatic launcher/unit restoration on activation failure.
- [x] Verify focused Python and Go regressions, rebuild both candidates independently from clean exact commits to identical SHA-256 values, and execute the cloud Linux candidate identity check from remote `/tmp` while the active gateway remains unchanged.
- [x] Accept the exact OpenAI OAuth CPA export wrapper without weakening provider checks; record that the separately imported ten records are one deactivated non-refreshable workspace and do not provide cloud fallback capacity.
- [x] Add local communication-continuity gating: real official-Codex requests before/after activation and after rollback, plus a private 180-second deferred worker so the authorizing CPA-backed turn finishes before restart.
- [x] Publish signed Cloudx `0.1.16` containing the receipt consumers; verify immutable refs, signatures, GitHub assets, self-checks, previous-root rejection, and selector-free idempotent isolated staging.
- [x] Stage and activate signed Cloudx `0.1.16` on cloud, retain signed `0.1.13` as N-1, accept self-check/release-status/handshake plus one natural CPA-health exit-`0` run with truthful aggregate `probe_error`, and preserve CPA PID/restart count plus auth/archive inventories.
- [x] Reproduce the cloud false-negative: direct interactive HTTPS lacked the declared proxy, while the correct mihomo path returned HTTP `402 deactivated_workspace` that `0.1.16` did not classify; prove 45/45 sequential permanent results and reversibly archive exactly 45 without a CPA restart.
- [x] Add an infrastructure/provider gate, explicit external proxy input, trigger-only full-pool probing with independent adaptive concurrency up to 32, identical-credential deduplication, bounded permanent-error parsing, direct conclusive archive, and Phi read-only boundary; retain quota/429, refreshable 401, network/TLS/DNS/timeout/5xx, and unknown failures, and retain the trigger when infrastructure is unavailable.
- [x] Keep the network-free receipt-only fast path, add a distinct network-capable aggregate incident sweep, release the archive lock during probes, package the signed trigger-aware health service/timer plus both systemd path/service pairs, and provide one rollback-protected watcher activation transaction. Local watches both private inputs with a two-minute missed-trigger fallback; cloud atomically replaces the old health unit, preserves its timer state, and reduces the five-minute path to trigger consumption only; neither watcher action restarts CPA or Codex.
- [x] Publish signed Cloudx `0.1.17`; verify immutable refs, signatures, all seven assets, source identity, stable selection, both self-checks, previous-root rejection, exact offline-bundle parity, and selector-free idempotent staging.
- [x] Install and activate signed Cloudx `0.1.17` on cloud, retain `0.1.16` as N-1, accept signature/source/artifact, self-check, release-status, handshake, and natural zero-account health evidence, and preserve CPA/importer identities plus all unit bytes.
- [x] Install and activate signed Cloudx `0.1.17` locally, retain `0.1.13` as N-1, pass fresh-shell and real official-Codex-through-CPA acceptance, and preserve CPA PID/listener plus every pre-existing Codex process.
- [x] Retain the previously staged `.policy.1` candidates as inactive evidence, mark the never-staged `.policy.2` source candidates superseded, and independently build matching `.policy.3` bytes twice from both exact upstream commits plus the shared supplemental trigger patch.
- [x] Stage the exact cloud `.policy.3` candidate after its distinct confirmation; verify binary/manifest identity and preserve CPA PID/restart count, baseline selection, unit bytes, credentials, archive, and Cloudx selectors.
- [ ] Stage the exact local `.policy.3` candidate only after its distinct confirmation, preserving CPA/listener and all existing Codex processes.
- [ ] Activate `.policy.3` cloud then local only after signed Cloudx `0.1.17` is active on the matching endpoint; accept health, two-request business-policy, real communication, trigger emission, and rollback canaries while retaining original binaries and snapshots.
- [ ] Activate the cloud then local dual failure/sweep watchers through their separate exact confirmations only after each `.policy.3` producer is live; verify immediate receipt archive, aggregate-trigger sweep latency/concurrency, zero-probe idle fallback, trigger retention on infrastructure failure, unit/launcher rollback, and unchanged CPA/Codex processes.
- [ ] Import at least one independently verified usable cloud CPA credential and pass live model traffic without restoring the 45 known-deactivated archive records; write acceptance alone is not capacity evidence.
- [ ] Prove with natural traffic that concurrent proxied business requests never exceed two; idle maintenance creates no account probes; aggregate `auth_unavailable` rapidly calibrates the pool above business concurrency two; weekly quota creates no archive; one provisional refreshable 401 creates no archive; one conclusive permanent refresh/auth result archives exactly one digest-matched credential; and exact restore returns it safely.

### M4B Stop Conditions

- Any candidate digest, upstream commit, active baseline digest, launcher/unit path, auth directory, or service identity differs from the pinned contract.
- A weekly/quota/rate-limit/network/timeout/5xx condition emits or consumes a permanent-auth receipt.
- A stage action changes a process, listener, launcher, unit, credential, archive, or release selector.
- Local activation is attempted synchronously from a CPA-backed Codex turn, before signed Cloudx `0.1.17` is active, or without successful real communication canaries before candidate selection, after candidate selection, and after any rollback.
- Activation cannot restore the prior external CPA selection and healthy listener automatically after a failed canary.
- Cloudx receipt consumers are not yet running from a signed current release with the previous signed release retained for rollback.
- A watcher is activated before its exact signed consumers and matching `.policy.3` producer; the direct receipt consumer performs a network request; the aggregate sweep runs without a fresh trigger or skips its infrastructure gate; or either path restarts CPA, Codex, Cloudx, or Phi.

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
- [x] Validate the completed root-only rollback snapshot against current runtime/unit/failure bytes, refresh attributed quiet-traffic evidence, and record a machine `preconditions-satisfied` decision that still requires separate operator confirmation.
- [x] Add a default-read-only exact-confirmation stop/restore transaction that requires fresh signed stop-gate parity, verifies the rollback manifest, closes only port `8780`, repeats SSH/health/Phi/gateway canaries, and automatically restores the importer on failure.
- [x] Replace the legacy quota monitor writer only after Cloudx health and reversible quarantine have accepted observation evidence.
- [x] Disable and archive the unattended import repair timer.
- [ ] Remove the old codex-plus shell hook and installed package only after native `codex`, account switching, and rollback pass in a fresh shell.
- [x] Add a default-read-only exact-confirmation quarantine/restore transaction for the live local codex-plus runtime, launcher, and recovery entrypoint while preserving official Codex/Git, Cloudx selectors/hook/entrypoints, external CPA state, accounts, and the private recovery bundle.
- [x] Validate native return, API compatibility selection, named-account selection, official Codex resolution, cloud mode, private recovery, and release-matched rollback in isolated fresh shells; publish and activate the hardened signed hook without editing the regenerated active shim.
- [x] Publish and stage signed `0.1.13` so repeated hook installation is whitespace-idempotent and read-only SSH probes detach from caller stdin while import and release-stage payloads retain explicit byte pipes; activation remains separate.
- [x] Rehearse exact signed `0.1.13` activation, release-matched rollback, reactivation, post-cutover hook reconciliation, scripted cloud selection, and source `0.1.14` alias-root N-1 protection in isolated roots without moving production selectors.
- [x] Activate signed `0.1.13` in production, repeat the local same-version hook reconciliation, complete the formal dual-endpoint N-1 round trip, and accept initial plus final API/cloud model canaries with all protected identities unchanged.
- [x] Add an exact-confirmation stage-only installer path for a lagging endpoint whose old updater cannot verify the current stable index; use it to stage signed `0.1.13` on `/Users/BofeiChen` with exact release signature/self-check and no selector, hook, profile, backup, other-endpoint, CPA, listener, broker, or process change.
- [x] Stage signed `0.1.12` idempotently beside `0.1.13` on `/Users/BofeiChen` as the exact intended N-1 candidate while retaining active `0.1.8/0.1.7` and granting no activation or service-change authority.
- [x] Rehearse the `/Users/BofeiChen` physical-root activation order from `0.1.8/0.1.7` through `0.1.12 -> 0.1.13`, release-matched rollback/reactivation, same-version hook reconciliation, and fresh-shell official Codex preservation without moving production selectors or processes.
- [x] Replace source `codexx import`'s package-level `codexx-legacy` dependency with a bounded, locked, atomic Cloudx-native compatibility adapter for the external local CPA; retain the installed legacy rollback path until signed activation and real import acceptance.
- [x] Add a default-read-only, exact-confirmation release trust-recovery preparation tool with clean-worktree, external-key-path, private-mode, three-root parity, fingerprint-change, atomic-write, rollback, and non-authorization guarantees; do not execute the real rotation without a separate decision.
- [x] Execute the separately confirmed `0.1.15` release trust rotation, retain the private key outside Git, synchronize and verify only the three public roots, and keep tag/publication/staging/activation/restart authority separate.
- [x] Add a default-offline exact-confirmation GitHub release-environment key synchronization transaction with pushed-HEAD/root binding, stdin-only secret transfer, a non-publishing signed workflow canary, unchanged-ref proof, and explicit no-tag failure semantics.
- [x] Synchronize the replacement key into the GitHub `release` environment and accept a non-publishing signed workflow run with successful verification/build/evidence steps and unchanged stable/tag/artifact refs.
- [x] Publish immutable signed `0.1.15`, verify tag workflow and GitHub assets, require new-root acceptance plus old-root rejection, and stage both artifacts idempotently only in selector-free isolated roots.
- [x] Rehearse the complete replacement-root release pipeline in an isolated temporary source tree: build and sign both candidates plus the stable index, require old-root rejection, verify candidate-embedded new-root acceptance, and stage both endpoints idempotently without activation or real key/ref/endpoint mutation.
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
