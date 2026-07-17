# BofeiChen Local Ordered Activation Rehearsal

## Scope

This batch rehearses the exact local transition required for the separately audited `/Users/BofeiChen` endpoint. The real endpoint remains on signed `current=0.1.8` and `previous=0.1.7`; production activation, account/profile changes, process changes, and old-package retirement remain unapproved.

The rehearsal uses only isolated `CLOUDX_USER_HOME` state under a mode-`0700` canonical `/private/tmp` root. It does not invoke a model, import an account, copy a credential, contact the cloud endpoint, start a broker, or alter a production release link.

## Inputs

The endpoint already held verified signed local artifacts for `0.1.7`, `0.1.8`, `0.1.12`, and `0.1.13`. All four returned healthy `cloudx.self-check.v1` responses with protocol range `1..1`. Physical copies placed in the canonical isolated release root retained the exact source artifact hashes.

The initial isolated selectors reproduced the real endpoint:

```text
current=0.1.8
previous=0.1.7
```

No account profile was copied. Each transition directly invoked the currently selected release's updater with `CLOUDX_DISABLE_UPDATE_CHECK=1` and installed only the target release's packaged shell hook inside the isolated home.

## Alias-Root Negative Evidence

An initial attempt reused the production release directories through symlinks. Signed `0.1.13` compares the resolved `current` target with the unresolved destination during same-version apply, so the alias made them appear different and replaced `previous=0.1.12` with `previous=0.1.13`. The requested rollback to `0.1.12` then failed closed with:

```text
requested local rollback version is not the previous release
```

This is the already documented signed-`0.1.13` alias-root defect. Source `0.1.14` resolves both sides before comparison and has a focused regression. The real endpoint's release directories are physical, not symlinks, so the invalid rehearsal topology was discarded rather than treated as production evidence.

## Canonical Physical-Root Sequence

The retry used physical artifact copies in a canonical root and passed this sequence:

1. start at `current=0.1.8`, `previous=0.1.7`
2. invoke the `0.1.8` updater to activate `0.1.12`, yielding `current=0.1.12`, `previous=0.1.8`
3. invoke the `0.1.12` updater to activate `0.1.13`
4. invoke the newly current `0.1.13` updater twice for hook reconciliation and idempotence, retaining `previous=0.1.12`
5. roll back to `0.1.12`, then run its same-version apply to restore the release-matched hook, yielding `current=0.1.12`, `previous=0.1.13`
6. reactivate `0.1.13` through the current `0.1.12` updater
7. reconcile and repeat through the newly current `0.1.13` updater

The first and final `0.1.13` states both produced the same stable `.zshrc` SHA-256:

```text
98e6eedb6d1582e1afb7b12cbb548596f6c19579b99734db9b0c2d4527e4da02
```

The rollback hook exactly matched the packaged `0.1.12` hook. The final hook exactly matched the packaged `0.1.13` hook, with SHA-256:

```text
e76347b0589887000022fb9d1562bd8f722f200a0baec30bdc24ca3011771671
```

Final isolated state was `current=0.1.13`, `previous=0.1.12`; the current artifact returned healthy local self-check version `0.1.13`. A fresh zsh sourced the isolated hook, executed `codexx --help` and `cloudx-update --help`, and preserved the pre-existing official `codex` resolution.

## Production Continuity

After both the negative and canonical rehearsals:

- real `current` remained `0.1.8`
- real `previous` remained `0.1.7`
- the external local CPA retained PID `17165` on port `8317`
- port `18317` retained zero listeners
- no production Cloudx broker was started

## Decision

The ordered local activation and N-1 rollback mechanics are ready for this endpoint's physical release layout. Production activation still requires a separate explicit operator decision, pre/post selector and shell hashes, a fresh-shell acceptance pass, local API and cloud canaries, protected-process continuity checks, and a rollback transaction. This rehearsal grants none of that authority.
