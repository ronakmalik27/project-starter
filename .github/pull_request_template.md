<!-- Delete rows that genuinely do not apply, with a word saying why. -->

## What

Fixes #

## Docs-first gate

- [ ] Docs updated first, in this PR: requirement/spec delta, API entry, event
      catalogue row, schema delta (as applicable) - or no doc-visible change
- [ ] New external surface has a threat-model note (or "not a new surface")
- [ ] Deferred features considered for design hooks now

## Quality

- [ ] Tests per the testing strategy (critical-path changes: property/invariant
      tests, no value-corrupting path left uncovered)
- [ ] Migration is compatible with the deployed revision (or no migration)
- [ ] New endpoints emit metrics and redacted logs
- [ ] Runbook/ops note updated if operational behaviour changed
- [ ] Docs style check clean (CI enforces)

## AI authorship

<!-- If a model wrote or co-wrote this, name it here and keep the
     Co-Authored-By trailers on the commits. -->
