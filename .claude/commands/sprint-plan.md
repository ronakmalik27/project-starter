# /sprint-plan - open the next iteration

Open the next iteration and write `docs/sprints/<NN>-<name>/plan.md`. See the
iteration cycle (docs/process/08-iteration-cycle.md). `$ARGUMENTS` may name the
goal.

Start a fresh context: load the last retro's next-iteration proposal and its
filed issues, the Definition of Ready (docs/process/02-governance.md), and the
current milestone. If `$ARGUMENTS` names a goal it refines the proposal, it
does not silently replace it. On the very first iteration there is no prior
retro: take the goal from `$ARGUMENTS` or `docs/00-vision.md` and pull the first
stories straight from the backlog.

1. Goal. One sentence: the single milestone outcome this iteration advances.
2. Select stories. Pull candidates from the backlog / last retro's issues in
   priority order. Verify each meets the Definition of Ready; a story that
   fails DoR goes back to refinement, not into the iteration.
3. Note each story's expected effort and (if you route across models) which
   model you will build it with - cheapest that will do the job well - so the
   iteration knows its cost shape up front.
4. Write plan.md: goal, committed-stories table (issue, what, DoR-met, build
   note), risks, explicit out-of-scope, and a decisions-recorded section. Open
   a scope-changes living record.
5. Name it (any stable naming scheme - a theme word, a sequence number).
6. Confirm the goal, then assign the committed issues on your tracker so the
   execute step has a queue.
