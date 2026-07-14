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

## Rollback

Rollback restores the previous endpoint symlink, cloud first only when local compatibility requires it, and otherwise local first. It never restores an old credential or session directory. Cached N-1 artifacts and an offline bundle make rollback independent of GitHub and the model API.
