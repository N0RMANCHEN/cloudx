# 2026-07-15 Simplified Mode Rollout

This document records the signed Cloudx `0.1.5` rollout, trust-root recovery, exact simplified command acceptance, installer verification, Phi repair handoff preparation, and continuity evidence. No legacy service was stopped, rebound, or deleted.

## Release Recovery And Publication

The tag-triggered `v0.1.3` workflow passed repository verification but failed before artifact publication because usable signing material for the committed trust root was unavailable. The tag remains unchanged and no `release-artifacts/v0.1.3` ref exists.

Recovery followed the patch-forward rule:

- replacement private key: repository-external, mode `0600`
- replacement public-key fingerprint: `SHA256:y3TOEy0VreM9X6WCDsRHj6UYEgpxjYDaab3d4loGOIc`
- public trust root committed in source `370aa4904cf143f9ed87b3fff37e8f76155819aa`
- immutable `0.1.4` artifact ref: `05d6e24050916453404d3958ffaac00a3b7f1655`
- failed `v0.1.3` tag: not moved or reused

Because active `0.1.2` artifacts embedded the unavailable old public root, signed `0.1.4` used the documented one-time candidate stage recovery. Both endpoints verified the candidate signature, manifest, artifact hash, and self-check before activation. No service restart occurred.

The ordinary signed update path was then proved with `0.1.5`:

- source commit: `db05c9004fee0def4ca73553f28a255423aea133`
- immutable artifact ref: `release-artifacts/v0.1.5` at `4c49b4fb2b5ce07475b779995fcb61db3d735fb1`
- signed stable ref: `release/stable` at `da2fcf5cc836c96e525ea15ba3d04304e133e5c6`
- local artifact SHA-256: `c9697ed65e7fedd29c0b5614e44ac85e5fc3f4b025dcd6d40afd2f3c2c3b2459`
- cloud artifact SHA-256: `ca5f00352a9d988fda92b36a8e174608a8f22f11972e4026f35dbd153e83d909`
- manifest SHA-256: `529a13104c1aec21007fc1f10e4b78781775f3173a8ea68e7e2fab01058499b1`
- manifest signature SHA-256: `eef5ce03a14084d5a532ba16dff467c71602b0e3cca1f4fb8b488e7fa0ba18bc`
- offline bundle SHA-256: `90ccad2d96459137ccb1f39773757f7eef59add12bf4ab182611b9a193a3b507`
- stable index SHA-256: `0b5e802cc4d74a744f110abd6e4f08a920369fe4318f6050ecb0f0df23f85bff`
- stable signature SHA-256: `1b98cf225269243f527185fc682325cbdcdd4799d608d070cc8f06ec88a1dd9e`

Fresh clones of both remote refs repeated signature, source revision, manifest digest, artifact-ref, and stable-index verification. The installed `0.1.4` updater staged `0.1.5` on both endpoints through the normal formal helper path.

## Final Endpoint State

- local current: `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.5`
- local previous: `/Users/BofeiChen/.local/lib/cloudx/releases/0.1.4`
- cloud current: `/opt/cloudx/releases/0.1.5`
- cloud previous: `/opt/cloudx/releases/0.1.4`
- official local Codex: `/opt/homebrew/bin/codex`, version `0.144.3`
- cloud official Codex: `/usr/local/bin/codex` to the global `@openai/codex` package

The cloud helper reported self-check version `0.1.5`, healthy gateway `7.2.71`, fresh secret-free health, and a valid client configuration with its key redacted from evidence.

## Simplified Command Acceptance

From clean zsh processes using the installed hook:

- native `codex` resolved directly to `/opt/homebrew/bin/codex`.
- `codexx api` selected mode `api`, account `api`, and `/Users/BofeiChen/.codex-accounts/api/.codex` while preserving the real user home.
- a complete local API/CPA model request returned exactly `CLOUDX_014_API_OK`.
- `codexx cloud` selected an isolated Cloudx home and acquired a 36-character shell-owned lease while plain `codex` remained the official binary.
- complete cloud model requests returned exactly `CLOUDX_014_CLOUD_OK` and, on the final release, `CLOUDX_015_CLOUD_OK`.
- `codexx soul0` selected the existing account and `codexx exit` cleared mode, account, and `CODEX_HOME` state.
- a temporary account completed add, rename, select, exit, and reversible remove-to-archive operations.
- `codexx cloud import` accepted a credential-free synthetic local file with `dryRun=true`, `written=1`, and no errors.
- `codexx import` reached the explicit legacy local adapter in a non-mutating missing-path probe. No synthetic local credential write was attempted because the adapter has no Cloudx dry-run contract.
- after each cloud canary the broker reported zero leases and shut down; it never bound the legacy port.

Compatibility commands `cloud codex`, `cloud import`, and `codexx use <account>` remain available during observation.

## Installer And Rollback Acceptance

`./install` produced distinct local and cloud plans with exact confirmations. A real repeated local install of signed `0.1.5` returned:

- local stage: `already-staged`
- activation: `active`
- shell source installed: `true`
- legacy backup: not repeated
- actual retained `previousLocal`: `0.1.4`

The installed `.zshrc` contains exactly one Cloudx source block. Native `auth.json` and `config.toml` exactly match the `soul0` source and remain mode `0600`.

A real one-endpoint-at-a-time rollback rehearsal completed:

1. local `0.1.5 -> 0.1.4 -> 0.1.5`
2. verify `codexx api` and official `codex` while local `0.1.4` was active
3. cloud `0.1.5 -> 0.1.4 -> 0.1.5`
4. verify cloud self-check and gateway continuity at both versions

Final `current` and `previous` links are the values listed above.

## Legacy And Service Continuity

Pre/post process identity remained exact:

- local legacy `18317` SSH listener: PID `78601`
- external local CPA on `127.0.0.1:8317`: PID `17165`
- cloud CLIProxyAPI: PID `977036`
- old cloud HTTP importer: PID `133756`

No current Codex or Phi session was terminated. No cliproxy restart, gateway bind change, systemd mutation, Tailscale change, VPN change, credential deletion, or production auth replay occurred.

## Phi Inventory And Repair Handoff

Read-only inspection confirmed Phi `0.80.6`, its aliases, ten staged Phi release directories, the official cloud Codex installation, the Tailscale-bound CLIProxyAPI listener, and the Phi/legacy/Cloudx units described in the roadmap. These are migration inputs only; no unit was disabled or deleted.

A credential-free repair handoff was validated and prepared using Phi's own `deploy.cloud.phi_repair_pr` workflow:

- request ID: `cloudx_nested_envelope_20260715`
- exact base revision: `db05c9004fee0def4ca73553f28a255423aea133`
- request SHA-256: `f3b290a5062808b3796b2e48a5cf4ac75673eb3372688a08e1a306398fd4b076`
- fixture SHA-256: `1d5683c8f5a8dbf4aa7eb6296fd2ea6697f6477a522691afa4ec039b67522298`
- branch: `phi-repair/cloudx_nested_envelope_20260715`
- validation and preparation: `production_changed=false`, `network_used=false`

The private request/control/worktree directories are outside Git. A dedicated push keypair was generated separately; only its public key is in the forwarding package. GitHub registration and a repository-only pull-request token remain explicit external authorization steps. No credential entered this repository or the forwarding archive.

## Verification

The `0.1.5` release source passed `./verify.sh`: architecture gate, `84` tests, and deterministic `cloudx-local-0.1.5.pyz` plus `cloudx-cloud-0.1.5.pyz` builds. After publication and activation evidence was recorded, repository development advanced to `0.1.6` so the signed version cannot be rebuilt from a different source revision; the closeout verification repeated the architecture gate, all `84` tests, and deterministic `0.1.6` candidate builds.
