# Legacy Health Bridge Production Acceptance

Captured at `2026-07-19T13:10:28Z` on the cloud endpoint. This record is secret-free and contains no credential, account identity, request body, or local path from another product.

## Fixed signed artifact

- The ordinary cloud updater correctly rejected `0.1.15` as a downgrade from active `0.1.21`.
- Operator source `4ff4bbe202af4227db6d13007aa4b50e05ae52fb` then used the separate pinned compatibility-stage transaction.
- Artifact ref commit: `332cb865a97d654efca4b4321b90cdc140e57e64`.
- Source commit: `9ffa3208f39053c2b3af1136a530ce98eac7ad41`.
- Manifest SHA-256: `3d1f9747cefab855725d105f584e938a27bc93baf488598b746418978547595a`.
- Cloud artifact SHA-256: `7e838757727e90b11029d85966525a621f629e5f400fa113abc6168790878b71`.
- `/opt/cloudx/releases/0.1.15` was added root-owned beside production. Selectors stayed `0.1.21/0.1.20`; no release was activated and no service restarted.

## Inactive installation and isolated canary

- Four exact signed files were installed with mode `0644`; only `systemctl daemon-reload` ran.
- Installation rollback set: `/var/lib/cloudx/legacy-health-bridge-install-backups/1784466081658485634`, root-owned mode `0700`.
- The old `cloudx-health-contract.timer` remained enabled and active while the primary bridge timer remained disabled and inactive.
- The isolated canary completed with `ExecMainStatus=0`, output SHA-256 `70ff274ca23a07be3e6987f1c0d230ffa5ba5c1ddc0f0aec7406a1d4b9e5738e`, removed its temporary output, and did not mutate `/var/lib/cloudx/health/v1.json`.

## Overlap, rollback, and restoration

Operator source `8f6c5a1c3a7c3e06895e4ce205e201f7cc2e55a3` accepted the separately retired importer as a continuity state only after proving `codex-import.service` inactive/disabled with PID `0` and no socket on port `8780`.

All five production phases passed without a publisher gap:

1. isolated canary;
2. candidate overlap;
3. candidate cutover;
4. legacy rollback;
5. candidate restoration.

The candidate phases produced SHA-256 `fd6f6203ce81d1bcbdd032c3ef39f206fd17e29fc01c463cc69c5d6e0a0c1d1b`; the distinguishable old exporter rollback produced `9f2cae626b22926dbce13a9091a903109f422e6344ef71047f55346ffda0e2fe`. Cutover backup `/var/lib/cloudx/legacy-health-bridge-cutover-backups/1784466559181899734` is retained root-owned mode `0700`.

## Final state

- `cloudx-legacy-health-bridge.timer`: loaded, enabled, active.
- `cloudx-health-contract.timer`: loaded, disabled, inactive; its service remains retained.
- Public legacy health output: root-owned mode `0644`, SHA-256 `fd6f6203ce81d1bcbdd032c3ef39f206fd17e29fc01c463cc69c5d6e0a0c1d1b`.
- `cliproxy.service`: active, PID `1719083`, restart count `0`.
- `codex-import.service`: inactive, disabled, PID `0`, restart count `0`, port `8780` closed.
- Cloudx selectors: unchanged at current `0.1.21`, previous `0.1.20`.
- Phi service restart: none.
- Local CPA/Codex lifecycle action: none; every transaction and audit in this acceptance was cloud-only.

This closes the two legacy-bridge runtime blockers and makes the recorded Phi/Cloudx current-and-N-1 ordering matrix compatible. It does not revoke rollback data, remove the old exporter service, activate a Cloudx release, restart the gateway, or grant Phi mutation authority.
