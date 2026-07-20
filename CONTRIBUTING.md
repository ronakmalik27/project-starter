# Contributing

Every change - docs or code - travels the same path. The gates are described in
full in [docs/process/](docs/process/README.md); this is the short version.

## The path

1. **Branch.** No direct pushes to the default branch. Work on a branch and open
   a PR. (`make install-hooks` blocks direct pushes locally; the ruleset blocks
   them server-side.)
2. **Docs first.** If the change touches behaviour, update the relevant `docs/`
   first, in the same PR (see docs/adr/0001-docs-first-development.md).
3. **Meet the Definition of Ready** before starting, and the Definition of Done
   before merging (docs/process/02-governance.md).
4. **Local gate before pushing.** Run `make verify` (mechanical checks) and
   `/review-gate` (the persona review loop) until zero Critical/High/Medium
   findings remain.
5. **Open the PR** using the template. CI runs hygiene, a secrets scan, and
   build/test. Independent bot reviewers review the diff.
6. **Resolve every review thread** - fixed, or declined with a reason - and get
   a genuine blocking-reviewer pass on the final commit.
7. **Final gate before merging.** Run `/pre-merge-gate`, then squash-merge.

## Commit messages

- Conventional-commit subjects (`feat:`, `fix:`, `docs:`, `chore:`, ...).
- If an AI model wrote or co-wrote a commit, add a
  `Co-Authored-By: <Model> <noreply@provider>` trailer for each model, and name
  the models in the PR body.
- The squash commit is the exception: a clean conventional subject with the PR
  number and at most `Closes #N`, no trailers (see
  docs/process/06-review-guidelines.md section 8).

## Style

Docs follow docs/process/05-documentation-standards.md; `make hygiene` enforces
the character rules. Code follows docs/process/03-coding-standards.md and the
formatter/linter for its language. Never commit a secret - see the security doc
and the gitleaks backstop.
