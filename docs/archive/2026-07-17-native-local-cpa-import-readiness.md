# Native Local CPA Import Readiness

## Scope

This batch removes the source-level `codexx import` dependency on the private codex-plus recovery package. It does not install or activate a release, write a production credential, change a shell selector, restart the external local CPA, remove `codexx-legacy`, or delete the codex-plus directory.

Cloudx continues to treat CLIProxyAPI as an external service. The native code owns only the migration compatibility adapter that normalizes an operator-selected source and writes the configured external auth directory.

## Dependency Audit

The `/Users/BofeiChen` fresh shell already used only the Cloudx hook and resolved official `codex` directly. No process had a codex-plus working directory, but `~/.local/bin/codexx-legacy` still pointed into the private `0.1.8` recovery bundle and source `local_cpa.py` invoked it for every local import. The external CPA remained launchd label `com.codexx.cliproxyapi`, PID `17165`, listening on `127.0.0.1:8317`.

The retained recovery implementation and the current codex-plus checkout had identical hashes for their import parser, auth writer/scanner, record normalizer, command parser, and OAuth refresh modules. That exact behavior supplied the compatibility input rather than an inferred or narrowed format list.

## Native Compatibility

Source `0.1.15` now accepts:

- flat CPA/Codex auth JSON
- sub2api exports and individual `credentials` entries
- `codexx-cliproxy-auth-bundle` files
- JSON arrays, JSONL, NDJSON, and concatenated JSON objects with text banners
- bounded recursive directories with ignored VCS, environment, dependency, and cache trees
- redirected stdin
- the existing raw-card line format, with refresh only during apply

The public result is `cloudx.local-cpa-import.v1`. Human output reports status, local-CPA destination, written/skipped counts, verification, source/credential counts, skip reasons, and the explicit `Cloudx native compatibility (external local CPA)` adapter. Redirected count output remains available; `--json` forces the versioned result. Failures use stable codes, sanitized messages, and nonzero exits.

## Write Safety

- one source file is limited to 16 MiB
- a directory is limited to 1,024 candidates and 64 MiB total
- explicit and discovered symlinks fail or skip closed
- the target auth directory must be absolute and outside Cloudx release/state roots
- apply uses a mode-`0600` lock with a ten-second acquisition bound
- targets must be regular files
- normalized JSON is written mode `0600` through atomic replacement
- identical normalized targets are unchanged
- every written file is verified for exact bytes and token presence
- a later failure restores overwritten bytes and removes newly created files
- no failure output contains a token or raw input snippet
- import never starts, restarts, stops, upgrades, or configures the external CPA

`--dry-run` performs parsing, normalization, deduplication, target comparison, and prospective counts without creating the auth directory, lock, target file, or raw-card refresh request.

## Verification

Targeted tests cover flat, sub2api, bundle, JSON-array, concatenated, directory, stdin-facing wrapper, raw-card, duplicate, unchanged, conflict, force, dry-run, JSON/human/raw UX, mode-`0600`, symlink, size, protected-directory, partial-write rollback, and secret-redaction behavior.

Two real operator-selected JSON files that had already been imported through the legacy adapter were then passed to the source-tree native adapter with `--dry-run --json`. Each result reported:

```text
discovered=1
parsed=1
duplicates=0
written=0
unchanged=1
status=preview
```

The external auth directory retained the same 44 JSON files and byte-for-byte aggregate before and after both previews. The adapter reported `externalService.managed=false` and `externalService.restarted=false`; CPA PID `17165` retained its identity.

Full `./verify.sh` passed architecture validation, 226 tests, and healthy local/cloud `0.1.15` builds.

## Decision

The package-level import dependency is removed in source and the M5 readiness subitem is complete. The installed endpoint still runs signed `0.1.8`, so `codexx-legacy` and the private recovery bundle remain required rollback inputs. Their deletion still requires a signed release containing this adapter, explicit local activation, a real import/verification and rollback acceptance transaction, confirmation that no other recovery command needs the package, and a separate operator-approved M5 removal action.
