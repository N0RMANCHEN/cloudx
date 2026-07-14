# Operations

## Safety First

Never use a build, test, or update command against the active legacy local port `18317`. Do not restart CLIProxyAPI, mihomo, Tailscale, SSH, or an active importer as an incidental Cloudx action.

## Build And Verify

```bash
./verify.sh
./build.sh
```

Artifacts are written to `dist/`. Building has no install or activation side effects.

Replay the accepted fake importer matrix in an automatically cleaned temporary directory with:

```bash
python3 scripts/replay_import_fixtures.py
```

For an M2 host, pass a shadow root and repeat its resolved path with `--confirm-shadow-root`. The verifier creates an isolated child directory, compares canonical normalized files, repeats every transaction for idempotence, confirms raw sources were not retained, and removes its child directory unless `--retain` is explicitly requested.

Tunnel broker status includes `lastReconnectMilliseconds` after an SSH child exit. M2 evidence should record this field together with the stable `publicPort` and incremented `generation`; HTTP probe failures must leave all three unchanged.

Installing the dedicated gateway key is an explicit maintenance action because it restarts the external `cliproxy.service`. A read-only invocation prints the required confirmation:

```bash
python3 scripts/install_scoped_gateway_key.py \
  --build-commit <signed-release-commit> \
  --gateway-version <observed-version>
```

The `--apply` path requires the exact printed confirmation. It preserves the existing YAML text, writes a mode-0600 backup, installs the restricted credential and shadow environment atomically, restarts only the declared gateway unit, verifies a real model-list request and both config/auth inotify watches, and restores all files plus the old service configuration if any check fails.

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
