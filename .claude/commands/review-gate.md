# /review-gate - full pre-push review loop (code + docs)

Run before EVERY push. Scope: the full diff vs origin/main (or $ARGUMENTS).

1. Mechanical checks first (fail fast, costs nothing):
   `python3 scripts/check_doc_style.py`; a YAML parse of any touched
   workflow/OpenAPI files; build + tests for the touched code areas.
2. Select reviewer hats by touched area (one persona minimum, ideally every
   one the change touches):
   - docs / README / api specs: the persona set in the doc review gate
     (docs/process/06-review-guidelines.md).
   - backend code: Software Engineer + Architect.
   - money or other critical-path code (ledgers, settlement, anything that
     moves value or must not corrupt data): add QA (property-test coverage)
     and verify the invariants that path documents explicitly.
   - auth / crypto / upload / any new external surface: add Security Engineer.
   - frontend / UI code: add Frontend Engineer (design-token conformance).
   - CI / infra / `.github/`: add DevOps/SRE.
3. Each hat reviews the diff IN FULL with surrounding context (read the whole
   touched file, not just the hunk): correctness, conformance to the contracts
   the change cites (API rows, schema, event catalogue), cross-file
   consistency, the industry-standard bar, and test coverage per the testing
   strategy.
4. Severity rubric (see review guidelines): fix ALL Critical/High/Medium plus
   quick-win Lows, then RE-REVIEW the changed files in full. Iterate until zero
   C/H/M remain and no quick-win Lows are left. Non-trivial Lows: list them for
   the maintainer as fix-or-defer.
5. Only then push. Summarize code findings (found and fixed) in the PR
   description; log doc reviews per the doc gate.
