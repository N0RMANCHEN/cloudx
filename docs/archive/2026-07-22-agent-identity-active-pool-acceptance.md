# Agent Identity Active Pool Acceptance — 2026-07-22

This record contains secret-free production acceptance evidence for the ten-record Agent Identity batch. No credential filename, runtime identifier, private key, bearer token, task identifier, or raw request body is retained here.

## Bound input and releases

- Request SHA-256: `e86e54fbf3895cc3059cbc675312719359a0fc775d1a9f333d3b7d837cc63517`
- Input size: `14006` bytes
- Expected transition: `1 + 10 = 11` active credentials
- Signed Cloudx: `0.1.25`, with `0.1.24` retained on both endpoints
- Source release commit: `f1b27ce01fcf525198d2b13cbdea25b889f7a060`
- Complete offline bundle SHA-256: `931062f538fdc4b603fd13b132b280edb8332a18377478605c88bd3347ad5091`

## Contained predecessors

The policy6 attempt returned HTTP `403` during task registration and transaction `20260722T094501Z-776804f3` restored the one-account baseline. Official Codex source comparison identified the required `originator: codex_cli_rs` header.

Policy7 added that header and activated with backup `1784716348899266147-cloud`, but transaction `20260722T103349Z-f053bf7b` was also contained. A root-private comparison proved direct cloud egress received the provider's unsupported-region HTTP `403`, while the already configured mihomo route succeeded. Both failed transactions retained recovery material, stored no raw input, preserved archive/watcher state, and restarted no service.

## Accepted producer and promotion

Cloud CPA `7.2.71-cloudx-policy.8` inherits account-level proxy override first and global `proxy-url` second for initial and invalid-task registration. Two independent Linux/amd64 builds were byte-identical:

- SHA-256: `4dfa561451662ca5deae566f6fcfdc32bec7f42590439fa053000c4b84f915c0`
- Size: `45359266`
- Activation backup: `1784718280076915831-cloud`
- Active PID/restart count: `1871934 / 0`

The active binary, systemd selection, and `cloudx.cloud-cpa-capabilities.v1` sidecar match that digest and advertise `codex-agent-identity-v1`. Existing bearer traffic and an isolated Agent Identity each returned HTTP `200` with business concurrency policy `2` before formal promotion.

Transaction `20260722T111007Z-1f2d49a8` then completed with:

- active count `1 -> 11`
- ten distinct Agent Identities
- ten isolated cohort canaries in thirteen attempts
- one final combined-pool canary
- repeat signed preview `written=0`, `skipped=10`
- archive entries `45`
- failure inputs `0`
- sweep trigger absent
- CPA PID/restart count unchanged
- service restart `false`
- raw credential stored `false`

The signed health maintenance one-shot completed successfully and archived zero records; active count remained eleven. Official Codex returned the exact final cloud marker through the upgraded local Cloudx `0.1.25` broker path.

## Local endpoint acceptance

The workstation installed signed `0.1.25` from the verified complete bundle and retained `0.1.24`. Installation reported `nativeProfileChanged=false`. Official Codex resolution, the accepted external Agent Identity CPA binary, and CPA PID `15946` remained unchanged. Real API-profile communication passed before and after installation.
