# 2026-07-15 M2 Scoped-Key And Shadow Acceptance

This document records the explicitly approved scoped-key maintenance transaction and the completed M2 shadow canary. It does not record a Cloudx release activation.

## Approved Gateway Transaction

Operator approval allowed one restart of `cliproxy.service` for a dedicated Cloudx key.

- Signed cloud artifact: `0.1.2`, source commit `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e`
- Gateway version: `7.2.71`
- Gateway config SHA-256 before: `1553bd677e7ba7ead7b37c799a65da476472660544dff35ad234d5aa3942cc34`
- Gateway config SHA-256 after: `8c1430544b796335b452478d0d9f73a0f0ac82e44d706d9f88104f42f627aa5b`
- Existing key count: `3`; post-transaction key count: `4`
- Gateway PID before: `586892`; gateway PID after: `977036`
- Scoped model-list probe: HTTP `200`
- Restored config/auth inotify watches: `2`
- Rollback backup: `/etc/cliproxy/backups/config.yaml.before-cloudx-1784089942`
- Credential metadata: mode `0600`, owner `cloudx:cloudx`
- Shadow environment metadata: mode `0640`, owner `root:cloudx`

The installer verified that the staged artifact self-check reported cloud `0.1.2` before writing any gateway state. It changed only the declared gateway config, scoped credential, shadow environment, backup, and gateway process.

## Handshake And Health

The restricted `cloudx` identity returned `cloudx.handshake.v1` with protocol `1..1`, deployment `shadow-0.1.2`, gateway `healthy`, and import contract `1`.

The distinct `cloudx-shadow-health.timer` was enabled. Both account-state and health oneshots completed with exit status `0`. The adapter was pointed at the active aggregate `/var/lib/cloudx/cpa-health/state.json`, not the disabled legacy quota-monitor state.

Fresh health evidence:

- schema: `cloudx.health.v1`
- Cloudx version: `0.1.2`
- gateway: `healthy`
- importer: `ready`
- freshness: `fresh`, age `109` seconds at capture
- source counts: total `15`, ready `15`, warning `0`, limited `0`, failed `0`
- adapted counts: total `15`, available `15`, limited `0`, unavailable `0`, unobserved `0`
- source-to-adapter comparison: exact match

No credential, key, account identity, or raw account record entered handshake or health output.

## Real SSH Import Canary

The staged local `0.1.2` artifact read a fake credential from a local path and sent it through real SSH stdin to the staged cloud `0.1.2` importer running as `cloudx`.

- dry-run: accepted, written `1`, skipped `0`
- first shadow transaction: accepted, written `1`, skipped `0`
- identical replay: accepted, written `0`, skipped `1`
- normalized file mode and owner: `0600`, `cloudx:cloudx`
- shadow root before and after cleanup: empty
- raw canary source search after cleanup: no match

The canary wrote only `/var/lib/cloudx/shadow-auth`. It did not invoke the legacy HTTP importer or target `/var/lib/codex-gateway/cliproxy-auth`.

## Tunnel And Model Canary

`cloud codex --check` selected remote mode `cloudx`, created a separate broker on local port `29226`, and received gateway HTTP `200`. A complete official Codex request returned exactly `CLOUDX_SCOPED_KEY_OK`.

The canary broker had zero leases after the request and was shut down cleanly. The legacy listener remained PID `78601` on `127.0.0.1:18317` throughout.

## Continuity And Cleanup

- `codex-import.service` retained PID `133756` and remained active.
- `cliproxy.service` performed only the approved restart and remained active on PID `977036`.
- `/opt/cloudx/current` remained absent.
- `/usr/local/bin/cloudx-remote` remained absent.
- Local `/Users/BofeiChen/.local/lib/cloudx/current` remained absent.
- Temporary local fixture, temporary remote helper, normalized fake credential, and canary broker were removed.
- Production CLIProxyAPI auth contents were not read or written by the Cloudx importer; the active CPA health service retained its independent ownership of health classification.

M2 shadow acceptance is complete. M3 cloud and local activation remain separate operator-confirmed actions.
