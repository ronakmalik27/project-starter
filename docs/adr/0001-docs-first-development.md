# ADR-0001: Docs-first development

- Status: Accepted
- Date: YYYY-MM-DD
- Deciders: the maintainer

<!-- This is a worked example ADR. It also happens to state the foundational
     choice this template embodies. Keep it, adapt it, or replace it. -->

## Context

A change can start from code or from docs. Starting from code tends to leave
requirements, contracts, and rationale implicit - they live in the author's
head and in the diff, and they rot. On a small team (or solo with AI agents
doing much of the building), that implicit context is exactly what a reviewer,
a future contributor, or the next agent session lacks.

## Decision

Docs come first. A feature's requirements, design, data model, and contracts
exist in the knowledge base (docs 01-14) before its implementation starts, and
the docs change first within the same PR when the knowledge base must move. The
documentation review gate (docs/process/06-review-guidelines.md) blocks a push
that leaves docs and code inconsistent. This matches how spec-driven teams
work (design docs before implementation is standard practice at scale).

## Consequences

- Reviews have something to check the code against; "does this match the spec"
  becomes a concrete question.
- AI agents get a stable, loadable context instead of reconstructing intent
  from code each session.
- There is up-front cost: a trivial change still updates a doc line. The doc
  gate is gate-light for records and bookkeeping to keep that cost bounded.
- Requirement ids (FR/SCR/INV) become the traceability spine linking docs,
  code, tests, and PRs.

## Alternatives considered

- **Code-first, document later.** Cheaper per change, but the docs lag reality
  and stop being trusted, which defeats their purpose. Rejected.
- **No design docs, rely on tests as the spec.** Tests capture behaviour, not
  intent or the rejected alternatives; they answer "what" but not "why".
  Rejected as the sole record.
