# Prompt Engineering

Cloudx prompts are versioned operational tools, not runtime policy.

Each prompt must define:

- purpose and owner
- accepted, redacted inputs
- explicit non-authority boundaries
- a structured output contract
- evidence required for each conclusion
- escalation and stop conditions
- a regression fixture when parsing its output matters

Prompts may explain an incident, classify sanitized import structure, propose a change plan, or review release evidence. They may not receive credentials, choose an account identity, modify production, approve a release, restart a service, merge code, or weaken a deterministic gate.

Runtime code validates every model-produced structure before use. A prompt result is a proposal until deterministic checks and an operator accept it.

The templates under `operations/` and `engineering/` follow the same separation used in Soul-seed: durable product rules live in standards and machine gates; prompts carry task context and expected evidence only.
