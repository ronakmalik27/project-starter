# Governance and decision authority

This doc covers when a story is ready to start, when it is done, who decides
what, and the branch protection rules that make those decisions stick.

## Definition of Ready

A story is ready to enter an iteration when all of the following hold:

- Acceptance criteria are written down and clear enough that a different
  person could implement against them.
- Any required doc delta is identified: which docs will need updating, even
  if the exact wording is not final.
- Dependencies are known: what this story needs from other work, and what
  other work needs from it.
- The story is roughly sized, so it can be scheduled sensibly against other
  work in the iteration.
- There is no unresolved blocker (an open question that would stop
  implementation cold).

A story that fails any of these stays out of the iteration until it is
fixed. Pulling in an unready story is how iterations slip.

## Definition of Done

A story is done when all of the following hold:

- Its change is merged to the default branch.
- Tests exist for the new or changed behavior and are green.
- Any doc affected by the change has been updated to match.
- Every gate in 01-lifecycle.md and 06-review-guidelines.md has passed.
- Follow-up work identified during implementation or review (things
  deliberately deferred) is filed as tracked work, not left as a comment
  that will be forgotten.

"Done" means shippable, not "done except for." A story that is merged but
not tested, or merged but leaves docs stale, is not done.

## Decision authority

- **Routine calls** (how to name a variable, which small library to pull in,
  how to phrase a doc section) belong to whoever is implementing the work.
  Do not escalate decisions that are cheap to reverse.
- **Significant or hard-to-reverse calls** (a change to the data model, a
  new external dependency the whole system will rely on, a shift in
  architecture) are recorded as Architecture Decision Records (ADRs). See
  09-decision-framework.md for when an ADR is required and how it moves
  through review.
- When a call is ambiguous, default to writing it down as at least a short
  ADR. A short record that turns out to be unnecessary costs little; a
  significant decision made silently costs a lot when someone later asks
  why.
- The maintainer (or, in a team, whoever holds final authority for the
  project) reviews at the document and milestone level, not by re-approving
  every individual pull request. Day-to-day merge decisions follow the gates
  in 06-review-guidelines.md, not a per-change sign-off from the maintainer.

## Branch protection summary

The default branch is protected so these rules are enforced by tooling, not
by memory:

- No direct pushes to the default branch. Every change rides a pull request.
- A pull request is required to merge, with required status checks green
  (see 07-testing-strategy.md and 06-review-guidelines.md for what those
  checks cover).
- Linear history is enforced: merges use squash, not merge commits, so the
  default branch reads as one commit per pull request.
- Review threads must be resolved before merge. An open, unresolved comment
  blocks the merge until it is addressed or explicitly declined with a
  reason.

Configure these as server-side rules where the hosting platform supports it,
so they hold even if a local hook is bypassed or missing.
