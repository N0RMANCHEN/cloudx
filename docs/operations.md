# Operations

## Safety First

Never use a build, test, or update command against the active legacy local port `18317`. Do not restart CLIProxyAPI, mihomo, Tailscale, SSH, or an active importer as an incidental Cloudx action.

## Build And Verify

```bash
./verify.sh
./build.sh
```

Artifacts are written to `dist/`. Building has no install or activation side effects.

The CPA-health probe can be inspected without state or quarantine writes:

```bash
sudo /usr/bin/python3 /opt/cloudx/current/cloudx-cloud.pyz cpa-health --check
```

After a native CPA-health release is explicitly activated, restore one quarantined file only with its exact private archive filename repeated as confirmation:

```bash
sudo /usr/bin/python3 /opt/cloudx/current/cloudx-cloud.pyz \
  cpa-health-restore <quarantined-file.json> \
  --confirm <quarantined-file.json>
```

The restore response is aggregate-only. Inspect the root-readable quarantine manifest before the action; the command refuses ambiguous selectors, an existing destination, an invalid manifest, or a cross-filesystem move.

Replay the accepted fake importer matrix in an automatically cleaned temporary directory with:

```bash
python3 scripts/replay_import_fixtures.py
```

For an M2 host, pass a shadow root and repeat its resolved path with `--confirm-shadow-root`. The verifier creates an isolated child directory, compares canonical normalized files, repeats every transaction for idempotence, confirms raw sources were not retained, and removes its child directory unless `--retain` is explicitly requested.

Tunnel broker status includes `lastReconnectMilliseconds` after an SSH child exit. M2 evidence should record this field together with the stable `publicPort` and incremented `generation`; HTTP probe failures must leave all three unchanged.

Installing the dedicated gateway key is an explicit maintenance action because it restarts the external `cliproxy.service`. A read-only invocation prints the required confirmation:

```bash
python3 scripts/install_scoped_gateway_key.py \
  --release-version <staged-version> \
  --build-commit <signed-release-commit> \
  --gateway-version <observed-version>
```

The read-only plan derives the cloud artifact path from the exact staged version. The `--apply` path first requires that artifact's self-check to report the same version, then requires the exact printed confirmation. It preserves the existing YAML text, writes a mode-0600 backup, installs the restricted credential and version-matched shadow environment atomically, restarts only the declared gateway unit, verifies a real model-list request and both config/auth inotify watches, and restores all files plus the old service configuration if any check fails.

## Import A Local File Over SSH

Use the local Cloudx command when the source path exists on the local machine:

```bash
cloud import ~/Downloads/credentials.json --dry-run
cloud import ~/Downloads/credentials.json
```

`cloud import` reads the local file or supported directory, applies the 16 MiB limit, and sends the bytes to `cloudx-remote import` over SSH stdin. The remote importer validates and normalizes the content under its configured auth directory with locking and atomic replacement.

Do not use `ssh cloud import ~/Downloads/credentials.json` for a local path. OpenSSH runs everything after the host on the remote machine, so that path would be resolved on the cloud host and no local file bytes would be transferred. The low-level equivalent for a single file is `ssh cloud cloudx-remote import < ~/Downloads/credentials.json`; `cloud import` is the supported interface and also handles directories safely.

## HTTP Importer Stop Gate

Before requesting the separate legacy HTTP importer stop transaction, capture root-readable evidence without including key contents, account identities, credential paths, request bodies, or raw failure inputs. Normalize only the declared aggregate facts into `cloudx.http-importer-stop-gate-evidence.v1`, then evaluate them through the exact signed cloud artifact:

```bash
cloudx-remote http-importer-stop-gate < sanitized-stop-gate-evidence.json
```

The evaluator checks the active/enabled service baseline, stable identity, port `8780`, established connections, readable and attributed traffic, later requests, transaction locks, raw failure inputs, formal import readiness, SSH adapter boundary and signed-artifact verification, legacy health readers, systemd requirements, and all required rollback snapshots. It does not impose a calendar delay; the evidence must instead prove the focused traffic and dependency gates directly.

The command reads at most 64 KiB and writes nothing. Unknown or duplicate fields are rejected so credentials cannot be smuggled into a nominal evidence record. A `preconditions-satisfied` result is bound to the exact evidence digest but explicitly reports `automaticAction=false` and `authorization.serviceStop=false`. Stopping or disabling `codex-import.service` still requires a separately approved transaction and the full rollback/canary sequence in the roadmap.

## Stage

Local releases live under `~/.local/lib/cloudx/releases/<version>` and cloud releases under `/opt/cloudx/releases/<version>`. State, configuration, credentials, sessions, and logs live elsewhere.

Staging verifies the manifest signature and artifact hash, expands into a new version directory, and runs offline self-checks. It does not change `current`.

## Activate

Activation is explicit and ordered:

1. verify the local offline rescue entrypoint
2. stage both endpoints
3. verify remote handshake and protocol selection
4. activate the cloud helper
5. run shadow health and importer checks
6. activate local entrypoints for new invocations
7. run tunnel, gateway, and real model canaries

Ordinary Cloudx activation must not restart CLIProxyAPI. A gateway or network boundary change is a separate maintenance procedure and confirmation.

The very first cloud activation cannot call `cloudx-remote` because that stable helper does not exist yet. Run the bootstrap plan on the cloud host, inspect its versioned paths, and rerun it with `--apply` plus the exact printed confirmation:

```bash
python3 scripts/bootstrap_cloud_helper.py --release-version <version> --operator <ssh-user>
```

The bootstrap is restricted to an absent `/opt/cloudx/current` and helper installation. It verifies the staged artifact version, installs root-owned launchers and a validated sudoers fragment, atomically activates `current`, checks a healthy handshake and release status, and removes every installed path if verification fails. Normal handshake, client configuration, health, and import commands always run as the restricted `cloudx` identity. Only signed release stage, activation, and rollback subcommands can run as root. It does not restart a service. All later activation and rollback operations use the normal endpoint-specific updater commands below.

The updater rejects a combined endpoint change. Activate each endpoint with its own exact version confirmation and inspect the cloud symlink state independently:

```bash
cloudx-update apply <version> --confirm <version> --cloud-only
cloudx-remote release-status
cloudx-update apply <version> --confirm <version> --local-only
```

Shell-hook installation and native-profile seeding remain local-only options and are rejected on a cloud-only activation.

## Rollback

Rollback restores the previous endpoint symlink, cloud first only when local compatibility requires it, and otherwise local first. It never restores an old credential or session directory. Cached N-1 artifacts and an offline bundle make rollback independent of GitHub and the model API.

Rollback also changes only one endpoint per confirmed command:

```bash
cloudx-update rollback --confirm <previous-version> --local-only
cloudx-update rollback --confirm <previous-version> --cloud-only
```
