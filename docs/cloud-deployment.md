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
