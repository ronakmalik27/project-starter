# Engineering principles

These principles apply to every doc in this directory and every change made
in this repository, regardless of language or stack. When a rule elsewhere
in docs/process conflicts with a principle here, fix the rule, not the
principle.

## 1. At or above industry standard

Every significant design choice names the established practice it matches or
beats. If you are designing a payments API, say which provider's API shape
you are following. If you are designing a review flow, say whose branch
protection model you are borrowing. Naming the reference forces a real
comparison instead of a guess.

A choice that falls below the industry standard is allowed, but only with a
written justification at the point where the choice is made: what the
standard practice is, why this project departs from it, and what the cost
of matching it would have been. Silence is not a justification.

## 2. Docs-first

Requirements and design exist before implementation starts. A feature's
behavior, data shape, and interfaces are written down before code is
written against them. This is not bureaucracy for its own sake: it means
reviewers can catch a bad design before it is expensive to change, and it
means the codebase has a source of truth that outlives any one
contributor's memory.

## 3. Small, reversible steps

Work is broken into steps small enough to review in one sitting. Every
merge to the default branch leaves it in a releasable state: no merge
depends on a second merge landing before the branch is safe to deploy.
Prefer several small reversible merges over one large one.

## 4. Parallelize independent work

When two pieces of work do not depend on each other, do them at the same
time rather than in sequence. This applies to tool calls, to review
streams, to documentation and implementation happening in parallel where
the design is already settled, and to running independent checks
concurrently in CI. A final integration pass is responsible for
reconciling anything that touched the same surface.

## 5. Cheapest-sufficient tooling

When two options produce a similar outcome, pick the cheaper one. This
applies to CI minutes (do not run a slow suite when a fast one gives the
same signal) and to model or tool choice when using AI assistance (do not
reach for the most expensive model when a cheaper one is sufficient for the
task's risk and complexity). Cheapest-sufficient is a default, not a ceiling:
money-path and security-sensitive work justifies spending more.

## 6. Everything rides a pull request

No direct pushes to the default branch, ever, including for the maintainer.
Every change, docs or code, goes through a pull request and the gates
described in 01-lifecycle.md and 06-review-guidelines.md. This is what makes
review, CI, and audit history actually mean something.

## 7. Honest reporting

A failing test is reported as failing, not worked around or hidden. A
skipped step is named as skipped, with the reason. Status reports (to
teammates, to the maintainer, to a reviewer) describe what actually
happened, including partial failures and open risks. Optimistic rounding of
status is a bug, not a courtesy.
