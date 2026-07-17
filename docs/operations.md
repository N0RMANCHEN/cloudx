# Operations

## Safety First

Never use a build, test, or update command against the active legacy local port `18317`. Do not restart CLIProxyAPI, mihomo, Tailscale, SSH, or an active importer as an incidental Cloudx action.

## Build And Verify

```bash
./verify.sh
./build.sh
```

Artifacts are written to `dist/`. Building has no install or activation side effects.

## Prepare Release Trust Recovery

When an immutable failed tag has no published artifact and the matching private release key is unavailable, inspect the non-mutating recovery plan:

```bash
python3 scripts/prepare_release_trust_recovery.py \
  --version 0.1.15 \
  --private-key /absolute/repository-external/path/to/key
```

The plan contains no private path or key material and grants no action. After a separate explicit trust-rotation decision, use its exact confirmation with `--apply`. The transaction generates a mode-`0600` Ed25519 key outside the repository, requires its parent directory to be mode `0700`, atomically replaces the repository/local/cloud `allowed_signers` files, verifies their shared replacement fingerprint, and restores the old roots plus removes generated key files on failure.

Do not combine this preparation with commit, tag, publication, stable selection, staging, activation, service restart, or legacy removal. Each later step keeps its own evidence and authorization gate.

The separately approved `0.1.15` rotation is complete. The current public signer fingerprint is `SHA256:oEhvhqj9U4wM8zLz8w43A/fvMN+BRNXO1k5/3eVPh9o`; its private key remains outside the repository with mode `0600`. Do not rerun recovery against the same path or copy that private key into Git, a release directory, an endpoint bundle, logs, or operator notes. Creating the release tag, signing/publishing artifacts, moving stable, staging endpoints, and activation are still later independent steps.

## Synchronize The Release Workflow Key

Before creating `v0.1.15`, inspect the GitHub Actions key synchronization plan without reading the private key, Git state, remote refs, GitHub authentication, environment, secret metadata, or workflow runs:

```bash
python3 scripts/synchronize_release_workflow_key.py \
  --version 0.1.15 \
  --private-key /absolute/repository-external/path/to/key
```

The `cloudx.release-workflow-key-plan.v1` output contains no private path or material and keeps all authorization fields false. Apply requires the exact printed confirmation, a clean `main` whose `HEAD` equals `origin/main`, a mode-`0700` key directory and mode-`0600` non-symlink Ed25519 key outside the repository, byte-identical committed public roots with the same fingerprint, authenticated `gh` access, and the fixed `N0RMANCHEN/cloudx` repository, `release` environment, `release.yml` workflow, and `CLOUDX_RELEASE_SIGNING_KEY` secret name.

The transaction validates that `workflow_dispatch` runs verification/build/signature checks but both publication steps remain tag-only. It snapshots stable, `v0.1.15`, and `release-artifacts/v0.1.15` refs; sends the private bytes only through GitHub CLI stdin; dispatches the pushed `main`; requires the signed release canary to succeed; and requires every release ref unchanged. It creates no tag, artifact ref, stable move, endpoint stage/activation, or service restart.

GitHub secret values cannot be read back, so this transaction cannot restore the previous value after a successful write. All reversible checks happen first. Any later metadata, dispatch, run, or ref failure returns nonzero and explicitly says not to create the release tag. Reauthenticate or resolve the GitHub run, then repeat the separately confirmed canary with the same matching key; never guess that a failed client response means the old secret was restored.

The separately confirmed `0.1.15` synchronization is complete. The `release` environment secret did not exist before the transaction and was created at `2026-07-17T12:09:03Z`. Workflow-dispatch run `29579236303` completed successfully on commit `f245186f62f298dba015f7a122a63eb2db177b33`: repository verification, key loading, signed build, and release-evidence verification passed; tag verification, signed-ref publication, and GitHub Release publication were skipped. Stable remained at its prior ref, and neither `v0.1.15` nor `release-artifacts/v0.1.15` was created.

Recording this receipt creates a later documentation commit. Before tagging, dispatch `release.yml` once more on the final pushed `main` and require a successful run whose `headSha` equals that exact tag target; this verification-only dispatch must again leave all release refs unchanged. It does not rewrite the secret and does not itself authorize tag creation.

## Diagnose API Failures

Run diagnosis immediately after a failed Codex turn:

```bash
codexx diagnose
codexx api diagnose
codexx cpa diagnose
codexx cloud diagnose
codexx diagnose --json
```

`codexx diagnose` selects the active `api`, `cpa`, or cloud mode; an explicit target works outside an active selection. The JSON form is `cloudx.api-diagnosis.v1`. A successfully formed diagnosis exits zero even when it describes a failure; command/configuration errors remain nonzero.

For local CPA, Cloudx reads only bounded `=== API RESPONSE ===` and response-status sections from recent external CLIProxyAPI error logs. It does not emit request bodies, headers, account identities, API keys, or raw upstream messages. For cloud mode, the tunnel broker observes plaintext response bytes already crossing its relay and retains only the enumerated cause, HTTP status, normalized signal, observation time, optional reset time, and masking relationship. It neither changes forwarded bytes nor restarts or reconfigures the tunnel or gateway.

The result distinguishes explicit account deactivation, exhausted allowance or credits, transient request/token rate limits, invalid/expired/reused login credentials, access/model denial, client-to-gateway authentication, network reachability, gateway/server failure, and insufficient evidence. A generic `503` `auth_unavailable`/`no auth available` is never guessed to mean quota or deactivation; when it follows a definitive upstream failure within the bounded retention window, the earlier root cause is retained and the later masking response is reported separately. A reachable `/v1/models` probe with no recent failure evidence is not presented as proof that an upstream account has quota.

Cloud observation begins when a broker process from the updated local artifact starts naturally. Verification, staging, and activation do not stop an older active broker, and diagnosis never terminates one.

## Import Into The External Local CPA

Preview or apply an operator-selected local source with:

```bash
codexx import ~/Downloads/credentials.json --dry-run
codexx import ~/Downloads/credentials.json
codexx import ~/Downloads/credentials.json --json
```

The source may also be a bounded directory or `-` for redirected stdin. `--name-prefix` controls filenames only when the normalized credential has no email or source hint. The compatibility default permits replacement of a different same-name target, but writes are locked, atomic, mode `0600`, verified, and rolled back as one transaction if any later write fails. Identical normalized targets are unchanged rather than rewritten.

The default target is `~/.cli-proxy-api`. Configure a different external auth directory with `localCpa.authDir` in the local Cloudx config or `CLOUDX_LOCAL_CPA_AUTH_DIR`; the path must be absolute and outside Cloudx release/state roots. Cloudx never starts, stops, restarts, upgrades, or reconfigures the external CPA as part of import. A preview performs no filesystem or token-refresh write side effect.

`codexx-legacy` remains a private rollback command for older installed releases. Do not remove its recovery bundle until a signed release containing the native adapter has been activated, a real local import and rollback have passed, and the separate M5 deletion decision is approved.

## Prepare Legacy Local Package Quarantine

Inspect the local retirement transaction without reading the home directory, process table, listener state, package, or recovery data:

```bash
python3 scripts/remove_legacy_local_package.py \
  --release-version <active-signed-native-import-version>
```

The default `cloudx.legacy-local-removal-plan.v1` document keeps every authorization field false. Do not use `--apply` until the exact signed native-import release is active on this endpoint and a separately approved real import/rollback acceptance window exists. A staged release, source checkout, successful test, or printed plan grants no authority.

Exact-confirmation apply takes a user-private lock, verifies the active artifact and current/previous selectors, requires one Cloudx shell hook with no old hook, inventories a bounded non-symlink live runtime, and matches the launcher/runtime hashes to the retained private recovery manifest. It refuses a legacy process, an open port `18317`, an unavailable or changed external CPA on port `8317`, or a failed native-import/fresh-shell check.

The transaction then moves only `~/.local/bin/codexx_app`, `~/.local/bin/codexx.py`, and `~/.local/bin/codexx-legacy` into a private retained quarantine on the same filesystem. It repeats native import, fresh-shell mode selection, selector/hook/entrypoint checks, and external CPA continuity after the move. Any failure restores every moved target before returning nonzero. Success is a quarantine receipt, not deletion: accounts, CPA binary/configuration/LaunchAgent, Cloudx entrypoints and hook, official Codex/Git, the original recovery bundle, and the quarantine all remain; no process is terminated and no service is restarted.

Inspect the exact signed Phi Mesh compatibility profile without reading a credential, probing the gateway, or changing runtime state:

```bash
cloudx-remote compatibility-profile
```

The profile references the current public contracts and compatibility rules only. It is not an access grant, deployment instruction, or service-change authorization.

Inspect the proposed Phi cloud consumer credential boundary separately:

```bash
cloudx-remote phi-consumer-credential-policy
```

This prints no credential and performs no filesystem or gateway read. It defines the future secret path, group-readable mode, gateway-only scope, denied operations, and overlap-first rotation/revocation order. Provisioning or changing that credential still requires a separately approved transaction with a gateway canary and rollback evidence.

Inspect the matching bounded traffic semantics with:

```bash
cloudx-remote phi-consumer-traffic-policy
```

The output is static and secret-free. The initial values are conservative interoperability ceilings rather than claims about live provider capacity. Enforcement belongs to the Phi provider adapter or an explicitly approved gateway boundary; Cloudx does not persist the queue, accept work items, or infer per-endpoint priority.

Classify current capacity against a consumer protocol range without publishing or changing state:

```bash
cloudx-remote capacity --consumer-protocol-min 1 --consumer-protocol-max 1 --json
```

The command performs the same bounded gateway probe and aggregate account-state read used by formal health, then emits `cloudx.capacity.v1`. Protocol/schema mismatch takes precedence, followed by live probe failure, stale observation, unknown or incomplete observation, and finally healthy versus exhausted aggregate capacity. A valid classification always exits successfully; invalid CLI protocol ranges are rejected.

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

Inspect the committed Phi/Cloudx current-and-N-1 release-ordering evidence without contacting either runtime:

```bash
python3 scripts/check_phi_cloudx_release_ordering.py --json
python3 scripts/check_phi_cloudx_release_ordering.py --require-compatible
```

The first command validates the strict evidence shape and evaluates all four release pairs, both upgrade orders, and both single-product rollback directions. Exit `0` means the recorded audit is internally valid, even when its truthful state is `blocked`. `--require-compatible` exits `2` until every required order is compatible. The current evidence identifies a direct formal-health path for Phi current and an explicit pending legacy bridge for Phi N-1; the ordering gate remains blocked until that bridge is published from a signed artifact, installed as its separate fixed-artifact unit, and accepted through rollback rehearsal.

Inspect the bridge source and exact Phi N-1 compatibility separately with:

```bash
python3 scripts/check_phi_cloudx_legacy_health_bridge.py --json
python3 scripts/check_phi_cloudx_legacy_health_bridge.py --phi-root <phi-checkout> --json
python3 scripts/check_phi_cloudx_legacy_health_bridge.py --require-runtime-accepted
```

The default check validates the strict formal-to-legacy mapping, shared schema/example, advertised capability, compatibility profile, and release-packaged service/timer. The checkout-aware form verifies the recorded Phi release/file digest and executes that exact parser against the generated legacy example. `--require-runtime-accepted` remains exit `2` until signed publication, isolated unit installation, and independent rollback rehearsal are all recorded; none of those actions is authorized by the checker.

Rehearse fixed-artifact independence without touching an endpoint:

```bash
python3 scripts/rehearse_legacy_health_bridge_rollback.py --json
python3 scripts/rehearse_legacy_health_bridge_rollback.py --phi-root <phi-checkout> --json
```

The rehearsal builds the current cloud candidate in a temporary root, seeds isolated `0.1.13/0.1.12` selectors, runs the candidate bridge, invokes the real Cloudx rollback implementation in both directions, and requires the persisted legacy bytes to remain identical across all three states. It emits no temporary path and grants no production publication, staging, unit, service, or selector authority.

Inspect the separate bridge unit-file installation transaction without changing the host:

```bash
python3 scripts/install_legacy_health_bridge_units.py \
  --release-version <staged-signed-version>
```

The default `cloudx.legacy-health-bridge-unit-plan.v1` result reads no artifact, systemd state, unit file, or legacy output and keeps every authorization false. Apply requires the exact printed `INSTALL cloudx-legacy-health-bridge UNITS WITHOUT START` confirmation, root, the exact `/opt/cloudx/releases/<version>/cloudx-cloud.pyz`, root-owned fixed installation directories, a loaded/enabled/active legacy timer, and inactive/disabled candidate units.

The transaction extracts the environment, static canary, primary service, and primary timer from that exact artifact, validates their immutable-path and offline boundaries, writes mode-`0644` root-owned files, runs `systemd-analyze verify`, and performs only `systemctl daemon-reload`. It retains prior files in a root-only backup and restores them plus reloads systemd if any write or verification fails. Success explicitly reports that no candidate was started or enabled, the legacy exporter was not stopped or disabled, and no release was activated. Publication, canary execution, primary start, output comparison, Phi N-1 rollback, restoration, and legacy retirement remain separately approved operations.

After the exact signed artifact and inactive unit set are installed, inspect the isolated runtime canary plan:

```bash
python3 scripts/run_legacy_health_bridge_canary.py \
  --release-version <staged-signed-version>
```

The default `cloudx.legacy-health-bridge-canary-plan.v1` result reads no artifact, unit, systemd state, health file, or credential and keeps every authorization false. Apply requires the exact printed `RUN cloudx-legacy-health-bridge-canary WITHOUT LEGACY CUTOVER` confirmation, root, exact signed env/canary bytes, an active enabled old timer, inactive/disabled primary units, a static inactive canary, and no stale canary output.

The signed canary unit uses the same immutable artifact and hardening boundary as the primary bridge but writes only `/run/cloudx-legacy-health-bridge-canary/v1.json`; `/var/lib/cloudx/health` is inaccessible to it. The runner starts only the static canary, requires systemd success plus the strict bounded legacy contract, records a public output digest, deletes the temporary file/directory, and rechecks all old/primary unit boundaries. Failure stops only the canary and removes temporary state. This does not start or enable the primary bridge and does not count as final production cutover or rollback acceptance.

Inspect the final overlap-first cutover/rollback/restoration transaction separately:

```bash
python3 scripts/rehearse_legacy_health_bridge_cutover.py \
  --release-version <staged-signed-version>
```

The default `cloudx.legacy-health-bridge-cutover-plan.v1` result reads no artifact, unit, process, selector, or health file and keeps every authorization false. Real apply requires the exact printed `CUT OVER AND REHEARSE cloudx-legacy-health-bridge WITH ROLLBACK` confirmation, root, exact signed installed bytes, the old active/enabled timer, inactive primary units, active unchanged gateway/importer processes, exact current/previous selectors, and a distinguishable old-exporter document.

The confirmed transaction runs five phases: isolated canary, candidate overlap, candidate cutover, legacy rollback, and candidate restoration. It enables and validates each target timer/writer before disabling the current timer, retains root-only copies of the pre-cutover public document and continuity manifest, requires the conservative bridge and old exporter to have distinct producer/process evidence, and finishes with the signed primary enabled plus the old service retained. Any failure re-enables and validates the old path before disabling the primary; it never moves a selector, restarts Phi, or touches the gateway/importer. This command performs a real production publisher cutover and is not authorized by repository verification or by the read-only plan.

Tunnel broker status includes `lastReconnectMilliseconds` after an SSH child exit. M2 evidence should record this field together with the stable `publicPort` and incremented `generation`; HTTP probe failures must leave all three unchanged.

Installing the dedicated gateway key is an explicit maintenance action because it restarts the external `cliproxy.service`. A read-only invocation prints the required confirmation:

```bash
python3 scripts/install_scoped_gateway_key.py \
  --release-version <staged-version> \
  --build-commit <signed-release-commit> \
  --gateway-version <observed-version>
```

The read-only plan derives the cloud artifact path from the exact staged version. The `--apply` path first requires that artifact's self-check to report the same version, then requires the exact printed confirmation. It preserves the existing YAML text, writes a mode-0600 backup, installs the restricted credential and version-matched shadow environment atomically, restarts only the declared gateway unit, verifies a real model-list request and both config/auth inotify watches, and restores all files plus the old service configuration if any check fails.

Prepare the distinct Phi consumer key transaction separately:

```bash
python3 scripts/install_phi_consumer_gateway_key.py \
  --release-version <staged-signed-version>
```

The default result is `cloudx.phi-consumer-key-plan.v1`, reads no credential or gateway file, and keeps every authorization false. Apply requires the exact printed `RESTART cliproxy.service FOR PHI CLOUDX CONSUMER KEY` confirmation, root, the exact staged artifact path, a pre-existing `phi-cloudx-consumer` group, a root-owned group-mode-`0750` credential directory, and the existing mode-private Cloudx client credential.

The transaction appends a distinct key, atomically writes only `/etc/cloudx/consumers/phi-cloud/credential` as root/group mode `0640`, restarts only `cliproxy.service`, requires HTTP 200 plus at least two restored inotify watches, and verifies the original Cloudx client credential is byte-identical. Rotation retains the old key until a later separately approved revocation. Any failure restores the gateway config and prior Phi credential, restarts the old gateway configuration, and removes the failed backup. It never creates the Phi group, restarts a Phi service, exposes a key, or closes the privilege gate automatically.

## Import A Local File Over SSH

Use the local Cloudx command when the source path exists on the local machine:

```bash
cloud import ~/Downloads/credentials.json --dry-run
cloud import ~/Downloads/credentials.json
cloud import ~/Downloads/credentials.json --json
```

`cloud import` reads the local file or supported directory, applies the 16 MiB limit, and sends the bytes to `cloudx-remote import` over SSH stdin. The remote importer validates and normalizes the content under its configured auth directory with locking and atomic replacement.

An interactive success is summarized as `Status`, `Destination`, `Imported`, `Skipped`, and `Verification`. Cloud verification explicitly says that live account validity is checked separately; a successful write is not a quota or login canary. A rejection or transport failure reports a safe `Reason` on stderr and returns nonzero. Redirect stdout to retain the raw `cloudx.import.v1` response, or pass `--json` to force it in a terminal.

Do not use `ssh cloud import ~/Downloads/credentials.json` for a local path. OpenSSH runs everything after the host on the remote machine, so that path would be resolved on the cloud host and no local file bytes would be transferred. The low-level equivalent for a single file is `ssh cloud cloudx-remote import < ~/Downloads/credentials.json`; `cloud import` is the supported interface and also handles directories safely.

## HTTP Importer Stop Gate

Before requesting the separate legacy HTTP importer stop transaction, capture root-readable evidence without including key contents, account identities, credential paths, request bodies, or raw failure inputs. Normalize only the declared aggregate facts into `cloudx.http-importer-stop-gate-evidence.v1`, then evaluate them through the exact signed cloud artifact:

```bash
cloudx-remote http-importer-stop-gate < sanitized-stop-gate-evidence.json
```

The evaluator checks the active/enabled service baseline, stable identity, port `8780`, established connections, readable and attributed traffic, later requests, transaction locks, raw failure inputs, formal import readiness, SSH adapter boundary and signed-artifact verification, legacy health readers, systemd requirements, and all required rollback snapshots. It does not impose a calendar delay; the evidence must instead prove the focused traffic and dependency gates directly.

The command reads at most 64 KiB and writes nothing. Unknown or duplicate fields are rejected so credentials cannot be smuggled into a nominal evidence record. A `preconditions-satisfied` result is bound to the exact evidence digest but explicitly reports `automaticAction=false` and `authorization.serviceStop=false`. Stopping or disabling `codex-import.service` still requires a separately approved transaction and the full rollback/canary sequence in the roadmap.

The sanitized `2026-07-17` production snapshot in `docs/archive/` is the current reference decision. It validates the existing root-only runtime, unit, token-metadata, failure-receipt, and restore-plan snapshot; refreshes attributed traffic and zero-connection/lock/caller evidence; and evaluates to `preconditions-satisfied`. This is readiness evidence only. It does not authorize an operator, Agent, timer, installer, or release command to stop the service.

Inspect the separately controlled stop transaction without reading evidence or contacting the host:

```bash
python3 scripts/stop_http_importer.py \
  --release-version <staged-signed-version>
```

The default `cloudx.http-importer-stop-plan.v1` result keeps all eleven authorization fields false. Real apply requires the exact printed `STOP AND DISABLE codex-import.service WITH AUTOMATIC RESTORE` confirmation, the exact evidence digest, evidence captured no more than five minutes earlier, the declared root-only rollback snapshot, and the exact staged cloud artifact. Both local source and that artifact must produce the identical blocker-free stop-gate decision before any service command.

The transaction verifies every rollback-manifest entry, records the active importer and gateway/selectors, disables/stops only `codex-import.service`, and requires the service inactive/disabled with port `8780` closed and no established connection. It then runs an actual SSH `cloudx-remote import --dry-run` with generated fixture data, live formal health, the existing Phi formal-health consumer state, and the authenticated gateway model probe. Any failure—including a partially failed disable—re-enables/starts the importer and requires its listener to return. Success retains the runtime, unit/drop-ins, token metadata, failure receipts, rollback snapshot, and legacy exporter. The archived evidence is intentionally too old for apply; an operator must refresh and re-sign the decision immediately before a separately approved stop window.

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
