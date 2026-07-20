# Process docs

This directory is the process playbook: how work moves from an idea to a
merged, released change. Start with 00-principles.md - everything else in
this directory is an application of those principles to a specific part of
the workflow.

## Index

- **00-principles.md** - the engineering principles every other doc in this
  set assumes.
- **01-lifecycle.md** - the path a piece of work travels, from idea to
  release.
- **02-governance.md** - readiness and done criteria, decision authority,
  branch protection summary.
- **03-coding-standards.md** - generic coding standards (naming, error
  handling, secrets, dependency hygiene, formatting).
- **04-architecture-principles.md** - module boundaries, contracts,
  observability, security by design, data integrity.
- **05-documentation-standards.md** - writing style and documentation
  standards.
- **06-review-guidelines.md** - the persona review gate, severity rubric, and
  the external bot-reviewer protocol.
- **07-testing-strategy.md** - the test layer map, coverage floors, and
  determinism rules.
- **08-iteration-cycle.md** - the plan, execute, QA, retro loop for running
  work in iterations.
- **09-decision-framework.md** - when a decision needs an Architecture
  Decision Record (ADR) and how ADRs move through their lifecycle.

## The workflow in one view

Every change rides a pull request through the gates. There is no direct push
to the default branch.

- **Docs** go through the doc gate before they are pushed (see the
  `/doc-gate` command in `.claude/commands/`). The gate is described in
  06-review-guidelines.md and 05-documentation-standards.md.
- **Code** goes through `/review-gate` before every push and
  `/pre-merge-gate` before merge (both in `.claude/commands/`). See
  06-review-guidelines.md for the persona loop and external reviewer
  protocol.
- **Iterations** are opened, executed, QA'd, and retro'd with the
  `/sprint-plan`, `/sprint-execute`, `/sprint-qa`, and `/sprint-retro`
  commands (`.claude/commands/`), following the loop in
  08-iteration-cycle.md.

If you are new to this repository, read 00-principles.md, then
01-lifecycle.md, then whichever doc covers the part of the workflow you are
about to touch.
