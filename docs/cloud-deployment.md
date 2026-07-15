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

Repository `0.1.11` prepares that importer migration by carrying a signed `codex-gateway-import` compatibility adapter. Inspect it without installing anything:

```bash
cloudx-remote compatibility-script codex-gateway-import
```

The adapter preserves FILE/stdin and `--force`, adds an explicit `--dry-run`, and routes bytes directly to `cloudx-remote import`. It contains no HTTP endpoint, token-file read, or curl dependency. Installing the script and stopping the old HTTP service remain separate confirmation-gated actions.
