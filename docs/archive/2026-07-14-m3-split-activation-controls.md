# 2026-07-14 M3 Split Activation Controls

This batch prepares M3 without activating either endpoint.

## Delivered

- Repository source advanced to `0.1.2`; the signed and staged `0.1.1` artifacts remain unchanged.
- `cloudx-remote release-status` reports only validated release versions and the active artifact SHA-256.
- Invalid, incomplete, or out-of-root `current` and `previous` symlinks are rejected.
- `cloudx-update apply` and `rollback` require exactly one of `--cloud-only` or `--local-only`.
- A cloud-only activation verifies the authoritative release status and does not require or modify a local staged release.
- Cloud-only commands reject local shell-hook and native-profile options.

## Validation

- Targeted release flow, release matrix, and remote client tests: 12 passed.
- Required closeout `./verify.sh`: architecture passed, 52 tests passed, and deterministic local/cloud `0.1.2` builds passed.
- No local or cloud production release symlink was changed by this repository test batch.
- No service, credential, auth directory, legacy tunnel, or port was changed.

The next node is to build, sign, publish, and side-by-side stage `0.1.2`; activation remains an explicit later operator action.
