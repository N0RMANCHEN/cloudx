# 2026-07-14 Shadow Identity And Account-State Evidence

This document records the restricted service identity, versioned shadow environment, and read-only account-state adapter deployment. The health publisher and scoped client credential are not yet active.

## Restricted Shadow Environment

- Service identity: system user and group `cloudx`, UID `993`, GID `985`, shell `/usr/sbin/nologin`
- `/etc/cloudx`: mode 0750, owner `root:cloudx`
- `/etc/cloudx/cloudx-shadow.env`: mode 0640, owner `root:cloudx`
- `/var/lib/cloudx/shadow-auth`: mode 0700, owner `cloudx:cloudx`
- `/run/cloudx-shadow`: mode 0750, owner `cloudx:cloudx`
- Configured artifact: `/opt/cloudx/releases/0.1.1/cloudx-cloud.pyz`
- Configured source commit: `2fc4c0a8ecc9a60e3858d721d070a36fffa04ed6`
- Configured existing gateway endpoint: `100.90.97.113:8317`

No `/opt/cloudx/current` symlink was created.

## Read-Only Account-State Adapter

- `cloudx-shadow-account-state.timer` is enabled and active.
- The oneshot service completed with result `success` and exit status `0`.
- `/run/cloudx-shadow/accounts.json` is mode 0644 and contains only aggregate state.
- Legacy total: 65
- Adapted available: 40
- Adapted limited: 0
- Adapted unavailable: 0
- Adapted unobserved: 25
- The adapted counts and unobserved count exactly matched the legacy summary mapping.

The adapter did not read or write the production auth directory and did not copy account identities into its output.

## Gateway Configuration Recovery Note

A scoped-key installation was attempted with automatic rollback. Every attempt restored the exact original gateway config SHA-256 `1553bd677e7ba7ead7b37c799a65da476472660544dff35ad234d5aa3942cc34`, retained three existing API keys, removed the candidate credential, and left `cliproxy.service` on PID `586892` with restart count `0`.

The first atomic config replacement removed CLIProxyAPI's inode-based config-file inotify watch. The auth-directory watch, running gateway, existing API keys, and request path remain available, but future config hot reload is unavailable until an explicitly approved `cliproxy.service` restart. No restart was performed. Secret-bearing rollback copies and temporary installer files were removed after the original config was verified.

## Production Continuity

- `cliproxy.service` retained PID `586892`, restart count `0`, and active timestamp `98063220486`.
- `codex-import.service` retained PID `133756`, restart count `0`, and active timestamp `43952803944`.
- The production auth directory retained metadata `131173:1783989250:1783989250:700:cliproxy:cliproxy`.
- The Cloudx scoped client credential remains absent and the health publisher remains stopped.
