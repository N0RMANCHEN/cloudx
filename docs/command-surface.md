# Command Surface And Compatibility

This is the accepted local interaction model during M3. The official Codex runtime, local CPA gateway, cloud gateway, and legacy recovery path remain distinct.

## Runtime Selection

| Intent | Command | Persisted effect |
|---|---|---|
| Use the native profile seeded from `soul0` | `codex` | None |
| Select a named account in the current shell | `codexx <name>` | Changes `CODEX_HOME`; records last selection |
| Preserve legacy selection syntax | `codexx use <name>` | Same as `codexx <name>` |
| Select the local CPA profile | `codexx cpa` | Sets `CODEX_HOME` to the existing `cpa` profile |
| Select the existing local API/CPA profile | `codexx api` | Sets `CODEX_HOME` to the existing `api` profile |
| Select cloud mode | `codexx cloud` | Creates a shell-owned broker lease and selects the isolated cloud profile |
| Return to the native profile | `codexx exit` | Clears Cloudx account variables |
| Inspect selection | `codexx current`, `codexx list` | Read-only |

Mode selection never changes or wraps the official `codex` executable and never changes the real user `HOME`. Cloud mode keeps its broker lease for the selecting shell, so plain `codex` remains valid for the full foreground session.

## Account Lifecycle

```bash
codexx add <name>
codexx login [name]
codexx status [name]
codexx logout [name]
codexx rename <old> <new>
codexx remove <name>
```

These commands operate on `~/.codex-accounts/<name>/.codex`. Pool selection, task control, dashboards, workspaces, agents, and automatic rotation are not part of Cloudx.

## Cloud Gateway

```bash
codexx cloud
codex
codexx cloud import <local-file-or-directory> --dry-run
codexx cloud import <local-file-or-directory>
```

`codexx cloud` acquires a broker lease owned by the current shell and configures an isolated Cloudx `CODEX_HOME`; the following `codex` remains the official local binary. `codexx cloud import` reads a local path and sends its bytes through SSH stdin to the cloud importer. `cloud codex` and `cloud import` remain compatibility entrypoints.

In zsh, the active selection is shown at the right edge as `[cx:api]`, `[cx:cloud]`, or `[cx:<account>]`. Cloudx appends only its own segment, preserves existing `RPROMPT` content, and removes its segment after `codexx exit`.

The low-level single-file equivalent is:

```bash
ssh cloud cloudx-remote import --dry-run < local-file
```

`ssh cloud import local-file` cannot upload a local path because arguments after the SSH host are resolved on the remote host.

## Migration-Only HTTP Importer Gate

The signed cloud artifact can evaluate a separately captured sanitized stop-gate evidence document:

```bash
cloudx-remote http-importer-stop-gate < sanitized-stop-gate-evidence.json
```

The input is limited to 64 KiB, must use `cloudx.http-importer-stop-gate-evidence.v1`, and rejects missing, unknown, duplicate, mistyped, or internally inconsistent fields. Exit `0` means the declared preconditions are satisfied; exit `2` returns deterministic blockers; exit `1` rejects invalid evidence.

The result is `cloudx.http-importer-stop-gate.v1`, binds the canonical evidence with a SHA-256 digest, contains no account identity or credential data, labels itself `migration-only`, sets `automaticAction=false`, and always keeps `authorization.serviceStop=false`. It neither collects root-only evidence nor authorizes or performs a service change.

## Phi Mesh Compatibility Profile

The signed cloud artifact publishes the static compatibility profile with:

```bash
cloudx-remote compatibility-profile
```

The result is `cloudx.phi-mesh-compatibility-profile.v1`. It references the existing handshake, health, gateway, credential-bearing client configuration, signed release, and rollback contracts; records protocol-overlap, N/N-1, offline rollback, and independent release-ordering requirements; contains no credential; and grants no runtime or mutation authority. Reading it does not probe the gateway or read Cloudx runtime configuration.

The adjacent credential policy is also read-only:

```bash
cloudx-remote phi-consumer-credential-policy
```

`cloudx.phi-cloud-consumer-credential.v1` defines a distinct mode-`0640` secret outside Git and release directories, readable only through the future dedicated Phi consumer group. The bearer represents the Phi cloud service, never a device, Task, or session. It is accepted only for gateway inference and carries no SSH, `cloudx-remote`, import, gateway-configuration, or release authority. The policy describes overlap-first rotation and revocation ordering but does not install, rotate, revoke, or restart anything.

The traffic policy is published alongside it:

```bash
cloudx-remote phi-consumer-traffic-policy
```

`cloudx.phi-cloud-consumer-traffic-policy.v1` defines the initial single-consumer ceilings: four in-flight logical requests, sixteen FIFO waiters, thirty gateway attempts per minute with burst four, bounded admission/connect/header/idle/overall timeouts, and at most three attempts with capped jittered backoff. Queue overflow and admission timeout fail before a gateway attempt. Retries stay in the logical request's original concurrency slot, consume the same rate budget, and stop permanently once any response bytes arrive. The document installs no limiter and gives Cloudx no Task, scheduling, or queue ownership.

Read the live aggregate capacity classification with the consumer's supported protocol range:

```bash
cloudx-remote capacity --consumer-protocol-min 1 --consumer-protocol-max 1 --json
```

`cloudx.capacity.v1` returns exactly one of `healthy_capacity`, `exhausted_capacity`, `unknown_observation`, `stale_contract`, `probe_failure`, or `incompatible_producer`. It probes the gateway and reads the existing aggregate account-state input without writing either. Missing or unobserved accounts remain unknown rather than being guessed exhausted; output contains no account identity or credential.

## Local CPA Compatibility

The existing local CLIProxyAPI remains an external launchd service on `127.0.0.1:8317`. Cloudx preserves its use through the existing `api` and `cpa` profiles:

```bash
codexx cpa
codex

codexx api
codex

codexx import <local-file-or-directory>
```

Cloudx does not own the local CLIProxyAPI process, binary upgrades, launchd lifecycle, credential refresh, or provider pool. During the observation period, the private recovery bundle exposes the old management surface explicitly as:

```bash
codexx-legacy api status
codexx-legacy api refresh --dry-run
```

`codexx-legacy` is a rollback tool, not a supported Cloudx command. It is removed only after the local CPA dependency has a separately accepted replacement or ownership decision.

During this migration stage, `codexx import` explicitly delegates local CPA normalization to that recovery runtime. The delegation is temporary and reported in product documentation; it does not grant Cloudx ownership of the local CPA service.

The legacy local adapter has no Cloudx dry-run contract. A real local import therefore requires an operator-selected source and is not used as a synthetic write canary. Cloud import has the explicit `--dry-run` path shown above.

## Installation

```bash
./install
./install local --version <signed-version> --apply --confirm "INSTALL CLOUDX LOCAL <version>"
sudo ./install cloud --version <signed-version> --apply --confirm "INSTALL CLOUDX CLOUD <version>"
```

The local installer stages the signed local artifact, creates a private legacy recovery bundle when needed, seeds the native profile, installs the shell source into `.zshrc`, and activates stable links. The cloud installer requires the scoped credential/environment prerequisite, stages the signed cloud artifact, and activates the helper without restarting a service.

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
