# /doc-gate - run the documentation review gate

Run the doc review gate (docs/process/06-review-guidelines.md) on the docs
changed in the working tree (or the docs named in $ARGUMENTS).

1. Determine scope: `git diff --name-only main` (or $ARGUMENTS) filtered to
   `docs/`, `README.md`, the agent-contract files (`AGENTS.md`, `CLAUDE.md`,
   `GEMINI.md`, `.github/copilot-instructions.md`), and any API spec files.
   Gate-light (mechanical checks only, no persona review): `docs/reviews/` logs,
   `docs/reference/` frozen drafts, `docs/sprints/*/state.md`, and
   `docs/snapshot.md`. Substantive docs stay gated.
2. Select personas from the review-guidelines gate table for every touched doc.
3. Launch persona review agents (parallel where scopes are disjoint). Each
   reviews its docs IN FULL: internal correctness, cross-doc consistency (walk
   references in both directions), missed scenarios, the industry-standard bar,
   and writing-style compliance.
4. Fix all Critical/High/Medium findings, then RE-REVIEW the changed docs in
   full (never delta-only). Iterate until zero C/H/M remain.
5. Lows: fix trivial ones immediately; list the rest for the maintainer as
   fix-or-defer with effort estimates.
6. Record findings + resolutions in `docs/reviews/YYYY-MM-DD-<scope>.md`, run
   `python3 scripts/check_doc_style.py`, and only then allow the push.
