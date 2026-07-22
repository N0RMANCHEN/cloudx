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
codexx cloud import <local-file-or-directory> --json
```

`codexx cloud` acquires a broker lease owned by the current shell and configures an isolated Cloudx `CODEX_HOME`; the following `codex` remains the official local binary. `codexx cloud import` reads a local path and sends its bytes through SSH stdin to the cloud importer. `cloud codex` and `cloud import` remain compatibility entrypoints.

In an interactive terminal, local and cloud imports use the same user-facing summary: `Status`, `Destination`, `Imported`, `Skipped`, `Verification`, and, on failure, one or more safe `Reason` fields. Local CPA success reports its completed post-write verification and labels the migration adapter. Cloud success states that import-time verification was not performed because `accepted` means the credential was stored transactionally, not that its live login or quota is healthy. Rejected and partial results return nonzero and write their summary to stderr.

For pipeline compatibility, redirected cloud-import stdout remains the raw `cloudx.import.v1` JSON document and redirected local-import output remains the legacy adapter's count output. `--json` forces the raw cloud contract even when stdout is an interactive terminal.

## API Failure Diagnosis

```bash
codexx diagnose
codexx diagnose api --json
codexx api diagnose
codexx cpa diagnose
codexx cloud diagnose
cloud diagnose
```

The active-mode form chooses local API/CPA or cloud automatically. Every form uses the same user vocabulary and the secret-free `cloudx.api-diagnosis.v1` JSON contract. Causes include `account_deactivated`, `quota_exhausted`, `rate_limited`, `login_required`, `access_denied`, `no_usable_accounts`, gateway authentication/network/server failures, upstream failure, and `unknown`.

Local diagnosis reads only the bounded response portion of recent CLIProxyAPI error logs. Cloud diagnosis uses a passive observer in the existing tunnel relay. Neither path reads a Codex request body into its result, exposes a credential or account identity, changes the response delivered to Codex, wraps the official executable, restarts CLIProxyAPI, or changes account routing. If a definitive 429/401/deactivation/permission response is followed by generic `503 auth_unavailable`, the definitive cause remains primary and the later response appears as `maskedBy=no_usable_accounts`.

This is a post-failure diagnostic surface, not an in-band rewrite of the external gateway's OpenAI-compatible response. When no retained structured failure exists, Cloudx reports that the cause is undetermined; `/v1/models` success proves gateway reachability only.

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

Repository operators can inspect the separate transaction with `python3 scripts/stop_http_importer.py --release-version <version>`. The default plan reads no evidence and opens no SSH connection. Its distinct exact-confirmation apply requires fresh source/signed-artifact gate parity and a verified rollback snapshot, then stops only `codex-import.service`, runs the real SSH import and health/consumer/model canaries, and restores the service on any failure. It never removes the retained legacy assets.

## Phi Mesh Compatibility Profile

The signed cloud artifact publishes the static compatibility profile with:

```bash
cloudx-remote compatibility-profile
```

The result is `cloudx.phi-mesh-compatibility-profile.v1`. It references the existing handshake, health, gateway, credential-bearing client configuration, signed release, and rollback contracts; records protocol-overlap, N/N-1, offline rollback, and independent release-ordering requirements; contains no credential; and grants no runtime or mutation authority. Reading it does not probe the gateway or read Cloudx runtime configuration.

The source-ready migration bridge can be inspected without writing a file:

```bash
cloudx-remote legacy-health-bridge --source /run/cloudx/health.json
```

Supplying `--publish-to /var/lib/cloudx/health/v1.json` performs one bounded, validated, atomic mode-`0644` publication. The bridge preserves unknown process state, unobserved accounts, and unavailable-reason ambiguity instead of probing credentials, the old importer, or failure directories. Its packaged unit uses an exact immutable artifact selected by `/etc/cloudx/legacy-health-bridge.env`, not `/opt/cloudx/current`, so Cloudx endpoint rollback cannot silently remove the compatibility command. The command and templates do not install or start the unit and do not authorize replacement of the current legacy exporter.

Repository operators can inspect the distinct unit-file plan with `python3 scripts/install_legacy_health_bridge_units.py --release-version <version>`. The default invocation is non-authorizing. Exact-confirmation apply installs the signed templates disabled and inactive and performs only `daemon-reload`; it does not publish or activate a release, start/enable the candidate, stop/disable the current exporter, or write legacy health output.

After those inactive files exist, `python3 scripts/run_legacy_health_bridge_canary.py --release-version <version>` prints a second non-authorizing plan. Its separately confirmed apply starts only the signed static canary, writes and validates one temporary `/run` document, then removes it. The canary unit masks the production legacy-health directory, so this command cannot cut over the legacy consumer path or replace final rollback evidence.

`python3 scripts/rehearse_legacy_health_bridge_cutover.py --release-version <version>` prints the final non-authorizing cutover plan. Its distinct exact confirmation covers a real overlap-first primary/legacy/primary round trip and root-only backup. No plan or canary invocation authorizes it, and the transaction rejects any selector, gateway, importer, or Phi-service continuity change.

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

All cloud-helper JSON, static text, and stderr messages pass through the same fail-closed public metadata guard. A document containing Phi Task/session/device/lease/approval identifiers, a local user path, transfer content, ContextRequest, LocalAction, or Phi Artifact metadata is rejected before output. Cloudx release `artifacts` remain allowed because they are signed Cloudx release records, not Phi user Artifacts.

## Local CPA Compatibility

The existing local CLIProxyAPI remains an external launchd service on `127.0.0.1:8317`. Cloudx preserves its use through the existing `api` and `cpa` profiles:

```bash
codexx cpa
codex

codexx api
codex

codexx import <local-file-or-directory|-> [--dry-run] [--json]
```

Cloudx does not own the local CLIProxyAPI process, binary upgrades, launchd lifecycle, credential refresh, or provider pool. During the observation period, the private recovery bundle exposes the old management surface explicitly as:

```bash
codexx-legacy api status
codexx-legacy api refresh --dry-run
```

`codexx-legacy` is a rollback tool, not a supported Cloudx command. Source `0.1.15` no longer invokes it for normal imports, but the installed older release and private recovery bundle remain intact until the native adapter passes signed production acceptance.

Source `0.1.15` performs local CPA normalization inside the signed Cloudx artifact. It supports flat CPA JSON, sub2api exports or account entries, cliproxy auth bundles, JSON arrays, JSONL/NDJSON/concatenated objects, bounded directory discovery, stdin, and the existing raw-card refresh format. The adapter writes only to `localCpa.authDir`, `CLOUDX_LOCAL_CPA_AUTH_DIR`, or the default `~/.cli-proxy-api`; that path must be absolute and cannot be inside Cloudx release or state directories.

Source `0.1.22` also recognizes tokenless Sub2API `agentIdentity` records. It accepts only a bounded RFC 8410 Ed25519 PKCS#8 private key plus runtime ID, writes the signing metadata with mode `0600`, forces HTTP rather than websocket transport, and discards the unsigned synthetic ID token and source gateway's task ID. Preview and apply both fail with `external_capability_missing` unless `cloudx.local-cpa-capabilities.v1` binds the exact current executable SHA-256 and the running loopback health endpoint advertises `codex-agent-identity-v1`. The check repeats on every import, so a CPA update cannot inherit stale authorization. Import does not build, patch, replace, configure, or restart that service; a compatible external CPA registers a fresh task and signs `AgentAssertion` headers itself.

Source `0.1.15` also includes a repository operator transaction for eventually quarantining the installed legacy runtime, launcher, and `codexx-legacy` entrypoint. Its default output is offline and non-authorizing; it is not part of the supported `codexx` command surface. Apply remains a separate exact-confirmation M5 action after the native adapter's signed activation and real import/rollback acceptance, and it preserves the external CPA, accounts, Cloudx shell/entrypoints, and the original private recovery bundle.

Each candidate is bounded to 16 MiB, each directory to 1,024 candidates and 64 MiB total. Apply uses a bounded exclusive lock, rejects symlink sources/targets, writes mode-`0600` JSON through atomic replacement, verifies exact bytes and validated credential material, and restores every changed target if a later write fails. Existing identical normalized files are reported as unchanged. The adapter does not restart, configure, or otherwise manage CLIProxyAPI.

Interactive output uses the same status/destination/count/verification/failure vocabulary as cloud import. Redirected output retains stable count lines; `skipped` is the total of ignored sources, duplicate credentials, and unchanged targets, while those component counts remain separately visible. `--json` emits `cloudx.local-cpa-import.v1`. `--dry-run` parses, normalizes, deduplicates, checks target conflicts, and reports prospective writes without creating the auth directory, lock, or credential file. Raw-card dry-run validates the card shape without sending its refresh token.

## Installation

```bash
./install
./install local --version <signed-version> --stage-only
./install local --version <signed-version> --stage-only --apply --confirm "STAGE CLOUDX LOCAL <version>"
sudo ./install cloud --version <signed-version> --stage-only --apply --confirm "STAGE CLOUDX CLOUD <version>"
./install local --version <signed-version> --apply --confirm "INSTALL CLOUDX LOCAL <version>"
sudo ./install cloud --version <signed-version> --apply --confirm "INSTALL CLOUDX CLOUD <version>"
```

Stage-only mode fetches one exact `release-artifacts/v<version>` ref, verifies its release signature, artifact digest, and self-check with the current repository trust root, and writes only the side-by-side release directory. It does not create a legacy backup, seed a profile, install a shell source, move `current` or `previous`, contact the other endpoint, or restart a process. This provides a recovery path when an older installed updater cannot verify the current stable index after an approved signing-root transition.

The ordinary local installer stages the signed local artifact, creates a private legacy recovery bundle when needed, installs the shell source into `.zshrc`, and activates stable links. It preserves an existing complete native auth/config pair byte-for-byte; only a fully absent pair is initialized from the validated requested seed account, while partial or unsafe state fails before any installation mutation. The ordinary cloud installer requires the scoped credential/environment prerequisite, stages the signed cloud artifact, and activates the helper without restarting a service.

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
