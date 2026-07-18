# Product Standards

## Supported Product Surface

Cloudx 0.x supports these durable behaviors:

1. Select native, `api`, `cloud`, or a named local Codex account mode with `codexx`.
2. Leave the official `codex` command untouched.
3. Hold a shell-owned broker lease for `codexx cloud`, then run the official Codex with plain `codex`.
4. Import local CPA credentials through the explicit migration adapter with `codexx import`.
5. Import cloud gateway credentials over SSH with `codexx cloud import`.
6. Stage an exact signed endpoint artifact without activation, or install it with the local shell source, through the separately confirmed `./install` workflow.
7. Diagnose retained local or cloud API failure evidence without replacing `codex`, changing the gateway response, or exposing a credential or account identity.
8. Reversibly archive unusable CPA credentials after an infrastructure-gated, account-scoped permanent-auth classification, while retaining exact-confirmation restore paths and never treating allowance exhaustion as credential failure.

`cloud codex` and `cloud import` remain supported compatibility commands during the migration window.

Remote handshake, health, release staging, and rollback exist to make those behaviors operable. They are not a general control plane.

The migration-only HTTP importer stop-gate evaluator accepts a bounded sanitized evidence contract and returns deterministic precondition blockers. It does not collect privileged host state, stop or disable a service, or grant authorization; every result keeps `serviceStop=false` and requires a separate operator-confirmed transaction.

That separate stop transaction also defaults to a non-authorizing plan. Exact-confirmation apply must require fresh digest-bound evidence evaluated identically by source and the exact staged signed cloud artifact, verify the complete root-only rollback manifest, stop/disable only `codex-import.service`, prove port `8780` closed, repeat the actual SSH dry-run import plus formal-health/Phi/gateway-model canaries, and preserve gateway/release-selector continuity. Any failure re-enables the importer. It cannot remove importer runtime, unit files, token metadata, failure receipts, rollback data, the legacy exporter, or any credential.

The legacy local codex-plus retirement transaction also defaults to a non-authorizing plan. Exact-confirmation apply must bind to the exact active signed release containing the native local-CPA adapter, verify the live runtime and launcher against the retained private recovery manifest, require no legacy process and no port `18317` listener, and accept native import plus fresh-shell mode switching before and after the move. It may quarantine only the live legacy runtime, launcher, and recovery entrypoint into retained private state. It must preserve official Codex and Git resolution, Cloudx entrypoints and shell hook, account profiles, the external CPA process/configuration/LaunchAgent, and the original recovery bundle; any failed post-move check restores all live targets. Planning, building, staging, or testing grants no quarantine or deletion authority.

Release workflow key synchronization also defaults to a non-authorizing offline plan. Exact-confirmation apply may update only `CLOUDX_RELEASE_SIGNING_KEY` in the fixed GitHub `release` environment after the external private key matches the committed public root and clean local `HEAD` equals pushed `origin/main`. It must prove `workflow_dispatch` cannot execute tag-only publication, run that dispatch as a signing canary, and require tag, artifact, and stable refs unchanged. Because GitHub never exposes the previous secret value, post-write failure cannot claim automatic rollback; it must retain the updated secret, return nonzero, and explicitly prohibit release tagging until a later canary succeeds.

## Product Invariants

- Single user and personal node first.
- Local execution remains local. `cloud codex` does not SSH into a remote Codex runtime.
- Account selection changes `CODEX_HOME`; it does not modify the official Codex executable.
- Cloud mode binds its tunnel lease to the selecting shell PID. `codexx exit`, another mode selection, or shell death releases that lease.
- The default local Codex profile and named profiles have independent authentication files.
- A single local broker owns the cloud SSH tunnel. Sessions acquire leases; they never monitor, kill, or rebuild the shared SSH process themselves.
- The broker uses a Cloudx-owned port distinct from the legacy bridge and never treats a transient HTTP probe failure as authority to kill an SSH tunnel.
- The broker may passively classify response bytes already crossing the cloud relay, but it stores only the secret-free diagnosis fields and never changes forwarded bytes. Local CPA diagnosis reads only bounded response sections from external gateway logs. A generic no-usable-account response cannot overwrite a recent definitive upstream cause, and insufficient evidence is never guessed to be quota exhaustion or deactivation.
- The existing legacy bridge remains a supported migration fallback until its removal has a separate, accepted roadmap item.
- Import and health code cannot require Phi.
- In the initial Personal Agent Mesh, trusted devices terminate at Phi cloud and only the Phi cloud runtime is a normal Cloudx gateway consumer. Cloudx never stores Phi device, Task, lease, approval, local-path, transfer-content, or Artifact metadata.
- Phi uses a revocable least-privilege Cloudx consumer credential that cannot import accounts, mutate gateway or release state, or represent a Phi device identity.
- Direct endpoint-to-Cloudx access for future local inference requires a separate accepted milestone and credential contract; Mesh membership alone never grants gateway access.
- Local CPA import is a Cloudx-owned compatibility adapter for an external CPA: it may normalize and atomically write bounded credential inputs, but it cannot own or restart the CPA service. Older installed releases may retain `codexx-legacy` only as an explicit rollback path until the native adapter has signed production acceptance.
- A CPA policy candidate may be built only from the exact deployed upstream revision and activated only through a separate operator-confirmed external-service restart. It enforces one global two-request ceiling for proxied business API traffic, may emit private digest-bound failure receipts for conclusive account failures, and may emit an identity-free aggregate `auth_unavailable` sweep trigger; it never moves or deletes an auth file itself.
- Automatic full-pool CPA probing occurs only after a fresh aggregate `auth_unavailable` trigger. The incident sweep first proves the declared HTTPS/proxy path is reachable, deduplicates identical credentials, and uses a separately configured high-concurrency probe pool that is not constrained by the two-request business ceiling. One explicit account-scoped permanent result—such as deactivation, deletion, a non-refreshable unauthorized credential, or a conclusive refresh revocation/invalid-grant failure—is sufficient and is digest-revalidated before a same-filesystem move; a provisional refreshable 401 is not sufficient. A file bundling multiple logical accounts moves only when every context in that file is conclusively permanent. Weekly allowance exhaustion, ordinary HTTP 429, transient rate limiting, network/TLS/DNS failure, timeout, 5xx, or an expired access token with a refresh token are never archive authority. Infrastructure/provider failure retains the trigger for a later retry. Archive is reversible and is not credential deletion.
- A conclusive private runtime receipt triggers a network-free archive consumer immediately. A distinct identity-free aggregate pool trigger invokes the network-capable incident sweep. Local and cloud watchers require their own exact activation after the matching signed consumers and CPA producer are active; watcher activation may reload only the maintenance LaunchAgent or systemd path units, never CPA, Codex, Phi, credentials, or a release selector. Periodic maintenance is only a missed-trigger fallback and performs no unsolicited full-account probe.
- Cloudx owns CPA probing, classification, receipt consumption, archive, restore, and aggregate health. Phi may consume the secret-free health result and notify the operator, but cannot probe credentials, decide archive eligibility, move credentials, or mutate Cloudx state.
- Legacy local package retirement is quarantine-first: no process is terminated, no service is restarted, no account or external CPA state is changed, and neither the private recovery bundle nor the quarantine is deleted by the transaction.
- Release signing keys never enter Git, release directories, artifacts, receipts, command arguments, or logs. Workflow synchronization sends key bytes only over the authenticated GitHub CLI stdin boundary and publishes only the signer fingerprint and secret name.
- Interactive local and cloud imports use one outcome vocabulary that identifies the destination, imported and skipped counts, verification scope, and safe failure reasons. Cloud write acceptance must never be presented as proof of live account usability.
- Local and cloud API diagnosis use one outcome vocabulary that separates account deactivation, exhausted allowance, transient rate limiting, relogin, permission denial, gateway failure, and unknown evidence. A successful model-list probe must never be presented as proof of remaining upstream quota.
- Cloud helper JSON, static text, health publication, receipts, release state, logs, and public errors pass through one fail-closed metadata boundary. Phi Task, session, device, lease, approval, local-path, transfer-content, ContextRequest, LocalAction, and Phi Artifact fields are rejected; the scoped credential policy may only state `device`, `task`, and `session` as literal `false` representation constraints.
- Unsupported or shadow-only behavior must be labeled as such in command output and documentation.

## Explicit Non-Goals

- account pools or automatic account selection on the local client
- task, agent, queue, approval, workspace, or project control planes
- Phi device registration, target selection, execution leases, LocalAction routing, or cross-device approval
- chat clients or multi-user hosted execution
- autonomous code repair, merge, deploy, or service restart
- ownership of Tailscale, mihomo, SSH, systemd, or CLIProxyAPI

## Compatibility

Local and cloud artifacts share a protocol range. A local artifact supports the current remote protocol and the immediately previous one. An absent helper is reported as `legacy_bridge`; it is not treated as permission to mutate the gateway.

During the Phi health-contract migration, the signed cloud artifact may translate formal `cloudx.health.v1` into the exact secret-free `cloudx.health`/`schemaVersion=1` document required by Phi N-1. The bridge must preserve unknown and unobserved state rather than reconstructing unavailable process or failure-receipt facts. Its service selects an exact immutable signed artifact independently of the Cloudx `current` symlink so endpoint rollback does not remove the compatibility path. Packaging the command or templates does not authorize publication, installation, service start, selector change, or retirement of the existing exporter.

The repository unit transaction for that bridge defaults to a read-only plan. Exact-confirmation apply may install only the signed artifact's fixed environment, static canary, primary service, and primary timer files and run `daemon-reload`; it must require the existing legacy timer to remain enabled and active, leave every candidate inactive and the primary timer disabled, retain a root-only rollback set, and restore prior files on failure. It cannot publish a release, activate a selector, start or enable the bridge, stop or disable the legacy exporter, replace legacy output, or satisfy runtime acceptance by itself.

The signed source also carries a static canary unit whose write boundary is a dedicated `/run` directory and whose inaccessible paths include the production legacy-health directory. Its separate operator transaction defaults to a non-authorizing plan; exact-confirmation apply may start only that canary, validate its bounded legacy document, remove temporary output, and stop the canary on failure. It cannot start the primary bridge, enable its timer, mutate the legacy document, stop the old exporter, activate a release, or substitute an isolated canary for final production cutover and rollback evidence.

The final bridge cutover transaction is separately confirmed and overlap-first. It must accept the isolated canary before any production-path write, enable and validate the target timer/writer before disabling the current timer, rehearse signed-primary to old-exporter rollback, restore the signed primary the same way, and preserve a root-only rollback set. Failure recovery re-enables the old timer before disabling the primary and may restore only the public legacy document. It cannot change release selectors, gateway/importer processes, Phi services, credentials, or release activation state.

The read-only `cloudx.phi-mesh-compatibility-profile.v1` document references the existing handshake, health, gateway, client-configuration, signed-release, and rollback contracts. The profile is secret-free and grants no credential, import, gateway-mutation, release-mutation, service, or activation authority.

The secret-free `cloudx.phi-cloud-consumer-credential.v1` policy defines a distinct gateway-only bearer for the Phi cloud service. Its only allowed operation is provider inference through `/v1`; it is not an SSH identity, cannot invoke `cloudx-remote`, read Cloudx auth or release state, import accounts, mutate gateway configuration, stage/activate/rollback a release, or assert a Phi Device, Task, or session identity. Installation, rotation, revocation, and any required gateway restart remain separately confirmed operations.

The repository operator transaction for this credential defaults to a read-only plan and binds apply to one exact staged cloud artifact, the fixed credential path/group/mode, and a distinct restart confirmation. It may append and canary a new gateway key, but it must retain the previous key, leave the existing Cloudx client credential byte-identical, restart only the external gateway, and restore config, credential, and gateway state on failure. It cannot create the Phi identity/group, restart Phi, revoke an old key, or make the privileged-boundary gate secure by itself.

The external CPA policy transaction also defaults to a non-authorizing plan. Stage and activation use different exact confirmations. Stage copies only the pinned candidate beside the active binary and cannot change a launcher, unit, process, listener, credential, or archive. Activation may select that candidate and restart only the declared local or cloud CPA after retaining a private rollback snapshot; it must preserve the original binary byte-for-byte, require health plus the public two-request policy header, and automatically restore the prior launcher or systemd drop-ins on failure. When the active Codex conversation depends on local CPA, local activation additionally requires a real official-Codex request before restart, after candidate selection, and after any rollback; a deferred private worker must let the authorizing turn finish before restart. It cannot upgrade to another upstream revision, restart Cloudx or Phi, or convert an archive into deletion authority.

The read-only `cloudx.phi-cloud-consumer-traffic-policy.v1` contract bounds the one Phi cloud consumer to four in-flight logical requests, a sixteen-entry FIFO queue, thirty gateway attempts per minute with burst four, explicit admission and request timeouts, and at most three attempts. Every retry retains its logical request's in-flight slot and consumes rate budget; no response is retried after response bytes are observed. This is a consumer interoperability policy, not a Cloudx queue or scheduling service.

`cloudx.capacity.v1` is the secret-free runtime capacity classification. It reports exactly one of healthy capacity, exhausted capacity, unknown observation, stale contract, probe failure, or incompatible producer. A missing or partially unobserved aggregate is never guessed to be exhausted, and the document contains aggregate counts only.
