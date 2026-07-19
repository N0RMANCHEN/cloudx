# CPA Policy.4 Staging

Date: 2026-07-19

## Boundary

The standing operator authorization accepted two independent stage gates:

```text
STAGE CLOUD CPA POLICY 7.2.71-cloudx-policy.4 3e3ed137ff90
STAGE LOCAL CPA POLICY 7.0.1-codexx-fast-service-tier-cloudx-policy.4 08608c2ebba6
```

Stage copies verified candidate bytes and a manifest beside existing releases. It grants no launcher/unit edit, service restart, process action, credential/archive mutation, watcher change, or Cloudx selector movement.

## Cloud

- path `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.4/cli-proxy-api`
- SHA-256 `3e3ed137ff90132203f2b0e969245b6580b3ff2b780e2f3a47b821642fd6fdc4`, size `45322402`
- root-owned mode `0755`; manifest root-owned mode `0644`
- runtime identity `7.2.71-cloudx-policy.4`, commit `5b7f2361+cloudx-cpa-policy4`, build time `2026-07-19T08:00:00Z`
- CPA PID `1613475`, importer PID `133756`, restart counts `0`, active `.policy.3` ExecStart, Cloudx `0.1.20/0.1.19`, one credential, 45 archive entries, failure/sweep aggregates, and unit selection unchanged

Private evidence: `/var/lib/cloudx/cpa-policy-stage-evidence/20260719T084900Z-policy4`.

## Local

- path `/Users/hirohi/.local/lib/cliproxy-cloudx/releases/7.0.1-codexx-fast-service-tier-cloudx-policy.4/cli-proxy-api`
- SHA-256 `08608c2ebba606115a5c4bf6588896af3d2bdeb6e71ed308e17a84148766cd29`, size `41484930`
- owner mode `0700`; manifest mode `0600`
- runtime identity `7.0.1-codexx-fast-service-tier-cloudx-policy.4`, commit `15ac7fb+cloudx-cpa-policy4`, build time `2026-07-19T08:00:00Z`
- CPA PID `61859`, all six captured Codex PIDs, original binary/config/LaunchAgent, Cloudx `0.1.20/0.1.19`, and the 37-file auth aggregate unchanged

Private evidence: `/Users/hirohi/.local/state/cloudx/cpa-policy-stage-evidence/20260719T085100Z-policy4`.

## Next Gate

Cloud activation is separately recovery-bounded and restarts only `cliproxy.service`. Local activation remains prohibited until its prepared recovery job and five consecutive zero-established-connection samples pass; no Codex process may be stopped to create quiescence.
