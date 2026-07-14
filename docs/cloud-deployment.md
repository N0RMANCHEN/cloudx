# Cloud Deployment

The initial cloud deployment is shadow-only. It uses:

- `/opt/cloudx/releases/<version>` for immutable code
- `/opt/cloudx/current` for the manually selected release
- `/etc/cloudx` for configuration and the scoped local-client credential
- `/var/lib/cloudx/shadow-auth` for importer canary output
- `/run/cloudx-shadow` for locks and secret-free health

The service templates under `cloud/systemd/` use a distinct `cloudx-shadow-*` name and do not conflict with legacy importer or gateway units.

The scoped client credential file must be owned by the account that executes `cloudx-remote client-config` and have mode 0600 or stricter. It is never included in health, handshake, logs, Git, or a release bundle.

For the first canary, configure the existing gateway address explicitly. Do not change the gateway bind address, API key, CLIProxyAPI unit, mihomo, Tailscale, or SSH. `cloudx-remote self-check`, `handshake`, `health`, and a dry-run import must pass before any unit is enabled.
