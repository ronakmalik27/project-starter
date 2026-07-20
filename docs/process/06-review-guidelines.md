# 06 - Review guidelines

Review is the load-bearing quality gate in this workflow. Nothing reaches the
default branch without passing it. There are three parts: the local persona
review (you, or your AI agents, acting as reviewers before a push and before a
merge), the doc review gate (the same idea, specialised for documentation), and
the external third-party reviewer protocol (independent bot reviewers on the
PR). All three use the one severity rubric in section 3.

The executable form of the local gates lives in `.claude/commands/`:
`/review-gate` (before every push), `/pre-merge-gate` (before every merge),
`/doc-gate` (the doc review gate). This doc is the policy those commands run.

## 1. The two local gates

- **Before every push: `/review-gate`.** A persona review over the whole
  outgoing diff (docs and code): review, fix, full re-review, iterate until
  zero Critical/High/Medium findings remain and quick-win Lows are done.
- **Before every merge: `/pre-merge-gate`.** The final check over the PR's full
  cumulative diff plus its dependency closure (the files that reference the
  changed files). Merge only on a clean pass.

No direct pushes to the default branch: everything rides a PR. Enforce this
server-side with the saved ruleset (`.github/rulesets/main-protection.json`,
applied with `make apply-ruleset`) and, as a local backstop, a pre-push hook.

## 2. Reviewer hats by area

Pick reviewers by what the change touches - at least one, ideally every hat the
change's scope covers. "Hat" means a review lens; solo, you wear them in turn,
or you dispatch each to a focused agent.

| Area touched | Reviewer hats |
|---|---|
| Requirements / product docs | Product + the domain owner |
| Architecture / design docs / ADRs | Architect + Engineering lead |
| API specs | Software Engineer + Architect |
| Data model / schema | Data Engineer + Software Engineer |
| Backend code | Software Engineer + Architect |
| Critical-path code (value-moving, must-not-corrupt) | add QA (property tests) + verify the invariants explicitly |
| Auth / crypto / upload / any new external surface | add Security Engineer |
| Frontend / UI code | Frontend Engineer (design-token conformance) |
| CI / infra / `.github/` | DevOps/SRE |
| Docs process, this file | Engineering lead |

Each hat reviews the diff IN FULL with surrounding context (read the whole
touched file, not just the hunk): internal correctness, conformance to the
contracts the change cites, cross-file consistency, missed scenarios, the
industry-standard bar (see 00-principles.md), and test coverage per
07-testing-strategy.md.

## 3. Severity rubric

One rubric for every review in this repo. It grades *review findings* (do not
confuse it with production-incident or bug-priority scales, which are separate).

- **Critical**: value/data corruption, a security breach, a legal violation, or
  it makes the thing unbuildable as specified.
- **High**: a cross-doc or cross-module contradiction, an invariant violation,
  or a gap that blocks a core flow.
- **Medium**: an ambiguity or gap likely to cause rework or bugs if built as
  written.
- **Low**: polish and minor inconsistency.

**The gate**: do not push or merge while any Critical/High/Medium finding is
open. Fix it first, or record a maintainer-approved waiver in the review log.
Fix quick-win Lows too. Non-trivial Lows may be logged and deferred with a
reason.

## 4. Iterate to Low with FULL re-review

Fixing findings is itself a change. After applying fixes, re-review every
changed file IN FULL with its hats - never a delta check of the fixes alone.
Each re-review confirms both: (a) every prior finding is actually fixed, and
(b) the fixes introduced no new issue. Cross-file propagation is the classic
failure mode (a fix in one place invalidates text or code elsewhere), so walk
the changed thing's references in both directions. Repeat fix -> full re-review
until zero Critical/High/Medium remain.

## 5. The doc review gate

After any change to `docs/`, `README.md`, or an API spec, run `/doc-gate`
before pushing. It is blocking.

1. Pick reviewer hats by scope (section 2's table), at least one.
2. Each hat reviews IN FULL: internal correctness, cross-doc consistency (walk
   references both ways), missed scenarios, the industry-standard bar, and
   writing-style compliance (05-documentation-standards.md).
3. Apply the section 3 rubric and the section 4 iterate-to-Low loop.
4. Record findings and resolutions in `docs/reviews/YYYY-MM-DD-<scope>.md`, run
   `make hygiene`, and only then push.

Records are exempt from the gate (they are gate-light, mechanical checks only):
`docs/reviews/` logs and `docs/reference/` frozen drafts. They are also
bot-excluded (see `.coderabbit.yaml` / `.gemini/config.yaml`). Substantive docs
stay gated.

## 6. External third-party reviewers

Run at least one independent automated reviewer on every PR. This template is
pre-wired for two, in the industry-standard blocking + advisory split:

- **A blocking reviewer** (e.g. CodeRabbit): its review must complete on the
  final commit before merge. It auto-reviews each push.
- **An advisory reviewer** (e.g. Gemini Code Assist): useful signal, never
  blocks a merge.

Protocol:

- Read the whole review, not just the inline threads: out-of-diff and nitpick
  findings often sit in the review body. Reason about each. Fix the necessary
  and quick-win ones; decline the rest with a stated reason. ALWAYS resolve
  every thread before merge (fixed or declined).
- A green check is not always a genuine review. A "rate limited" or "skipped"
  conclusion is not a review - never merge on it. Wait for a real one.
- Do not spam re-reviews. Re-request only after you push fixes. Back off a
  quota-exhausted reviewer instead of retrying. A sensible per-PR cap for the
  advisory reviewer scales with scope (roughly: 1-2 files -> up to 2 requests,
  3-5 -> up to 3, 6+ -> up to 4); the blocking reviewer has no such cap.
- If the BLOCKING reviewer is down or unresponsive: paced retries, then a
  maintainer waiver recorded as a `docs/reviews/` WAIVED entry. Never merge
  past a missing blocking review without that record. The advisory reviewer
  never needs a waiver.

## 7. The merge gate

Merge (squash only) when ALL hold on the exact commit you are merging:

- CI is green.
- The blocking reviewer's review completed and is genuine on the final HEAD
  (not rate-limited, paused, or superseded by a later push).
- Zero unresolved review threads from any reviewer (each fixed or declined per
  section 3).
- The PR is mergeable and its merge state is clean.

A new commit invalidates a prior approval: always merge the exact reviewed
HEAD. Human approval is per-project policy; a solo maintainer may set the
required approval count to zero and rely on the gates above (that is how the
ruleset ships).

## 8. Commit and squash conventions

- Every commit (first and follow-ups) that an AI model wrote or co-wrote
  carries a `Co-Authored-By: <Model> <noreply@provider>` trailer for each model
  involved, and the PR body names the models used.
- The squash commit is the exception: a concise conventional-commit subject
  with the PR number, plus at most `Closes #N`, and NO trailers (a squash would
  otherwise fold every commit's trailers into the default branch's history).
