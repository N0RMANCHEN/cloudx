# Command Surface And Compatibility

This is the accepted local interaction model during M3. The official Codex runtime, local CPA gateway, cloud gateway, and legacy recovery path remain distinct.

## Runtime Selection

| Intent | Command | Persisted effect |
|---|---|---|
| Use the native profile seeded from `soul0` | `codex` | None |
| Select a named account in the current shell | `codexx <name>` | Changes `CODEX_HOME`; records last selection |
| Preserve legacy selection syntax | `codexx use <name>` | Same as `codexx <name>` |
| Select the local CPA profile | `codexx cpa` | Sets `CODEX_HOME` to the existing `cpa` profile |
| Select the existing local API profile | `codexx use api` | Sets `CODEX_HOME` to the existing `api` profile |
| Return to the native profile | `codexx exit` | Clears Cloudx account variables |
| Inspect selection | `codexx current`, `codexx list` | Read-only |

Account selection never changes the official `codex` executable and never changes the real user `HOME`. It changes only `CODEX_HOME` and Cloudx account markers in the current shell.

## Account Lifecycle

```bash
codexx add <name>
codexx login [name]
codexx status [name]
codexx logout [name]
```

These commands operate on `~/.codex-accounts/<name>/.codex`. Pool selection, task control, dashboards, workspaces, agents, and automatic rotation are not part of Cloudx.

## Cloud Gateway

```bash
cloud codex --check
cloud codex [official Codex arguments]
cloud import <local-file-or-directory> --dry-run
cloud import <local-file-or-directory>
```

`cloud codex` runs the official local Codex process through the Cloudx-owned broker and the active cloud helper. `cloud import` reads a local path and sends its bytes through SSH stdin to the cloud importer.

The low-level single-file equivalent is:

```bash
ssh cloud cloudx-remote import --dry-run < local-file
```

`ssh cloud import local-file` cannot upload a local path because arguments after the SSH host are resolved on the remote host.

## Local CPA Compatibility

The existing local CLIProxyAPI remains an external launchd service on `127.0.0.1:8317`. Cloudx preserves its use through the existing `api` and `cpa` profiles:

```bash
codexx cpa
codex

codexx use api
codex
```

Cloudx does not own the local CLIProxyAPI process, binary upgrades, launchd lifecycle, credential refresh, or provider pool. During the observation period, the private recovery bundle exposes the old management surface explicitly as:

```bash
codexx-legacy api status
codexx-legacy api refresh --dry-run
```

`codexx-legacy` is a rollback tool, not a supported Cloudx command. It is removed only after the local CPA dependency has a separately accepted replacement or ownership decision.

## Signed GitHub Updates

```bash
cloudx-update check
cloudx-update stage <version>
cloudx-update apply <version> --confirm <version> --cloud-only
cloudx-update apply <version> --confirm <version> --local-only
cloudx-update rollback --confirm <previous-version> --local-only
cloudx-update rollback --confirm <previous-version> --cloud-only
```

One signed GitHub release contains independent local and cloud artifacts. Checking and staging never activate a release. Cloud and local activation remain separate explicit transactions. Both endpoints retain a staged N-1 release as `previous` for offline rollback.

## Ownership Summary

Cloudx owns account selection, the local cloud tunnel broker, cloud helper integration, SSH import, health contracts, and signed release synchronization. Tailscale, SSH, local and cloud VPNs, mihomo, CLIProxyAPI, launchd, and systemd remain declared external dependencies.
