# 2026-07-14 Local Shadow Stage 0.1.2

This document records local side-by-side staging only. No local Cloudx release, entrypoint, profile, or shell hook was activated.

## Staged Release

- Destination: `~/.local/lib/cloudx/releases/0.1.2`
- Source commit: `3b3e03f77aa6e0cb0355de8e1b21c3a0564a314e`
- Local zipapp SHA-256: `98462f223fc74bb64eee892e0b8c1bd2b0d833ed6f1b195894ed5647f62f5912`
- Manifest SHA-256: `f59b81ae4643fa73639a1125e43103111ab2b733ce350fa324e0ad2637427087`
- Manifest signature SHA-256: `01ec61c6abcc6f1262b6b4dea7043d4bc334b1ef9c8e18cf7cbe196b35efdf13`
- Artifact self-check: local `0.1.2`, protocol `1..1`, status `ok`

The staged hashes exactly match the signed `0.1.2` release evidence. The release directory is user-owned mode 0700, the zipapp is mode 0755, and manifest, signature, and trust root are mode 0644.

## Continuity Evidence

- `~/.local/lib/cloudx/current`: absent before and after staging.
- Existing `~/.local/bin/codexx`: remained a non-symlink legacy file with unchanged metadata `172382536:1776769678:1783946417:755:hirohi:staff` and SHA-256 `fc089c6b2b8d1aac959a35509407afdc63906ff57eaa1ee682b2d667241448c6`.
- `~/.local/bin/cloud`: absent before and after.
- `~/.local/bin/cloudx-update`: absent before and after.
- Official `codex` resolution: remained `/opt/homebrew/bin/codex`.
- `~/.zshrc` SHA-256: remained `4ac5742ffd0cb292beeb4973108d011e3ffd1208f5b0a59af533a5fc17638ac3`.
- Exact official local Codex PID set: remained `45333,74770,79772,80516,86256`.
- Local port `18317`: absent before and after.

No running session, command resolution, shell configuration, account profile, tunnel, listener, or production cloud state changed.
