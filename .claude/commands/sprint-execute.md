# /sprint-execute - work the open iteration

Drive the open iteration's committed stories through the development lifecycle
(docs/process/01-lifecycle.md) one at a time, until the committed scope is
closed or you call it. `$ARGUMENTS` may name a single issue to execute just
that story; the default is to work the whole committed set in priority order.

The driver orchestrates and holds merge judgment; it does not generate. When a
story's build is dispatched to a subagent (or a separate model), fixes for
review findings go back to that same constructor - never authored by the
driving session, however small the fix looks. This keeps the reviewer and the
author separate, which is the point of the gate.

Run the loop; each pass takes one story from Todo to Done and freezes it in
`state.md`.

1. Load the iteration. Read plan.md (committed stories, the scope-changes
   record) and state.md (stories done, decisions later stories must honor, open
   risks, blockers) as the entry context - do not replay prior conversation.
2. Pick the next ready story: committed, Todo, DoR-met, unblocked, its
   dependency stories closed. Reserve it (move it to In Progress) before any
   work starts. If none is ready, stop and report the blocker.
3. Load the story's context bundle: the docs it cites, the code it touches, and
   the state.md decisions it must honor - the minimum, expanded deliberately,
   never a full-repo rescan.
4. Run the lifecycle, docs-first: the docs-delta stage first when the knowledge
   base must change (run the doc gate), then implementation with its tests in
   the same PR. A story larger than one PR splits into PRs that each leave the
   default branch releasable; run steps 4-7 once per PR.
5. Local quality gates: the affected suites, the formatter/linter, the doc
   style and link checks for doc changes, then the `/review-gate` persona loop
   over the outgoing diff. Zero Critical/High/Medium findings before the PR
   opens.
6. Open the PR with the checklist filled in; request the bot reviews. Drive to
   green: address findings (dispatch fixes back to the story's constructor),
   re-request the bots after each fix push, then `/pre-merge-gate` + CI green +
   every finding resolved.
7. On the PR that closes the story, append its state.md summary (outcome,
   decisions, changed, tests, docs, lessons, follow-ups) as the final pre-merge
   commit, so the state change rides the same PR. Then squash-merge.
8. Close the story: file any follow-up issues, move the card to Done, and reset
   the session before the next story enters - the reset is a step of closing a
   story, not a habit left to memory. state.md is the living memory the next
   story loads.
9. Standing rules. Scope changes are visible: a story added or dropped
   mid-iteration gets a line in plan.md's scope-changes record with the reason.
   Process fixes do not wait for the retro: fix a misfiring gate the moment it
   blocks work, and note it for the retro.
10. Loop or stop. Return to step 2. Stop when the committed scope is closed
    (recommend `/sprint-retro`), or a blocker needs a decision you cannot make
    alone. Never silently drop a committed story: carry it with a reason.
