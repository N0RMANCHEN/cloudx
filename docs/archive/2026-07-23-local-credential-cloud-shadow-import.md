# Local Credential Cloud Shadow Import

Date: 2026-07-23

The operator authorized extracting the current workstation's local CPA accounts and importing them to cloud after the Phase 1 official-Codex canary reached the authorized gateway path but found no usable active account.

The local auth root contains credential JSON plus nested operational directories. A first recursive ordinary-cloud dry-run returned `missing_token`, `written=0`, and changed nothing. Read-only structural validation of the 74 top-level JSON files found 74 supported records: 22 Agent Identity and 52 token credentials.

A private temporary directory was created outside the repository with directory mode `0700` and copied top-level files mode `0600`. It was transmitted only through `cloud import`, which retains the 16 MiB bound, SSH stdin transport, importer lock, validation, atomic replacement, and secret-free response contract.

- exact request SHA-256: `050047f47b170a0d95755ea5d7338d07f2af56497e70dff01a27b1ecafa0e8f4`
- dry-run: accepted, `written=42`, `skipped=32`, zero errors
- apply: accepted, `written=42`, `skipped=32`, zero errors
- repeated dry-run: accepted, `written=0`, `skipped=74`, zero errors

This was an ordinary shadow import only. It did not write the active CPA auth directory, restart a process or service, modify the scoped gateway keys, or establish usable cloud capacity. The existing rollback-bounded Agent Identity promotion script remains safely unusable on the current endpoint because its exact release gate is historical Cloudx `0.1.26`. A signed current-version binding is the next prerequisite before selecting a new Agent Identity cohort for active promotion.
