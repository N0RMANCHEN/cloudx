# CPA policy.5 staging

Date: 2026-07-19

## Boundary

Both exact stage confirmations were exercised only after signed Cloudx `0.1.21` was active on the matching endpoint:

```text
STAGE CLOUD CPA POLICY 7.2.71-cloudx-policy.5 5f83b1821d2b
STAGE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.5 bb6fe9cfcc26
```

Staging authorized side-by-side candidate and manifest writes only. It did not authorize CPA selection, launcher/unit mutation, service restart, credential/archive mutation, watcher activation, Phi mutation, or legacy retirement.

## Cloud

- path `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.5/cli-proxy-api`
- SHA-256 `5f83b1821d2be7cf5b7615973e4e6130d477386e16eae3a50af46e99bf7af7f8`
- size `45322402`, owner/group `root:root`, mode `0755`
- identity `7.2.71-cloudx-policy.5` / `5b7f2361+cloudx-cpa-policy5` / `2026-07-19T09:15:00Z`
- mode-`0644` manifest matches exact target, version, digest, and size
- first stage returned `staged`; exact repeat returned `already-staged`
- the prior cloud installation transaction reverified all protected credential/archive/failure/sweep tree aggregates, watcher states, unit/drop-in bytes, private prerequisites, Cloudx `0.1.21/0.1.20`, CPA PID `1693505`, importer PID `133756`, and restart counts `0`

Cloud CPA remains selected on active `.policy.4`; staging did not restart or rebind it.

## Local

- path `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.5/cli-proxy-api`
- SHA-256 `bb6fe9cfcc26d521ce0dcf9f503d2dffa742bce62bd359cab8f91052116c0db3`
- size `41484978`, owner/group `hirohi:staff`, mode `0700`
- identity `7.0.1-codexx-fast-service-tier-cloudx-policy.5` / `15ac7fb+cloudx-cpa-policy5` / `2026-07-19T09:15:00Z`
- mode-`0600` manifest matches exact target, version, digest, and size
- first stage returned `staged`; exact repeat returned `already-staged`
- the prior local installation transaction reverified native/shell/CPA bytes, the 37-file JSON aggregate, Cloudx `0.1.21/0.1.20`, CPA/listener PID `61859`, and all six captured Codex PIDs

Local CPA remains selected on its original external binary. The local `.policy.5` candidate is inactive, the watcher remains inactive, and activation is prohibited until the private recovery bundle and five consecutive zero-established-connection samples pass.

## Next Gate

Cloud `.policy.5` activation requires a new root-only recovery job that independently restores active `.policy.4`, followed by one separately confirmed `cliproxy.service` restart and real policy/model/local-communication canaries. Local activation remains later and cannot be attempted from this CPA-backed active-connection state.
