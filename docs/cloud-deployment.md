# Cloud Deployment

The initial cloud deployment is shadow-only. It uses:

- `/opt/cloudx/releases/<version>` for immutable code
- `/opt/cloudx/current` for the manually selected release
- `/etc/cloudx` for configuration and the scoped local-client credential
- `/var/lib/cloudx/shadow-auth` for importer canary output
- `/run/cloudx-shadow` for locks and secret-free health

The service templates under `cloud/systemd/` use a distinct `cloudx-shadow-*` name and do not conflict with legacy importer or gateway units.

Shadow units execute the exact signed artifact selected by `CLOUDX_CLOUD_ARTIFACT` in `/etc/cloudx/cloudx-shadow.env`. They do not read `/opt/cloudx/current`, so observation can run from a staged version without activating Cloudx for any other invocation.

`cloudx-shadow-account-state` is a read-only adapter for the legacy quota summary. It emits only aggregate counts into `/run/cloudx-shadow/accounts.json`. Legacy `failed` observations remain explicitly unobserved and are not guessed to be unavailable; health consumers can derive that count as total minus the classified counts. Health freshness is derived from the source observation timestamp, so replaying stale input cannot make it appear fresh.

The scoped client credential file must be owned by the account that executes `cloudx-remote client-config` and have mode 0600 or stricter. It is never included in health, handshake, logs, Git, or a release bundle.

The Phi consumer uses a different credential at `/etc/cloudx/consumers/phi-cloud/credential`. Source `0.1.15` provides a default-read-only exact-confirmation installer for that key, but it requires the Phi-owned group membership and root/group mode-0750 parent directory to exist first. The transaction preserves the Cloudx client credential exactly, retains the previous Phi key during rotation, restarts only the external gateway, and does not install or restart Phi. Running the plan, building a release, or staging an artifact performs no gateway or credential write.

For the first canary, configure the existing gateway address explicitly. Do not change the gateway bind address, API key, CLIProxyAPI unit, mihomo, Tailscale, or SSH. `cloudx-remote self-check`, `handshake`, `health`, and a dry-run import must pass before any unit is enabled.

## Active Health Publisher Preparation

The signed cloud artifact also carries read-only templates under `cloudx_cloud/data/systemd/` for a future active `cloudx.health.v1` publisher. An operator can inspect an exact template without installing it:

```bash
cloudx-remote systemd-template cloudx-account-state.service
cloudx-remote systemd-template cloudx-account-state.timer
cloudx-remote systemd-template cloudx-health.service
cloudx-remote systemd-template cloudx-health.timer
```

The account-state adapter writes aggregate state to `/run/cloudx-account-state/accounts.json`. The health publisher runs as `cloudx`, writes the mode-0644 contract to `/run/cloudx/health.json`, reads the importer lock without creating or modifying it, and cannot access gateway configuration or credential directories. Merely building, publishing, staging, or activating a Cloudx artifact does not install, enable, start, or restart these units. Their deployment is a separate operator-confirmed Cloudx maintenance action that must finish before the Phi M4 consumer window; an M4 Phi change cannot deploy or restart Cloudx.

The accepted `0.1.7` deployment keeps the signed base units and adds `10-active-paths.conf` drop-ins because systemd gives `EnvironmentFile` values precedence over the base unit's `Environment` declarations. The drop-ins set only the two declared `/run` output paths through `ExecStart` and preserve the runtime directories after successful oneshot exits. Repository `0.1.8` moves those settings into the signed templates and uses activation-relative first timer deadlines, so the next release does not require the drop-ins.

## Versioned CPA Health Preparation

Repository `0.1.8` also carries `cloudx-cpa-health.service` and `.timer` as signed artifact data. The service executes `cpa-health` from `/opt/cloudx/current/cloudx-cloud.pyz`, so production no longer needs to execute the monitor from a mutable Git checkout after a separately approved unit migration.

This batch deliberately keeps `/opt/codex-gateway/codexx_app` as an explicit, read-only compatibility dependency. The signed Cloudx adapter owns locking, private atomic state, aggregate output redaction, and the call boundary, while the legacy runtime temporarily supplies the existing quota probe and reversible quarantine primitives. Removing that dependency is a later M5 item and must not be hidden inside this migration.

The adapter's journal output contains only aggregate counts. Candidate paths and archived filenames remain only in root-readable runtime state. Building or activating a Cloudx release does not install, enable, start, or restart these units; replacing the current production unit remains a separately confirmed maintenance action with the existing unit retained as rollback.

The accepted `0.1.8` maintenance action activated the cloud endpoint before the local endpoint, without reinstalling the shell hook or seeding a profile. It then installed the signed CPA-health service and timer, reloaded systemd, and restarted only `cloudx-cpa-health.timer`. The former unit, timer, private state, unit status, and credential-directory inventory are retained under `/var/lib/cloudx/cpa-health-service-backups/20260715T095526Z` with root-only permissions.

Two natural timer activations completed successfully from the signed artifact. Both emitted aggregate-only healthy summaries for 15 accounts, created no quarantine candidate, and left the production auth and archive inventories unchanged. The timer then returned to its five-minute cadence. The compatibility dependency on `/opt/codex-gateway/codexx_app` remains explicit; neither the old importer nor that runtime package is retired by this cutover.

Source `0.1.9` replaced that compatibility import boundary with native standard-library auth scanning and HTTP quota classification. Signed `0.1.10` is the accepted production release after immutable `0.1.9` was rejected during cloud staging for a stale embedded trust root. The native implementation rejects symlinked, non-regular, oversized, and over-count credential inputs; preserves direct, nested-token, and sub2api bundle parsing; and writes refresh state and quarantine manifests atomically with mode 0600. Quarantine uses a locked same-filesystem rename and restores the source automatically if its manifest transaction fails. The explicit restore command requires the quarantined filename to be repeated as confirmation and emits no filename or account identity.

Signed `0.1.10` passed cloud-side read-only parity, candidate-verified staging, cloud-first/local-second activation, complete model canaries, and endpoint-only N-1 rollback rehearsals. Its native unit templates passed `systemd-analyze verify` and replaced only the CPA-health service/timer in a rollback-protected transaction. Two natural timer invocations returned aggregate-only healthy results and left anonymous auth/archive inventories unchanged. Cloudx CPA health no longer needs `/opt/codex-gateway/codexx_app`, but the active legacy HTTP importer still imports `codexx_app.cloud_import_server`; removing the runtime therefore remains gated on separate importer retirement and rollback acceptance.

## Legacy Health Bridge Preparation

Source `0.1.15` carries `legacy-health-bridge.v1` plus a strict `cloudx.legacy-health.v1` schema/example for the previous Phi consumer. The bridge reads only bounded regular-file `cloudx.health.v1`, maps aggregate counts without inventing login, process, failure-receipt, active-session, or recovery-time facts, and atomically writes the legacy document with mode `0644`. Missing freshness remains unobserved and unavailable accounts map to `other`, not guessed login failure.

The packaged `cloudx-legacy-health-bridge.service` reads an operator-created `/etc/cloudx/legacy-health-bridge.env` whose sole value selects an exact `/opt/cloudx/releases/<version>/cloudx-cloud.pyz`. It deliberately does not follow `/opt/cloudx/current`, has no network address family beyond `AF_UNIX`, and can write only `/var/lib/cloudx/health`. Building, publishing, staging, or activating the artifact does not install, enable, start, or restart the bridge. The mutable-checkout legacy exporter remains in place until a separately confirmed side-by-side candidate, output comparison, Phi N-1 rollback, and restoration transaction pass.

Source `0.1.15` also provides `scripts/install_legacy_health_bridge_units.py`. Its default plan is read only; exact-confirmation apply can install only the exact staged artifact's four fixed environment/canary/service/timer files and run `daemon-reload`. It requires the old timer to remain active/enabled, every candidate to remain inactive, and the primary timer to remain disabled; it saves a root-only rollback set and changes no selector or output. Merely running the plan, building, publishing, staging, or activating a release does not grant that installation authority; running the canary or starting the primary bridge remains a later maintenance action.

Signed `0.1.15` is now published from exact source `9ffa3208f39053c2b3af1136a530ce98eac7ad41` under immutable artifact ref `332cb865a97d654efca4b4321b90cdc140e57e64`. Fresh clones and downloaded assets passed replacement-root signature verification and isolated idempotent staging; the previous root rejected the release. No production endpoint is staged or activated by publication. The bridge runtime gate is therefore reduced only from three blockers to two: fixed-unit installation and independent production rollback/cutover acceptance.

Signed `0.1.16` is published from exact source `ec77369a990418f2a990874d1d7bd4b9d2c7fe04` under immutable artifact ref `9513ff87b3b2e45d2b3609f0746248a7422d34b2`, with stable at `bba9f619fc2d3e57cbd1b2808fe97ac58e805aef`. It contains the strict CPA failure-receipt consumers and the OpenAI OAuth export compatibility required by M4B. Fresh verification passed signatures, asset identity, self-checks, and selector-free idempotent staging. Publication alone did not change `/opt/cloudx/current`, the CPA-health unit, any credential, or any service; cloud-first then local endpoint activation remains separately confirmed.

Signed `0.1.17` is published from exact source `0bf7461c9c421b55031c8d17c0951bc8321a0ba9` under immutable artifact ref `d720979dc46ff5a7b4cb1ba121aca92849e0e09a`, with stable at `82a35ff57ae97c4fd655d14ce2bf28c4304cd31b`. It contains the aggregate `auth_unavailable` sweep trigger, trigger-only high-concurrency credential calibration, direct receipt fast path, and dual signed watcher templates required by corrected M4B. Fresh verification passed signatures, previous-root rejection, all asset and bundle identities, self-checks, and selector-free idempotent staging. Publication left cloud at `0.1.16/0.1.13`, CPA PID `977036`, restart count `0`, and did not install a unit, credential, or policy; cloud-first endpoint installation remains separately confirmed.

Signed `0.1.18` is published from exact source `f94c926daa929d8d9801722013408eb9ebb7e90a` under immutable artifact ref `5e345ed8cbf0373ac9e6214e45358187a524ea5d`, with stable at `d3275fd150bceaa50c216c13a99969b58409992d`. It contains the independently executable local CPA recovery bundle, shared automatic/manual recovery path, repeated zero-connection gate, and secret-free activation-stage evidence required before another local `.policy.3` restart attempt. Fresh verification passed signatures, previous-root rejection, all seven asset and offline-bundle identities, self-checks, and selector-free idempotent staging. Publication left cloud and local on signed `0.1.17`, did not restart either CPA, and did not install a release, unit, credential, watcher, or policy; cloud-first then local endpoint installation remains separately confirmed.

Signed `0.1.19` is published from exact source `51c5294ed6dd5b504ef4384e9860c70e2593ae78` under immutable artifact ref `d4bddf35a1305186ffe568438ceaca6afb5cce61`, with stable at `e5f7fafb7539b09f5b3e0f5424999bccd5a06dac`. It closes the production-discovered sweep vocabulary gap so a conclusive non-refreshable HTTP 401 with reason `authentication_unauthorized` becomes a digest-bound permanent archive candidate while quota, refreshable 401, transport, timeout, and provider failures remain excluded. Fresh verification passed signatures, pre-rotation-root rejection, all seven asset and offline-bundle identities, self-checks, and selector-free idempotent staging. Publication left both endpoints on signed `0.1.18/0.1.17`, did not restart either CPA, and did not install a release, unit, credential, watcher, or policy; cloud-first then local `0.1.19` installation remains separately confirmed.

Signed `0.1.20` is published from exact source `eefd8a4aa70d554ac32babe3ff7aa1ae9996e875` under immutable artifact ref `d6bce9346d86b2b133057df01ced068ef3eef9b2`, with stable at `11edbaf440d0f38958743aea279ddc36ea9320e5`. It carries the deterministic CPA `.policy.4` contracts and recovery-bounded acceptance update: final `auth_unavailable` and all-candidate `model_cooldown` produce the same identity-free incident trigger while quota, ordinary 429, refreshable 401, network, timeout, and provider failures remain excluded from archive authority. Fresh verification passed signatures, pre-rotation-root rejection, all seven asset and offline-bundle identities, both self-checks, stable selection, and selector-free idempotent staging. Publication left both endpoints on signed `0.1.19/0.1.18`, did not restart either CPA, and did not install a release, unit, credential, watcher, or policy; cloud-first then local `0.1.20` installation remains separate from `.policy.4` stage and activation.

Signed `0.1.21` is published from exact source `f46a0e39887722bd20301270dc3e84d030f8058d` under immutable artifact ref `00148d962a8e90b213b36ef5cb8fcae46a046029`, with stable at `2e402391d4a5782af5602738cb2a714248f2a41f`. It corrects the unreachable `.policy.4` cooldown producer by exposing a typed pool-unavailable capability on the real upstream `modelCooldownError` and consuming it before the handler's `coreauth.Error` cast; archive authority and the stable identity-free trigger contract are unchanged. Fresh verification passed signatures, pre-rotation-root rejection, all seven asset and offline-bundle identities, both self-checks, stable selection, and selector-free idempotent staging. Publication left both endpoints on signed `0.1.20/0.1.19`, did not restart either CPA, and did not install a release, unit, credential, watcher, or policy; cloud-first then local `0.1.21` installation remains separate from `.policy.5` stage and activation.

The separately confirmed cloud endpoint install now selects `0.1.17/0.1.16` without restarting CPA or changing any unit byte. Artifact, manifest, self-check, release status, handshake, CPA/importer identities, and archive inventory passed. The current zero-account health run had concurrency zero. The pre-existing health unit deliberately remains unchanged until the separate watcher transaction installs the signed trigger-aware health service/timer together with the failure/sweep paths; do not import usable capacity before that transaction is accepted.

The later approved `0.1.18` cloud install now selects `0.1.18/0.1.17`. It used the immutable tag installer plus explicit existing mihomo proxy environment, staged the exact artifact, and moved only release selectors. CPA PID `1613475`, importer PID `133756`, restart counts `0`, health, zero active auth, 45-entry archive, empty failure/sweep inputs, and all inspected unit bytes remained unchanged. No service or watcher was restarted or activated; local installation remains the next separate transaction.

The installed set now includes a fourth static canary service. It shares the signed artifact selection and hardening rules but publishes only to `/run/cloudx-legacy-health-bridge-canary/v1.json` and explicitly masks `/var/lib/cloudx/health`. `scripts/run_legacy_health_bridge_canary.py` defaults to a read-only plan and, after separate exact confirmation, may start only this canary, validate and remove the temporary document, and stop it on failure. It never starts the primary service, enables the primary timer, changes the old exporter, or moves a release selector.

`scripts/rehearse_legacy_health_bridge_cutover.py` is the separately confirmed production transition. It requires the canary first, then performs overlap-first primary cutover, old-exporter rollback, and primary restoration with no point at which both timers are intentionally inactive. It retains the old service and a root-only backup, and fails closed if Cloudx selectors, CLIProxyAPI, or the real `codex-import.service` continuity changes. Running its plan, building, publishing, staging, installing files, or running the isolated canary grants no cutover authority.

Repository `0.1.11` prepares that importer migration by carrying a signed `codex-gateway-import` compatibility adapter. Inspect it without installing anything:

```bash
cloudx-remote compatibility-script codex-gateway-import
```

The adapter preserves FILE/stdin and `--force`, adds an explicit `--dry-run`, and routes bytes directly to `cloudx-remote import`. It contains no HTTP endpoint, token-file read, or curl dependency. Installing the script and stopping the old HTTP service remain separate confirmation-gated actions.

Source `0.1.15` adds `scripts/stop_http_importer.py` for the latter action. Its default plan is offline and non-authorizing. Exact-confirmation apply requires fresh signed stop-gate parity plus the existing complete rollback manifest, disables only `codex-import.service`, proves the listener closed, repeats the real SSH dry-run import and health/consumer/model canaries, and restores the importer on any failure. It does not remove the service, runtime, keys, receipts, snapshot, exporter, or any external dependency. Building, publishing, staging, activating, evaluating the stop gate, or running the plan grants no stop authority.
