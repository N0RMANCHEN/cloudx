# Quality Evaluation

Quality is evaluated in this order:

1. Communication continuity and offline recovery
2. Credential confidentiality and transactional writes
3. Correct failure attribution across local process, SSH tunnel, gateway HTTP, and upstream service
4. Upgrade and rollback behavior
5. Command ergonomics

A release candidate is not ready when any of these are true:

- build or tests modify an active tunnel, gateway, auth directory, service, or release symlink
- a failure path logs raw import content, tokens, API keys, or account identities in health output
- local or cloud diagnosis reads request content, exposes raw upstream messages, or treats generic 429/403/503 status alone as proof of quota exhaustion or account deactivation
- update checking stages, activates, or restarts anything implicitly
- local and cloud protocol compatibility is unknown
- rollback depends on GitHub, the model API, or a mutable source checkout
- a Phi workflow can write Cloudx production state
- a Phi Agent instruction surface can reach Cloudx auth, import, gateway mutation, or release mutation directly or through available privilege elevation
- a Cloudx cloud-runtime output path can bypass the public metadata guard or emit Phi control-plane identifiers, local paths, transfer content, or Phi Artifact metadata
- proxied CPA business requests exceed two concurrent calls; a full account sweep runs without a fresh aggregate-unavailable trigger; a direct failure-receipt consumer performs a network probe; an incident sweep skips its infrastructure/provider gate or archives quota/transient evidence; or either watcher starts before its signed consumer/producer prerequisites or restarts CPA/Codex/Phi

Repository evidence consists of fresh test output, artifact hashes, a signed manifest for releases, and an operator-visible canary result. Historical notes are useful context but not fresh release evidence.
