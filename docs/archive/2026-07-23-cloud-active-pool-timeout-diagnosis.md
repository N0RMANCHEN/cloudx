# Cloud Active-Pool Timeout Diagnosis

Date: 2026-07-23

This item investigated the cloud `/responses` timeout observed after the ordinary doghubx shadow import. It was deliberately read-only: no credential was copied, held, promoted, rewritten, restored, or archived; no release selector, unit, process, listener, or proxy configuration was changed; and no service was started, stopped, or restarted. Because the transaction had no mutation authority, its rollback boundary was preservation of the complete production baseline before and after observation.

## Pinned Baseline

- Cloudx selected signed `0.1.29/0.1.28`; current cloud artifact SHA-256 was `272ce07da46da5f3d6c9e52dd108a2517bec4eadab3f0547324f6631413e8aa5`.
- The active CPA was `/opt/cliproxy-cloudx/releases/7.2.71-cloudx-policy.8/cli-proxy-api`, PID `1871934`, restart count `0`, listening on the declared Tailscale address and port `8317`.
- Mihomo was active with PID `277808`, restart count `0`.
- The active directory contained `11` regular JSON records. The separate shadow directory contained `45`; ordinary cloud import had not promoted any of them.
- The archive contained `46` records, the permanent-failure input directory was empty, and the sweep directory contained one identity-free pool observation.

## Evidence

Formal handshake and gateway probes remained healthy, which excludes listener, tunnel, and gateway-process failure. Redacted CPA request logs then distinguished the client symptom from the server result:

- the first official-Codex websocket remained open for about `30.298` seconds and delivered a structured HTTP `503` error with `auth_unavailable`;
- subsequent websocket attempts returned the same result in roughly `65` to `178` milliseconds;
- direct `POST /v1/responses` attempts returned HTTP `503` in milliseconds after the pool had converged unavailable;
- at least one real upstream attempt returned explicit HTTP `402 deactivated_workspace` before selection converged to aggregate `auth_unavailable`.

The signed sweep watcher ran after the aggregate incident signal. Its secret-free receipts showed `probe_gate=reachable`, `probe_concurrency=1`, `unique_probe_credentials=1`, and `archived_count=0`. Earlier observations classified that one bearer-eligible credential as weekly limited; later observations reported `probe_error`. The remaining ten active records are Agent Identity credentials and are intentionally excluded from the bearer/JWT sweep path, so the formal health producer reports only the one probe-eligible record and must not guess Agent Identity usability. At final observation it therefore truthfully reported no available account and an unknown or stale capacity state rather than healthy capacity.

## Conclusion

The post-import timeout was not caused by doghubx shadow import, credential promotion, a dead listener, mihomo failure, or a CPA restart. It was the official-Codex websocket waiting for usable authentication and eventually surfacing the active pool's aggregate `auth_unavailable` result. The active pool no longer had observed usable capacity for the requested traffic. This diagnosis does not authorize promoting shadow credentials or mutating the active pool; either action remains a separate exact-confirmation, rollback-backed production transaction.

Final preservation checks matched the baseline: active `11`, shadow `45`, archive `46`, failure inputs `0`, sweep observations `1`, CPA PID `1871934` with restart count `0`, mihomo PID `277808` with restart count `0`, and signed Cloudx `0.1.29/0.1.28` still selected.
