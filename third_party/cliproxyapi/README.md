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
`CLIPROXY_AUTH_FAILURE_DIR` name absolute directories. A receipt requires two
pieces of evidence within ten minutes and at least one conclusive permanent
authentication signal. Weekly or ordinary quota exhaustion, HTTP 429, network
errors, timeouts, and 5xx responses never produce a receipt. A later successful
request or refresh clears pending evidence and any receipt.

Cloudx maintenance code independently validates receipt age, schema, flags,
top-level filename, and the SHA-256 of the still-active auth file before moving
that file into a private same-filesystem archive. The move is reversible. CPA
itself never deletes or moves an auth file.

`policy-manifest.json` pins the upstream commit, patch digest, Go version,
target platform, and build identity. `scripts/build_cpa_policy_candidate.py`
applies a patch to a clean exact checkout, runs focused regression tests, and
builds only a side-by-side candidate. It cannot install, activate, or restart a
service.
