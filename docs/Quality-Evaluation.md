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
- update checking stages, activates, or restarts anything implicitly
- local and cloud protocol compatibility is unknown
- rollback depends on GitHub, the model API, or a mutable source checkout
- a Phi workflow can write Cloudx production state

Repository evidence consists of fresh test output, artifact hashes, a signed manifest for releases, and an operator-visible canary result. Historical notes are useful context but not fresh release evidence.
