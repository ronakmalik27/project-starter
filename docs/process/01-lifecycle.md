# Development lifecycle

This is the path a piece of work travels, from idea to release. It applies
whether the work is a feature, a bug fix, or a documentation change.

## Stages

1. **Idea.** Someone identifies a need: a feature, a fix, a process change.
2. **Requirements or design doc delta.** If the change affects behavior,
   data, interfaces, or process, the relevant doc is updated first. Small
   fixes with no behavior change (typo, a comment, a dependency bump) can
   skip straight to implementation.
3. **Doc gate.** Any doc change runs through the doc gate before it is
   pushed. See 06-review-guidelines.md for the gate itself.
4. **Implementation with tests in the same pull request.** Code and its
   tests land together. A pull request that adds behavior without adding
   the tests that cover it is not ready for review.
5. **Local quality gates.** Linting, formatting, the local test suite, and
   the pre-push review loop (`/review-gate`) all run before the branch is
   pushed.
6. **Pull request and review.** The change goes up as a pull request. It
   picks up automated checks and reviewer feedback per
   06-review-guidelines.md.
7. **Merge.** Once the pull request passes every required gate
   (02-governance.md has the branch protection summary), it is merged with
   `/pre-merge-gate` as the final check.
8. **Release.** The merged change ships per the project's release process.
   Because every merge left the default branch releasable (see
   00-principles.md, principle 3), release is a formality, not a scramble.

## Rules

- **Docs change first when the knowledge base must change.** If a change
  alters what the system does, how it is built, or how the team works, the
  doc describing that thing is updated in the same pull request as the code,
  or in a pull request that lands first. Code should never contradict the
  docs it implements.
- **A story bigger than one pull request splits into a chain of pull
  requests, each of which leaves the default branch releasable.** Do not
  merge a partial, broken state and promise to finish it in a follow-up.
  Split the work so every merge point is safe to ship from.
- **Every pull request is independently reviewable.** A reviewer should be
  able to understand and evaluate one pull request without having to read
  three others first. If a pull request needs that much surrounding
  context, it is a sign the work was not split well.

## State flow

```
idea -> doc delta -> doc gate -> implementation + tests -> local gates -> PR + review -> merge -> release
```

Any stage can send work backward: a review finding sends a pull request back
to implementation; a doc gate finding sends a doc back to drafting. Moving
backward is normal and cheap when steps are small.
