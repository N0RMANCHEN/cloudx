# Cloudx Repository Guide

Cloudx is a single-user bridge between the official local Codex runtime and a personal cloud model gateway. It is intentionally smaller than `codex-plus`, `Coffey`, and `Soul-seed`.

## Product Contract

- `codex` always means the installed local Codex product. Cloudx must not replace or wrap that command.
- `codexx` selects native, local CPA, cloud, or named-account modes and manages local account records; selection changes shell state, not the official Codex executable.
- `codexx cloud` holds a Cloudx broker lease for the current shell so the next plain `codex` invocation uses the cloud gateway without wrapping `codex`.
- `codexx import` is a migration-period compatibility adapter for the external local CPA; Cloudx does not own that service lifecycle.
- `codexx cloud import` sends credentials to the cloud importer through SSH.
- `cloud codex` and `cloud import` remain compatibility entrypoints during migration.
- `./install` performs endpoint-aware signed staging and installs the local shell source as part of local activation.
- The local and cloud components are built independently from this repository and share only versioned contracts.
- Cloudx is not a task system, agent control plane, hosted multi-tenant service, or replacement coding runtime.

## Source Of Truth

When documents disagree, use this precedence:

1. `AGENTS.md`
2. `docs/Product-Standards.md`
3. `docs/Quality-Evaluation.md`
4. `docs/Test-Standards.md`
5. `docs/architecture-guardrails.md`
6. `docs/roadmap.md`
7. Other current documents under `docs/`
8. Historical evidence under `docs/archive/`

## Non-Negotiable Safety Rules

1. Never terminate or rebind a legacy communication path as part of build, test, install, or update.
2. New releases are staged beside the active release. Activation and service restart require explicit operator action.
3. Production does not run from a Git checkout and never updates through `git pull`.
4. Runtime credentials, account files, sessions, logs, state, and API keys never enter Git or a release directory.
5. Import writes use size limits, locking, validation, and atomic replacement. Failure records contain no raw secrets.
6. Health output is versioned, read-only, and secret-free.
7. A local release must support the current and previous remote protocol, including an explicit legacy bridge while migration is active.
8. Cloudx must remain useful without Phi. Phi may consume Cloudx health but cannot deploy, restart, merge, or mutate Cloudx state.

## Ownership Boundaries

Cloudx owns account selection, local cloud tunneling, gateway integration, credential import, credential health classification, release staging, and the `cloudx.health.v1` signal.

Phi owns mail commands, goal recovery, DeepSeek or provider monitoring, notifications, and optional repair assistance. A Phi repair workflow may create a candidate patch or pull request only.

Tailscale, SSH, mihomo, systemd, and CLIProxyAPI remain external host dependencies. Cloudx declares and checks their contracts; it does not silently take ownership of them.

## Delivery Rules

- Keep local, cloud, and shared contract code in separate directories.
- Add targeted regression coverage with behavior changes.
- Update `CHANGELOG.md` and `docs/roadmap.md` with shipped batches.
- Run `./verify.sh` before closeout.
- Keep watched Python and shell files below 800 lines unless explicitly frozen in `config/governance/architecture_rules.json`.
- Prefer standard-library implementations and deterministic public behavior tests.
- Keep prompts advisory. Runtime truth and authorization stay in code and persisted state.
