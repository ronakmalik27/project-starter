# /sprint-retro - run the iteration retrospective

Run the retrospective for the closing iteration and write
`docs/sprints/<NN>-<name>/retro.md`. See the iteration cycle
(docs/process/08-iteration-cycle.md). `$ARGUMENTS` may name the iteration; the
default is the open one.

Start a fresh context. Load the iteration's plan.md, state.md, and qa.md (if
`/sprint-qa` ran) first, then the sources each step needs as it runs. "Fresh
context" bans replaying old conversation, not reading the evidence each step
requires.

Run the steps in order; each produces a section of retro.md:

1. Scope check. Every planned story closed, or explicitly carried with a reason.
2. Full verification. The whole test estate locally, suite counts and coverage
   against floors. (If `/sprint-qa` produced qa.md, read it here instead of
   re-running.) A suite that cannot run is an environment-parity failure at bug
   priority, not a silent pass.
3. Story acceptance audit. Re-check each closed story against the merged default
   branch - criteria, not memory. Acceptance gaps become requirement-gap issues.
4. Bug hunt. The riskiest merged code, critical paths first; new defects become
   bug issues, anything that broke prior behavior a regression issue.
5. Doc drift scan. Where do the docs no longer match what shipped?
6. Architecture drift review. Where did the implementation diverge from the
   design? Steps 5-6 together are the design-vs-implementation drift pass.
7. Tech-debt census. TODOs without issues, deferred review Lows, coverage-floor
   gaps, open bot findings, aging dependency PRs; each becomes a debt issue.
8. AI/process review. What the agents (or you) got wrong, slow, or needlessly
   manual; which review seats caught what (keep-or-drop). Ship at least one
   process improvement, or record "none needed" with the reason.
9. Health scorecard + a short executive summary (a handful of lines).
10. File and prioritize. Every non-trivial finding becomes a labelled issue in
    priority order (critical bugs, security, regressions, bugs, requirement
    gaps, tech debt, next-iteration candidates). Trivial fixes may ride the
    retro PR, marked as such.
11. Repository snapshot. Regenerate docs/snapshot.md.
12. Next-iteration proposal. Goal plus candidate stories, then run /sprint-plan.

The retro is honest or it is useless: failed steps recorded as failed, skipped
steps as skipped with the reason. A retro that only ever finds "all green" is
itself a finding.
