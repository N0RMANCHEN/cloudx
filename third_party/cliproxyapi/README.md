# CLIProxyAPI policy patches

Cloudx does not own or silently upgrade CLIProxyAPI. These patches are a
reproducible, operator-selected compatibility layer for the two exact CPA
revisions already deployed on the accepted local and cloud endpoints.

The patched binaries enforce one global ceiling of two in-flight proxied API
requests. Later requests wait for a slot until their request context is
cancelled. Health, management, OAuth callback, and local model-list endpoints
do not consume a slot.

The patches can also emit private `cloudx.cpa-auth-failure.v1` receipts. Receipt
emission is disabled unless both `CLIPROXY_AUTH_DIR` and
`CLIPROXY_AUTH_FAILURE_DIR` name absolute directories. One conclusive permanent
authentication result is sufficient; a provisional refreshable 401 is not.
Explicit `deactivated_workspace`, account disable/delete, non-refreshable 401,
refresh invalid-grant/reuse/revocation, and missing-token results are supported.
Weekly or ordinary quota exhaustion, HTTP 429, network errors, timeouts, and 5xx
responses never produce a receipt. A later successful request or refresh clears
pending evidence and any receipt.

Cloudx maintenance code independently validates receipt age, schema, flags,
top-level filename, and the SHA-256 of the still-active auth file before moving
that file into a private same-filesystem archive. The move is reversible. CPA
itself never deletes or moves an auth file.

`agent-identity-manifest.json` separately pins the replacement workstation's
official `v7.0.2` source, one reviewed Agent Identity plus fast-tier patch, the
Go toolchain, deterministic build identity, and candidate bytes. The patched
runtime registers a fresh task, emits per-request `AgentAssertion` signatures,
re-registers once for an invalid task, and exposes only the capability name on
the existing loopback `/healthz` response. It never trusts an imported task ID.
Cloudx binds that live response to a sidecar manifest and the exact on-disk
binary digest, so a later upstream replacement is re-evaluated automatically
instead of inheriting a stale capability assertion.

The cloud target in `policy-manifest.json` composes that reviewed implementation
onto exact upstream `v7.2.71` without weakening policy5. The original patch is
path-limited to five compatible files, while
`patches/v7.2.71-agent-identity-port.patch` adapts the current uTLS executor and
middleware locations. `patches/v7.2.71-agent-identity-originator.patch` adds the
official Codex `originator: codex_cli_rs` registration header required by the
current account endpoint. `patches/v7.2.71-agent-identity-global-proxy.patch`
makes registration inherit the same account-level-then-global proxy selection as
normal Codex traffic, avoiding unsupported-region direct egress. Cloud policy8
exposes the same capability, retains the
two-request and failure/sweep contracts, and is accepted only after a
deterministic Linux/amd64 build. Its activation publishes the digest-bound cloud
capability sidecar only after the live restarted candidate advertises the
header; rollback restores both systemd drop-ins and the prior sidecar.

`policy-manifest.json` pins the upstream commit, patch digest, Go version,
target platform, and build identity. `scripts/build_cpa_policy_candidate.py`
applies a patch to a clean exact checkout, runs focused regression tests, and
builds only a side-by-side candidate. It cannot install, activate, or restart a
service.
