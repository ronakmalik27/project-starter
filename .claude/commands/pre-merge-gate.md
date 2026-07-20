# /pre-merge-gate - final check before merging any PR

(Named to avoid collision with any CI stage called "merge": that is the
post-merge pipeline on the default branch.)

The last gate before the default branch. Scope: the PR's FULL cumulative diff
vs main (all commits, docs and code) PLUS its dependency closure.

1. Build the dependency closure of the changed files:
   - Docs: every doc that references a changed doc's sections / requirement
     ids / tables (grep the changed section numbers and ids across `docs/`).
     Cross-doc propagation is the classic failure mode.
   - Code: files importing or using the changed modules (project references,
     using directives, imports); tests covering the changed paths; the API
     entries and doc rows the code claims to satisfy.
2. Run the /review-gate persona review over the diff AND spot-check the closure
   files for statements the change just invalidated.
3. Verify PR hygiene: the PR checklist boxes are honestly checked, CI is green,
   and findings from earlier review rounds are all resolved (no open C/H/M
   conversation).
3a. External reviewers: if you pushed fixes for a bot reviewer's findings,
   re-request its review per the review guidelines, then WAIT for the
   re-review of the new commits. Reply to every fixed thread and resolve it.
   Decline taste-only suggestions with a reason, then resolve them. No
   unresolved thread at merge time.
4. Iterate fix -> full re-review to zero C/H/M plus quick-win Lows, exactly
   like /review-gate.
5. Only then merge (squash). Record doc reviews per the doc gate; summarize
   code findings in a PR comment before merging.
