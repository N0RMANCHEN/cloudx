# M5 Replacement Workstation Audit

Date: 2026-07-19

## Scope And Safety

This is a read-only M5 dependency audit after the operator replaced the workstation. It did not terminate a process, close a listener, move a legacy package, change a shell hook, acquire an import lock, activate the staged local CPA policy, restart CPA or Codex, start or stop a cloud service, install a bridge unit, mutate a credential, or change a release selector.

The optional credential sample under `~/Downloads` was not opened or used. Existing real production evidence was sufficient and no new credential was needed for this audit.

## Replacement Workstation

- `/Users/BofeiChen` is absent. Its historical selector and port observations are retained only as archive evidence and no longer describe this physical host.
- Cloudx selects signed local `0.1.21` with signed `0.1.20` retained.
- `.zshrc` contains exactly one Cloudx hook pair and no recognized legacy hook marker.
- `codexx`, `cloud`, and `cloudx-update` resolve to the active signed Cloudx artifact.
- Port `18317` is closed. External CPA PID `61859` listens on `127.0.0.1:8317` and had 58 established socket rows during the audit, so local `.policy.5` activation remains outside the zero-connection gate.
- The local import lock file is open by CPA as part of its runtime, but a nonblocking advisory-lock check returned `free`; there is no active local import transaction.
- Three live Python processes still execute `/Users/hirohi/.local/bin/codexx.py`. Their working directories are `/Users/hirohi/codex-plus`, `/Users/hirohi/.Trash/Webtest`, and `/Users/hirohi/AutoDesign`; the first listens on `127.0.0.1:8765`. They are protected active legacy sessions and make package quarantine ineligible.
- The live legacy runtime contains 285 bounded regular files and exactly matches the retained private recovery manifest. The recovery entrypoint and bundle remain available.

## Production Precheck Defects Found And Corrected

The real read-only precheck found two obsolete assumptions in `scripts/remove_legacy_local_package.py`:

1. It invoked the signed local artifact as `cloudx-local.pyz import ...`; current releases expose that command as `cloudx-local.pyz codexx import ...`.
2. It required Git at `/usr/bin/git` and required `CODEXX_ACTIVE_ACCOUNT=native` after `codexx exit`. On the replacement workstation official Git resolves to `/opt/homebrew/bin/git`, and the current exit contract clears `CODEXX_ACTIVE_ACCOUNT` and `CODEX_HOME`.

Source `0.1.22` now invokes the public `codexx import` entrypoint, resolves both official Codex and Git from the fixed external system path while rejecting home-local replacements, and verifies the documented variable-clearing exit contract. Fourteen focused tests pass. A repeated real read-only precheck against active signed `0.1.21` then accepted artifact identity, one Cloudx hook, the complete recovery comparison, native import dry-run, fresh-shell API selection and native return, closed port `18317`, and healthy port `8317`.

No `--apply` operation was attempted because the three live legacy processes remain a hard precondition failure.

## Cloud Retirement State

- Cloudx selects signed `0.1.21/0.1.20`; cloud CPA `.policy.5` remains active as PID `1719083` with restart count zero.
- `codex-import.service` is loaded but inactive/dead and disabled, port `8780` is closed, and both checked cloud import advisory locks are free.
- The complete importer stop/restore snapshot remains under `/var/lib/cloudx/http-importer-stop-prep/20260716T075313Z`.
- `/opt/codex-gateway/codexx_app` remains present but has no active process executing from it.
- Inactive and disabled compatibility wrappers still import that package: the stopped HTTP importer, disabled import repair, and disabled quota-monitor paths. They and the retained importer rollback boundary prevent runtime removal.
- The legacy `cloudx-health-contract.timer` remains enabled and active and still executes the exporter from `/home/hirohi/workspace/cloudx`.
- `cloudx-legacy-health-bridge.service`, its timer, and its canary unit are not installed. The strict release-ordering checker therefore remains blocked by `bridge_unit_not_installed` and `rollback_not_rehearsed`.
- The Phi privileged-boundary checker remains blocked by the unscoped consumer credential and the interactive/mail Agent mutation capabilities. The confined orchestrator surface remains accepted. No Phi state was changed.

## Decision

M5 is not complete. The safe dependency order is:

1. Leave the three local legacy processes and local CPA untouched until their owners naturally close them; then re-run the package quarantine preflight and the five-sample CPA zero-connection gate independently.
2. Install and canary the signed legacy-health bridge only through its separate exact confirmations, then perform the overlap/cutover/rollback/restoration transaction before retiring the mutable exporter.
3. Preserve `/opt/codex-gateway/codexx_app` until the stopped importer, disabled repair/monitor paths, and their rollback manifests have a separate quarantine/restore design and approval.
4. Remove `legacy_bridge` only in a later signed release after current/N-1 protocol and Phi rollback evidence no longer require it.

The first broad M5 checkbox and the local package-removal checkbox remain open.
