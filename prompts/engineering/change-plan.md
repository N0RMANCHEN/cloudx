# Change Plan Prompt

Owner: Cloudx engineering

## Purpose

Plan a repository change against current product standards and runtime evidence.

## Instructions

1. Name the supported behavior being changed.
2. List local, cloud, shared contract, release, and Phi boundary impact separately.
3. Identify active communication dependencies and forbidden actions.
4. Define deterministic tests, a side-by-side canary, rollback, and documentation updates.
5. Reject proposals that require production `git pull`, implicit activation, shared secrets, or Cloudx dependence on Phi.

## Output

Return Markdown sections: `Scope`, `Invariants`, `Files`, `Contracts`, `Tests`, `Canary`, `Rollback`, and `Open Evidence`. Do not claim implementation or verification has occurred.
