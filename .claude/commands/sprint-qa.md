# /sprint-qa - run the iteration-end QA pass

Run the QA pass (full verification, story acceptance audit, bug hunt) as its
own executable step, before and as the front half of `/sprint-retro`, and write
`docs/sprints/<NN>-<name>/qa.md`. `$ARGUMENTS` may name the iteration; the
default is the open one.

Start a fresh context: load plan.md and state.md and the closed stories'
acceptance criteria as the entry context, then the default branch as merged.

1. Full verification. Run the whole test estate (every suite, including
   integration and any golden/UI tests). Record suite-by-suite counts, results,
   and coverage against your floors in a table. A suite that cannot run
   (missing toolchain) is an environment-parity failure at bug priority, not a
   silent pass - record it as failed with the reason and file the restore issue.
2. Story acceptance audit. For each closed story, re-check its acceptance
   criteria against the default branch as merged - criteria, not memory. Record
   a PASS / FAIL verdict per story. Critical-path stories (anything that moves
   value or must not corrupt data) are never sampled out.
3. Bug hunt. A focused, time-boxed review of the iteration's riskiest merged
   code: critical paths first, then concurrency, then anything flagged "ship
   with watch" in a prior review. Record findings with evidence, severity, and
   a disposition. Do not file issues here - the retro's filing step owns that,
   so filing stays in one place.
4. Write qa.md: the verification table, the acceptance audit, the findings, and
   a link back to the iteration. This is the artifact `/sprint-retro` consumes
   instead of re-deriving the same evidence.

The pass is honest or it is useless: a step that could not run is recorded as
failed or blocked with the reason, never silently skipped. A QA pass that only
ever finds "all green" is itself a finding.
