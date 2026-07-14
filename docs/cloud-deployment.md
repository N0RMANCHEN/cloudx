# Cloud Deployment

The initial cloud deployment is shadow-only. It uses:

- `/opt/cloudx/releases/<version>` for immutable code
- `/opt/cloudx/current` for the manually selected release
- `/etc/cloudx` for configuration and the scoped local-client credential
- `/var/lib/cloudx/shadow-auth` for importer canary output
- `/run/cloudx-shadow` for locks and secret-free health

The service templates under `cloud/systemd/` use a distinct `cloudx-shadow-*` name and do not conflict with legacy importer or gateway units.

`cloudx-shadow-account-state` is a read-only adapter for the legacy quota summary. It emits only aggregate counts into `/run/cloudx-shadow/accounts.json`. Legacy `failed` observations remain explicitly unobserved and are not guessed to be unavailable; health consumers can derive that count as total minus the classified counts. Health freshness is derived from the source observation timestamp, so replaying stale input cannot make it appear fresh.

The scoped client credential file must be owned by the account that executes `cloudx-remote client-config` and have mode 0600 or stricter. It is never included in health, handshake, logs, Git, or a release bundle.

For the first canary, configure the existing gateway address explicitly. Do not change the gateway bind address, API key, CLIProxyAPI unit, mihomo, Tailscale, or SSH. `cloudx-remote self-check`, `handshake`, `health`, and a dry-run import must pass before any unit is enabled.
