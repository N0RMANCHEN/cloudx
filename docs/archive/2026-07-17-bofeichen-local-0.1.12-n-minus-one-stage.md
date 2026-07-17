# BofeiChen Local 0.1.12 N-1 Stage Preparation

## Scope

This batch uses the exact-confirmation stage-only path to place signed local `0.1.12` beside the already staged `0.1.13` on the `/Users/BofeiChen` macOS endpoint. It does not activate either release, move `current` or `previous`, install a shell hook, seed a profile, modify a backup, contact the cloud endpoint, start a broker, stop a process, or change the external local CPA.

## Reason

The endpoint still selects signed `0.1.8` as `current` and signed `0.1.7` as `previous`. Directly activating `0.1.13` from that state would not establish signed `0.1.12` as the desired N-1 selector. Staging the exact `0.1.12` artifact first makes the intended predecessor available for a separately approved ordered activation while preserving the existing rollback state.

This preparation grants no authority to perform that activation.

## Real Staging Evidence

The exact command was:

```text
./install local --version 0.1.12 --stage-only --apply --confirm 'STAGE CLOUDX LOCAL 0.1.12'
```

The first execution returned:

```text
schema=cloudx.install-stage.v1
endpoint=local
version=0.1.12
status=staged
staged.local=staged
staged.cloud=not-requested
activated=false
shellSourceInstalled=false
nativeProfileChanged=false
legacyBackupChanged=false
```

A repeat returned `staged.local=already-staged` with the same non-activation fields.

The staged artifact returned `cloudx.self-check.v1` with local component, version `0.1.12`, protocol range `1..1`, and status `ok`. Public artifact evidence is:

```text
manifest sha256 = 9f4c6e59db3975756aad3ae048087beb54eada1ba2120be1d8c24482e5976e86
local pyz sha256 = 10065be877ab788ca3a9b7cd1ebb5013369989d98007b3dea31472d0035fec28
```

## No-Activation Acceptance

Before and after staging:

- `current` remained `0.1.8`
- `previous` remained `0.1.7`
- `.zshrc` and the installed Cloudx shell source remained unchanged
- the external local CPA retained PID `17165` and port `8317`
- port `18317` remained closed
- no Cloudx broker process appeared
- no cloud release was requested

## Decision

Signed `0.1.12` and `0.1.13` are now both verified side-by-side candidates on this endpoint. A later transition that intentionally ends at `current=0.1.13` and `previous=0.1.12` must be a separately confirmed activation transaction with canary and rollback evidence. This batch performs and authorizes none of those runtime changes.
