# 08 - Iteration cycle

Work is organised into short iterations. Each one is opened with a plan, worked
one story at a time, QA'd, and closed with an honest retrospective. The four
phases have executable commands in `.claude/commands/`: `/sprint-plan`,
`/sprint-execute`, `/sprint-qa`, `/sprint-retro`. ("Sprint" is just the command
name; use whatever cadence suits you.)

## 1. Layout

Each iteration owns a directory:

```
docs/sprints/<NN>-<name>/
  plan.md    # goal, committed stories, risks, out-of-scope, scope-changes log
  state.md   # append-only living memory: what closed, decisions to honor, blockers
  qa.md      # the QA pass output (verification, acceptance audit, findings)
  retro.md   # the retrospective
```

`state.md` is the memory the next story loads. It is append-only continuity
bookkeeping, and it plus `docs/reviews/` logs are gate-light: a change to them
runs mechanical checks only (doc style, links), not the full persona doc gate.
`plan.md`, `qa.md`, and `retro.md` are substantive and stay fully gated.

## 2. Plan (`/sprint-plan`)

Open the iteration: one-sentence goal, a small committed set of stories pulled
from the backlog and the last retro's proposal in priority order, each meeting
the Definition of Ready (02-governance.md). Write `plan.md` with the goal, the
committed-stories table, risks, explicit out-of-scope, and open the
scope-changes living record. Note each story's expected build effort up front.

## 3. Execute (`/sprint-execute`)

Drive the committed stories through the lifecycle (01-lifecycle.md) one at a
time. The driver orchestrates and holds merge judgment; it does not generate.
When a story's build is dispatched to a separate agent or model, fixes for
review findings go back to that same constructor, never the driver - the
reviewer and the author stay separate. Each story: load its minimal context
bundle, run docs-first (doc gate first when the KB changes, then code + tests in
the same PR), pass the local gates (`/review-gate`), open the PR, drive to green
through review, append the story's `state.md` summary as the final pre-merge
commit, then squash-merge. Reset the session before the next story enters. A
story bigger than one PR splits into PRs that each leave the default branch
releasable.

Standing rules: scope changes are visible (a line in `plan.md`'s scope-changes
record with the reason); process fixes do not wait for the retro (fix a
misfiring gate the moment it blocks work).

## 4. QA (`/sprint-qa`)

The front half of the retro, run as its own pass: full verification (the whole
test estate, counts and coverage against floors), a story acceptance audit
(criteria, not memory, against the merged default branch), and a time-boxed bug
hunt over the riskiest merged code. Write `qa.md`. The retro consumes it instead
of re-deriving the evidence.

## 5. Retro (`/sprint-retro`)

The honest close-out: scope check, verification (from `qa.md`), acceptance
audit, bug hunt, doc drift, architecture drift, tech-debt census, an AI/process
review that ships at least one improvement or records "none needed", a health
scorecard and short executive summary, then file every non-trivial finding as a
prioritised issue, regenerate the snapshot, and propose the next iteration.

The retro is honest or it is useless: failed steps recorded as failed, skipped
steps as skipped with the reason. A retro that only ever finds "all green" is
itself a finding.
