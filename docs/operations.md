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

Recording this receipt created a later documentation commit. Verification-only run `29579445629` then succeeded on exact tag target `9ffa3208f39053c2b3af1136a530ce98eac7ad41` while leaving every release ref unchanged. The later separate publication confirmation created `v0.1.15`; neither canary alone authorized that tag.

## Published Release 0.1.15

The immutable annotated tag `v0.1.15` identifies source `9ffa3208f39053c2b3af1136a530ce98eac7ad41`. Tag workflow `29579921061` completed repository verification, exact tag verification, key loading, signed build, release evidence verification, signed-ref publication, and GitHub Release publication successfully.

The immutable artifact ref is `332cb865a97d654efca4b4321b90cdc140e57e64`; stable is `78fe78303f9d57c592b103e11c0fdca1c373b37c`. The release manifest SHA-256 is `3d1f9747cefab855725d105f584e938a27bc93baf488598b746418978547595a`. Local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `9d9d400ce16630eae7e9dddcf17e837ef05d3315a709ff4bbc12abcf10308e97`, `7e838757727e90b11029d85966525a621f629e5f400fa113abc6168790878b71`, and `5f523fec6c1d53b4b3ee8c1e2a252daf552888eb0e3af39a97a13cd43534b89a`.

Fresh remote clones verified the manifest and stable signatures with the replacement root, rejected the same release with the previous root, matched all seven GitHub Release assets to the artifact ref, and repeated local/cloud `staged -> already-staged` transactions in isolated roots with no `current` or `previous` selector. Publication did not stage or activate a real endpoint and did not restart any service.

Installed `0.1.13`/`0.1.12` and lagging `0.1.8/0.1.7` artifacts embed the previous trust root, so they cannot be assumed to accept the newly signed stable index. Use the separately confirmed repository-root stage-only recovery or an exact candidate-verified offline bundle transaction for `0.1.15`; do not bypass signature checks or move a selector as part of publication.

## Published Release 0.1.16

The immutable annotated tag `v0.1.16` identifies source `ec77369a990418f2a990874d1d7bd4b9d2c7fe04`. Main CI run `29637937166` passed the complete Ubuntu/macOS and Python 3.9/3.12 matrix after CI checkout was corrected to fetch annotated release history. Tag workflow `29640659405` then completed repository verification, exact tag verification, key loading, signed build, release evidence verification, signed-ref publication, and GitHub Release publication successfully.

The immutable artifact ref is `9513ff87b3b2e45d2b3609f0746248a7422d34b2`; stable is `bba9f619fc2d3e57cbd1b2808fe97ac58e805aef`. The release manifest SHA-256 is `9ac48648b9e00bc0fcdbc33517cb3f97bb545211829626e6423281549f7b4fee`. Local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `b8fb5d72192d140b212fcc3aacef05066972bdfb720a83b507b069b47920c323`, `b6257a5bbe128f159019ea0592be6eb3f3f5e38d5e109bdb293af06230ed8cfe`, and `7679bfd25a308d3390cd2476492ecadb97cdc4dab19bc85a97b534c711e4919f`.

Fresh remote clones and seven downloaded release assets verified the current signer and exact source, rejected the release with the previous signer, matched every non-bundle asset byte-for-byte, passed both component self-checks, accepted the stable index, and repeated local/cloud `staged -> already-staged` transactions in selector-free isolated roots. Publication itself did not stage or activate a real endpoint and did not restart any service.

The separately confirmed cloud install is now complete. Because the cloud host could not fetch GitHub directly, the canonical installer consumed a complete Git bundle whose local and remote SHA-256 was `b77928f9d7e7e88cfa7871b660c79c077e4da16b2bcc3879c8669395c75f4540` and whose sole release ref resolved to immutable artifact commit `9513ff87b3b2e45d2b3609f0746248a7422d34b2`. Cloud `current=0.1.16`, `previous=0.1.13`; self-check, release status, and handshake passed. The next natural CPA-health timer invocation exited `0` and truthfully reported aggregate `probe_error` with all 45 auth files retained and the archive empty. CPA PID `977036` and restart count `0` were preserved. Local install still requires the separate exact `INSTALL CLOUDX LOCAL 0.1.16` confirmation.

## Published Release 0.1.17

The immutable annotated tag `v0.1.17` identifies source `0bf7461c9c421b55031c8d17c0951bc8321a0ba9`. Main CI run `29646011920` passed the complete Ubuntu/macOS and Python 3.9/3.12 matrix, and non-publishing signed-build canary `29646089414` passed while leaving release refs unchanged. Tag workflow `29646167279` then completed repository verification, exact tag verification, key loading, signed build, release evidence verification, signed-ref publication, and GitHub Release publication successfully.

The immutable artifact ref is `d720979dc46ff5a7b4cb1ba121aca92849e0e09a`; stable is `82a35ff57ae97c4fd655d14ce2bf28c4304cd31b`. The release manifest SHA-256 is `9ea06875527f31cf1ca2577b33afe480a331f25f3e0718935f1d28771ef69aed`. Local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `b375e12ed9bfede2005bc18efb777135ebf373001bc4bbf311184ad444a52caa`, `bc94accbfcdbff3cf8d33a370e748cf6a25b52546cb15a0b313c5b5274a98480`, and `d3c6e726b651e345935821a3605d5fb0eddf7845a1a9deb55c7737009a37a9e9`.

Fresh remote clones and all seven downloaded Release assets verified the current signer and exact source, rejected the release with the previous signer, matched every artifact and offline-bundle member byte-for-byte, passed both component self-checks, accepted stable, and repeated local/cloud `staged -> already-staged` transactions in selector-free isolated roots. Publication itself did not install or activate a real endpoint, restart CPA, or modify a credential/archive. Cloud remained `0.1.16/0.1.13` with CPA PID `977036` and restart count `0`; local remained `0.1.13/0.1.12` with CPA PID `38189`. Real installation requires separate `INSTALL CLOUDX CLOUD 0.1.17` and `INSTALL CLOUDX LOCAL 0.1.17` confirmations in that order.

The separately confirmed cloud install is complete. Cloud now selects `current=0.1.17`, `previous=0.1.16`; current artifact SHA-256 is `bc94accbfcdbff3cf8d33a370e748cf6a25b52546cb15a0b313c5b5274a98480` and current manifest SHA-256 is `9ea06875527f31cf1ca2577b33afe480a331f25f3e0718935f1d28771ef69aed`. Self-check, release status, and handshake passed. CPA PID `977036`, restart count `0`, importer PID `133756`, zero active auth files, 45 archive-manifest entries, and every inspected unit byte were preserved. A natural health invocation exited `0` with `probe_gate=no_accounts` and `probe_concurrency=0`. Because endpoint installation intentionally does not replace units, the existing service command is still the pre-watcher `cpa-health` command; the separately confirmed watcher transaction must install the signed trigger-aware health service/timer before usable credentials are imported. Local installation remains separately confirmed.

The separately confirmed local install is also complete. Local now selects `current=0.1.17`, `previous=0.1.13`; current artifact and manifest SHA-256 values are `b375e12ed9bfede2005bc18efb777135ebf373001bc4bbf311184ad444a52caa` and `9ea06875527f31cf1ca2577b33afe480a331f25f3e0718935f1d28771ef69aed`. Self-check, fresh-shell `codexx api`, official `/opt/homebrew/bin/codex` resolution, and a real post-install Codex request through the existing API profile passed. CPA PID/listener `38189` and all six captured pre-existing Codex PIDs survived. `codexx` and `cloud` now resolve to the signed `0.1.17` artifact, while the CPA launcher still selects the baseline `/Users/hirohi/.local/bin/cli-proxy-api` and contains neither failure nor sweep producer environment. Local installation therefore activated no CPA policy and restarted no service.

## Published Release 0.1.18

The immutable annotated tag `v0.1.18` identifies source `f94c926daa929d8d9801722013408eb9ebb7e90a`; tag object `0798a6c4bc3d4004fec56000306601a18fd1b857` peels to that exact commit. Main CI run `29653018964` passed the complete matrix, and non-publishing signed-build canary `29653206898` passed on the same source while both publication steps were skipped and release refs remained unchanged. Tag workflow `29653241622` then completed repository verification, exact tag verification, key loading, signed build, release evidence verification, signed-ref publication, and GitHub Release publication successfully.

The immutable artifact ref is `5e345ed8cbf0373ac9e6214e45358187a524ea5d`; stable is `d3275fd150bceaa50c216c13a99969b58409992d`. The release manifest SHA-256 is `b5ab79e932f215730452dd6aa8afabe629a23118a489ec5c03054d5e0856ee23`. Local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `56881ca376857652cefaecc5159f8818edf765702f3d574c3b55f37972edde1f`, `1cba50617522634c09584d7cc9d1a800df056256c0201fd325cb54afa8ca1426`, and `a4ae5d73b1ec6a25f64e9a4f86467a3f7be07455ef6d30f510a9286a87bc6738`.

Fresh remote clones and all seven downloaded Release assets verified the current signer and exact source, rejected the release with the previous signer, matched every artifact and offline-bundle member byte-for-byte, passed both component self-checks, accepted stable, and repeated local/cloud `staged -> already-staged` transactions in selector-free isolated roots. Publication itself did not install or activate a real endpoint, restart CPA, or modify a credential/archive. Local remained Cloudx `0.1.17/0.1.13` with healthy CPA PID `61859`; cloud remained Cloudx `0.1.17/0.1.16` with CPA PID `1613475`, restart count `0`, and zero active auth files. Real installation requires separate `INSTALL CLOUDX CLOUD 0.1.18` and `INSTALL CLOUDX LOCAL 0.1.18` confirmations in that order.

The cloud-install read-only preflight is accepted. `/opt/cloudx/releases/0.1.18` remains absent; selectors, CPA/importer PIDs and restart counts, 45-entry archive manifest, zero active/failure/sweep inputs, required private files, watcher absence, and the local CPA communication path are preserved. Direct cloud-host GitHub HTTPS timed out, but an automatically removed clone using explicit `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7890` matched the immutable ref/source/signature/digests and passed the cloud self-check. The future exact-confirmation transaction must inject that proxy environment into the immutable installer or use the complete verified offline Git bundle; it must not change mihomo or global Git/system proxy configuration.

The local-install read-only preflight is also accepted but found a workstation-specific preservation issue: native auth still matches `soul0`, while native config now carries a workspace-trust entry and one TUI notice difference. The immutable signed `0.1.18` canonical installer would reseed and overwrite that complete config after selector activation. A synthetic signed rehearsal instead used active `0.1.17` only for exact staging and staged `0.1.18` for activation with no seed account; native/shell/user/fake-CPA bytes stayed unchanged across activation, signed rollback to `0.1.17`, and reactivation to `0.1.18`. The future real local transaction must use this signed preserving path, prepare rollback before movement, retain every live CPA/Codex identity, and pass a real official-Codex-through-CPA canary. Source `0.1.19` separately prevents future installers from reseeding any complete native profile.

The separately approved cloud `0.1.18` install is complete. A first operator-wrapper source-identity check failed before installer invocation because it omitted the temporary clone working directory; inspection proved no release directory or selector changed. The corrected proxy-aware retry returned stage `staged`, activation `active`, and no service restart. Cloud now selects `0.1.18/0.1.17`; exact artifact/source/manifest, self-check, release status, and handshake passed. CPA PID `1613475`, importer PID `133756`, both restart counts `0`, zero active auth, 45 archive entries, zero failure/sweep inputs, all inspected unit/runtime bytes, and watcher absence were preserved. Local remained `0.1.17/0.1.13` with healthy CPA PID `61859`.

The separately approved local `0.1.18` install is also complete through the signed no-reseed path. A private recovery job was prepared and validated before staging. The first activation reached post-acceptance, where a missing operator-script import triggered fail-closed signed rollback to `0.1.17` plus a real recovery communication canary; CPA never restarted. The corrected retry returned `already-staged`, activated `0.1.18/0.1.17`, and preserved native auth/config, `.zshrc`, shell source, CPA binary/plist, the 56-file local auth tree, CPA PID `61859`, and all ten captured Codex PIDs. Fresh-shell API selection, official Codex resolution, self-check, and a real post-activation Codex-through-CPA canary passed. Recovery job `20260718T180043Z-a677fe97` remains private and executable.

The separately approved cloud failure/sweep watcher transaction is active. After the source gate was aligned to active signed `0.1.18` and CI passed, the rollback-protected installer wrote the signed trigger-aware health service/timer plus both path-service pairs, enabled only the two path units, and preserved the health timer state. Backup `1784398277383594551` retains every prior unit byte. CPA PID `1613475`, importer PID `133756`, restart counts `0`, selectors, CPA unit/drop-in, zero active auth, 45 archive entries, empty trigger inputs, and local CPA PID `61859` were unchanged. A real idle health invocation exited `0` with `probe_gate=not_triggered`, `probe_concurrency=0`, absent trigger, and zero archive.

The separately approved first-active-capacity transaction is accepted. Ordinary cloud import remained shadow-only and was not treated as capacity. One direct-Codex-verified `soul0` credential then entered the active pool through signed dry-run/apply and rollback-bounded stdin handling. Two source-hardening attempts privately restored the empty pool after an expected available observation and one hot-load HTTP `400`; final transaction `20260718T183809Z-6171f256` passed real model traffic with `codex-auto-review`, HTTP `200`, exact response text, public policy `2`, identity-free `available` observation, active/available count one, archive count 45, CPA PID `1613475`, restart count `0`, and no service restart or raw transaction copy. Signed health plus formal publishers now report one ready/available account and `cloudx.capacity.v1 state=healthy_capacity`, gateway HTTP `200`.

## Published Release 0.1.19

The immutable annotated tag `v0.1.19` identifies source `51c5294ed6dd5b504ef4384e9860c70e2593ae78`; tag object `205f25b2f3ad060b66082716a69ef2e4006c18ea` peels to that exact commit. Main CI run `29669596380`, non-publishing signing canary `29669662202`, and tag workflow `29677581155` all passed. The immutable artifact ref is `d4bddf35a1305186ffe568438ceaca6afb5cce61`; stable is `e5f7fafb7539b09f5b3e0f5424999bccd5a06dac`.

Manifest, local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `d6de8428c97ac30371626a6b4f9b41b47da134a5dd3e3900c5d2c90eb3ec996f`, `2d54f0e8d5b1e38bd4d5e231620c31691b8f5d926c2222ab5be59fc0832dfb03`, `33b575ec67844f36c2343cbef255cf740a93d288d910cf0405fdab1bb299e430`, and `cce684675b289e6fac34a1f56e82bb9be5624b7445a671e8b111d1b6689cf3d6`. Fresh clones and all seven Release assets verified current-root acceptance, pre-rotation-root rejection, exact source/manifest/stable binding, byte-identical offline contents, both self-checks, and local/cloud `staged -> already-staged` behavior without selectors.

Publication left both real endpoints on `0.1.18/0.1.17`, local CPA PID `61859`, cloud CPA PID `1613475` with restart count `0`, importer PID `133756`, one active cloud credential, 45 prior archive entries, and empty failure/trigger inputs. Install cloud first with `INSTALL CLOUDX CLOUD 0.1.19`, then install local with `INSTALL CLOUDX LOCAL 0.1.19`; publication itself authorizes neither endpoint activation nor any service restart.

The separately confirmed cloud `0.1.19` install is complete. Private transaction `20260719T072339Z-2a6bd2fa` prepared a signed `0.1.18` selector recovery before mutation, cloned immutable `v0.1.19` through the existing mihomo proxy, and invoked the tagged canonical installer. Cloud now selects `0.1.19/0.1.18`; exact source/artifact/manifest, self-check, release status, and handshake passed. CPA PID `1613475`, importer PID `133756`, both restart counts `0`, one active credential, 45 archive entries, empty failure/trigger inputs, watcher/unit bytes, and private prerequisite bytes were preserved. Local remained `0.1.18/0.1.17` with CPA PID `61859`; no service restarted. Local `0.1.19` installation remains the next separate gate.

The separately confirmed local `0.1.19` install is also complete. Recovery job `20260719T073812Z-336c544b` captured native/shell/CPA/auth/process state and a real baseline canary before mutation, then retained an executable exact-selector/file restoration path with a real recovery canary. The immutable tagged installer activated `0.1.19/0.1.18` with no native seed. Artifact/source/manifest, self-check, fresh-shell API mode, official Codex resolution, and real post-install communication passed; native auth/config, CPA binary/config/LaunchAgent, 34 CPA JSON files, CPA PID `61859`, and all eight captured Codex PIDs remained unchanged. Cloud stayed `0.1.19/0.1.18`; no service restarted.

## Published Release 0.1.20

The immutable annotated tag `v0.1.20` identifies source `eefd8a4aa70d554ac32babe3ff7aa1ae9996e875`; tag object `bd0cfee4bf9073c429a5f210dec2f36723495767` peels to that exact commit. Main CI `29679388154`, non-publishing signing canary `29679446529`, and tag workflow `29679495793` passed. The immutable artifact ref is `d6bce9346d86b2b133057df01ced068ef3eef9b2`; stable is `11edbaf440d0f38958743aea279ddc36ea9320e5`; GitHub Release `356290726` is final and contains seven assets.

Manifest, local artifact, cloud artifact, and offline bundle SHA-256 values are respectively `9a9984cf18de1797900ea3710c463abcca20a1958a4809627065f73c3d7e23c7`, `bce19e8b27f35bcb95637a5a3afa82c01feb51765763d1b3f34f14dad0e315fd`, `801a5977362cac6653f18c83efc9bd414126feebc0297cebc35e8c4bd514216e`, and `a37dfd8e56e5487fbeb50efc1faad682e14a70ddac42bab9efb6050803915e79`. Fresh immutable clones and downloads accepted the current signer, rejected the pre-rotation signer, matched all assets and offline members byte-for-byte, passed local/cloud self-checks and stable selection, and repeated isolated local/cloud `staged -> already-staged` behavior without `current` or `previous` selectors.

Publication changed no production selector or release directory. Local and cloud remain signed `0.1.19/0.1.18`; local CPA remains PID `61859`, cloud CPA remains PID `1613475` with restart count `0`, importer remains PID `133756` with restart count `0`, the cloud active pool retains one credential, the archive retains 45 entries, and failure/trigger inputs remain empty. Install cloud then local through separate exact gates before staging `.policy.4`; CPA activation remains a later independent restart boundary.

The separately confirmed cloud `0.1.20` install is accepted. Root-only transaction `20260719T082934Z-8f5ce554` stored a complete selector recovery script and manual first, verified it against `0.1.19/0.1.18`, then cloned immutable `v0.1.20` and its artifact branch from one locally audited offline Git bundle. The tagged canonical installer returned stage `staged`, activation `active`, and `serviceRestarted=false`. Cloud now selects `0.1.20/0.1.19`; exact artifact/manifest, self-check, release status, handshake, nine unit/drop-in digests, two private prerequisite digests, watcher states, one active credential, 45 archive entries, empty failure input, and absent trigger all passed. CPA PID `1613475`, importer PID `133756`, and both restart counts `0` were preserved. A real local official-Codex-through-CPA canary passed afterward. Local remains `0.1.19/0.1.18`; its install is the next separate gate.

The separately confirmed local `0.1.20` install is also accepted. Private job `20260719T083822Z-8a0b219c` stored exact native/shell snapshots, immutable source/artifact bundle, aggregate CPA/auth/process state, an executable recovery tool and manual, then passed recovery `--check` and a real baseline official-Codex canary before selector movement. The tagged installer returned local stage `staged`, activation `active`, and `nativeProfileChanged=false`. Local now selects `0.1.20/0.1.19`; exact artifact/manifest, self-check, fresh-shell `codexx api`, official Codex resolution, and real acceptance traffic passed. Native auth/config, `.zshrc`, signed shell source, CPA binary/config/LaunchAgent, the 37-file auth JSON aggregate, CPA PID `61859`, and all six captured Codex PIDs remained unchanged. Cloud stayed `0.1.20/0.1.19` with CPA/importer identities, one active credential, 45 archive entries, and empty failure/trigger inputs unchanged. No service restarted.

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

Source `0.1.16` also recognizes the exact CPA export wrapper with outer `platform=openai`, outer `type=oauth`, and a nested `credentials` object. Another OAuth platform remains rejected. Cloud import acceptance proves only a locked, validated, atomic credential write; always follow it with idempotent dry-run and real model traffic. A model-list response or `written` count is not evidence that the workspace is active, has quota, or can refresh.

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
sudo /usr/bin/python3 /opt/cloudx/current/cloudx-cloud.pyz \
  cpa-health --check --proxy-url http://127.0.0.1:7890
```

The explicit proxy argument makes an interactive check use the same declared external mihomo path as the installed oneshot unit. The probe first checks that path without account authority. A transport/provider outage skips all account archive decisions. When the path is reachable, account checks use a bounded pool of at most two; explicit deactivation/deletion, non-refreshable unauthorized, and conclusive refresh revocation/invalid-grant results are immediately eligible, while quota/429, refreshable 401, network/TLS/DNS/timeout/5xx, and unknown results are retained. Network requests run outside the archive lock, and output remains aggregate-only.

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

## Prepare The External CPA Safety Policy

This is a separate external-service maintenance path. It is not part of ordinary Cloudx activation and does not change the official `codex` executable. The repository pins the currently deployed local CPA commit `15ac7fb...` and cloud CPA commit `5b7f2361...`; it does not upgrade either endpoint.

Build planning is read-only. `--build` requires a clean exact checkout, applies the digest-bound patch in a temporary copy, runs focused Go regressions, and writes only a side-by-side candidate outside the repository:

```bash
python3 scripts/build_cpa_policy_candidate.py \
  --target local \
  --source /absolute/path/to/clean-v7.0.1 \
  --output /absolute/path/to/local-candidate

python3 scripts/build_cpa_policy_candidate.py \
  --target cloud \
  --source /absolute/path/to/clean-v7.2.71 \
  --output /absolute/path/to/cloud-candidate
```

Inspect the two independent deployment plans:

```bash
python3 scripts/install_cpa_policy_candidate.py --target local
python3 scripts/install_cpa_policy_candidate.py --target cloud
```

Stage and activation have different exact confirmations. Stage verifies the pinned candidate bytes and copies them under the target's dedicated `cliproxy-cloudx/releases` tree; it does not edit a launcher or unit and does not restart CPA. Activation remains unapproved until the operator repeats the exact printed `ACTIVATE ... CPA POLICY ...` string. It retains the original binary, snapshots the prior launcher or drop-ins, configures private auth/failure directories, restarts only the selected external CPA, and requires `/healthz` plus `X-CPA-Max-Concurrent-API-Requests: 2`. Any failed canary restores the prior service selection automatically.

The separately confirmed cloud `.policy.3` stage and later activation are complete. `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.3/cli-proxy-api` is root-owned mode `0755`, size `45322402`, SHA-256 `453df72d15235ea51e5fdf66d27692bb5249bd262800fd628af3638246021a2b`, and reports the pinned version/commit/build date. Its mode-`0644` manifest matches those fields. After one readiness-race attempt automatically restored the baseline, the operator repeated the exact confirmation using the bounded-retry installer. Cloud CPA now runs the exact candidate as PID `1613475`; health returns `200`, the invalid-auth inference canary returns public policy `2`, the original binary and root-only rollback snapshot remain available, and Cloudx `0.1.17/0.1.16`, zero active auth files, 45 quarantined credentials, plus all local CPA/Codex identities were preserved. Failure/sweep watchers remain inactive and separately gated.

The separately confirmed local `.policy.3` stage is also complete. `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.3/cli-proxy-api` is owner mode `0700`, size `41484930`, SHA-256 `1cff3152e34666d2753add54ce7f5f96dbd643e607c1f136a9052cd28eba9ecd`, and reports the pinned local version/commit/build date; its mode-`0600` manifest matches. The first deferred activation attempt failed while many CPA-backed requests were active: CPA graceful shutdown reached its HTTP deadline, the old rollback path raced launchd unloading, and the baseline remained offline until the operator manually reopened it. The launcher and baseline bytes are restored and healthy, but local `.policy.3` remains inactive and will not be retried; its recovery hardening is retained for the `.policy.4` gate below.

Production acceptance later exposed a separate aggregate-producer gap without losing service or credentials. Transaction `20260719T074516Z-8d0f6abf` accepted three real quota retentions, provisional refreshable-401 retention, one non-refreshable-401 archive and digest-exact restore, then observed exact upstream `v7.2.71` return HTTP `429 model_cooldown` for the fully cooled pool instead of `auth_unavailable`. Active `.policy.3` therefore emitted no trigger, the transaction rejected, and its prebuilt recovery restored one useful active credential, the 45-entry archive, empty watcher inputs, HTTP `200` policy-`2` traffic, CPA PID `1613475`, restart count `0`, and local CPA/Codex continuity. Source `.policy.4` treats final `auth_unavailable` and all-candidate `model_cooldown` as the same identity-free pool incident while leaving archive authority unchanged. Independent exact-commit builds twice produced local SHA-256 `08608c2ebba606115a5c4bf6588896af3d2bdeb6e71ed308e17a84148766cd29`, size `41484930`, and cloud SHA-256 `3e3ed137ff90132203f2b0e969245b6580b3ff2b780e2f3a47b821642fd6fdc4`, size `45322402`. Signed Cloudx `0.1.20` publication and endpoint installation preceded the separate staging evidence below.

Both `.policy.4` candidates are now staged after distinct exact confirmations and remain inactive. Cloud path `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.4/cli-proxy-api` is root-owned mode `0755`, size `45322402`, SHA-256 `3e3ed137ff90132203f2b0e969245b6580b3ff2b780e2f3a47b821642fd6fdc4`, and reports `7.2.71-cloudx-policy.4` / `5b7f2361+cloudx-cpa-policy4`. Local path `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.4/cli-proxy-api` is owner mode `0700`, size `41484930`, SHA-256 `08608c2ebba606115a5c4bf6588896af3d2bdeb6e71ed308e17a84148766cd29`, and reports the pinned local identity. Stage evidence retained cloud CPA PID `1613475`, importer PID `133756`, local CPA PID `61859`, all six captured Codex PIDs, both Cloudx `0.1.20/0.1.19` selectors, one cloud credential, 45 archive entries, 37 local auth JSON files, and all launcher/unit selections unchanged. Neither stage edited a service definition or restarted a process.

The separately confirmed cloud `.policy.4` activation is accepted. Root-only job `20260719T085449Z-fda9a073` captured both active `.policy.3` drop-ins and a complete exact-confirmation recovery tool before mutation; its `--check` verified snapshot/tool digests, active `.policy.3`, health, and policy `2` without restarting. The canonical installer then retained automatic rollback backup `1784451450447783787-cloud`, restarted only `cliproxy.service`, and selected exact `.policy.4` as PID `1693505` with restart count `0`. Independent acceptance matched candidate identity and service selection, passed invalid-client policy `2`, real authenticated HTTP `200` model traffic, and a local official-Codex-through-CPA canary. Importer PID `133756`, Cloudx `0.1.20/0.1.19`, one active credential, 45 archive entries, watcher states, and empty failure/trigger inputs remained unchanged. The manual recovery job remains executable and restores `.policy.3`; local `.policy.4` remains staged/inactive behind the zero-connection gate.

Do not invoke synchronous local activation from a Codex turn that is itself using the local CPA. The next local `.policy.4` activation requires signed Cloudx `0.1.20` so the independently executable recovery tool, safe stage receipts, and zero-established-connection gate are present before another restart is authorized. After that release is active locally, inspect the non-authorizing deferred plan:

```bash
python3 scripts/schedule_local_cpa_policy_activation.py
```

Its exact-confirmation apply prepares the installer, pinned contract, original launcher snapshot, recovery tool, `RECOVERY.txt`, and digest-bound job manifest before starting the private worker. After the 180-second delay and a real baseline Codex canary, five consecutive audits must report zero established CPA connections; otherwise the job fails before editing the launcher or stopping CPA. Automatic recovery invokes the same job-local command documented for the operator, waits for complete launchd unloading, retries baseline bootstrap, and requires both health and real Codex communication. Worker logs contain only enumerated stages and aggregate states. The detailed procedure and failure-code response are in [Local CPA Activation And Recovery Manual](local-cpa-recovery.md).

Local activation never terminates a `codex`, Codex App, terminal, workspace, or project process. It is now prohibited from stopping the shared CPA while any established connection is observed. Once the explicit quiescence gate passes, a restart still has a short availability window and cannot guarantee an overlapping request; the prepared manual/automatic recovery path exists for that exact boundary. Installing a Cloudx local release remains separate and does not restart CPA at all.

The matching signed Cloudx receipt/sweep consumers and `.policy.4` producer must be active before event-driven maintenance is accepted. Inspect the separate non-authorizing watcher plans only after those prerequisites pass:

```bash
python3 scripts/install_cpa_failure_watcher.py --target local
python3 scripts/install_cpa_failure_watcher.py --target cloud
```

The exact-confirmation local action preserves the existing `codexx api refresh --apply` command and log paths, adds both the private failure directory and exact sweep-trigger file to `WatchPaths`, changes the missed-trigger fallback from fifteen minutes to two minutes, and reloads only that maintenance LaunchAgent. The cloud action extracts six signed templates from active Cloudx `0.1.17`: trigger-aware CPA-health service/timer, a `PrivateNetwork=true` receipt service/path using `cpa-health --runtime-failures-only`, and a separate network-capable sweep service/path using `cpa-health --sweep-if-triggered` with incident concurrency 32. One transaction backs up and atomically installs all six, performs `daemon-reload`, preserves the health timer's prior enabled/active state, and enables only the two path units. The five-minute fallback then performs zero account probes when no fresh trigger exists. Neither watcher action restarts CPA, Codex, Cloudx, or Phi. Phi may read the resulting aggregate health and notify, but cannot inspect receipts or triggers, probe credentials, or move them. Manual local preview and reversible restore are:

```bash
codexx api refresh --dry-run --json
codexx api refresh --apply --json
codexx api restore <archived-file> --confirm <archived-file>
```

An access token that is merely expired but still has a refresh token is retained. A provisional refreshable 401 is also retained until refresh produces a conclusive permanent result. Weekly quota, HTTP 429, transient limits, network failures, timeouts, and 5xx never create an accepted receipt. CPA never moves the auth file; Cloudx performs the digest-bound same-filesystem archive and keeps the private manifest outside release directories.

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
