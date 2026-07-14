# Import Repair Proposal Prompt

Owner: Cloudx importer maintainers

## Purpose

Turn a sanitized structural failure fixture into a candidate parser test and pull request plan.

## Non-Authority

This prompt cannot read raw credentials, edit the production checkout, deploy a parser, restart an importer, replay production input, merge a branch, or change an auth directory.

## Input

- redacted JSON shape with values replaced by type markers
- parser error code and location
- current contract version
- existing fixture names and expected normalized fields

## Instructions

Produce the smallest parser hypothesis that preserves existing formats. Require a failing regression fixture before implementation. Flag ambiguous fields instead of guessing token meaning.

## Output

Return JSON with `schema`, `hypothesis`, `fixture`, `compatibilityRisks`, `proposedFiles`, `tests`, and `pullRequestOnly`. `pullRequestOnly` must be `true`; schema is `cloudx.prompt.import-repair.v1`.
