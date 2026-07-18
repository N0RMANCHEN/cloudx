# CPA Policy 3 Local Staging

Date: 2026-07-18

## Decision And Boundary

The operator supplied the exact confirmation:

```text
STAGE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.3 1cff3152e346
```

This authorized side-by-side staging of the exact local candidate only. It did not authorize CPA activation or restart, launcher changes, watcher activation, credential/archive mutation, Cloudx selector changes, cloud actions, process termination, or legacy removal.

## Pinned Candidate

```text
version=7.0.1-codexx-fast-service-tier-cloudx-policy.3
upstream=15ac7fb9324095330e60f522147b8a8e81f16ab5
sha256=1cff3152e34666d2753add54ce7f5f96dbd643e607c1f136a9052cd28eba9ecd
size=41484930
runtime commit=15ac7fb+cloudx-cpa-policy3
build date=2026-07-18T12:30:00Z
```

## Acceptance

- staged path: `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.3/cli-proxy-api`
- binary: owner/group `501/20`, mode `0700`, exact size and SHA-256
- manifest: schema `cloudx.cliproxy-policy-stage.v1`, target `local`, exact version/hash/size, mode `0600`
- runtime `-h` identity matches version, commit label, and build date
- active CPA remained PID/listener `38189`
- active CPA still selects baseline `/Users/hirohi/.local/bin/cli-proxy-api`
- baseline SHA-256 remained `cf9641b3e50ae486aec1698dec88f735589680f9ae98558c29cde184daac3a96`
- launcher SHA-256 remained `80535ade89c6f0de399a6dbab9f69280c933b8fe3c5cbba829f96c86d6325970`
- launcher contains neither failure nor sweep producer environment
- all six captured Codex/Codex-App PIDs remained alive
- the 40-file auth aggregate remained 97079 bytes with digest `883b12ecf5183a54aa95f5f3fed6350ffb952631c3d4e360aa969aa77677e3c2`
- Cloudx selectors remained `0.1.17/0.1.13`

## Next Gate

Both `.policy.3` candidates are staged and inactive. Cloud CPA activation is next and requires a distinct exact confirmation. It will retain the original binary and root-only rollback snapshot, write only the declared producer/drop-in paths, restart only `cliproxy.service`, and require health plus the public maximum-two header. Local activation remains later and must use the deferred 180-second communication-safe worker so the authorizing CPA-backed turn completes before restart.
