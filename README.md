# project-starter

A batteries-included starting point for docs-first, review-gated,
AI-assisted software projects. It is the reusable "how we work" layer - the
engineering workflow, the review gates, the CI scaffolding, and the AI-agent
commands - with empty skeletons for the project-specific "what we are building"
layer.

Use it as a GitHub template repository ("Use this template"), or copy the parts
you want. Nothing here is stack-specific: it drives .NET, Node, Flutter, Python,
or anything else once you fill in two Makefile targets.

## What is inside

```
.claude/commands/     AI-agent commands: the review + iteration workflow, executable
.github/              CI (pr-gate, merge-gate, cd stub, secrets sweep), templates, ruleset
docs/
  process/            The reusable workflow: principles, lifecycle, governance,
                      coding/testing/doc standards, review guidelines, iteration cycle
  adr/                Architecture Decision Records: a template + a worked example
  01-14 *.md          Project-doc skeletons (PRD, SRS, UX, HLD, security, ...) to fill in
  reviews/            Review logs (gate-light, bot-excluded)
  sprints/            One directory per iteration (plan/state/qa/retro)
scripts/              Doc style + link checkers, git hooks
Makefile              Developer entrypoints; `make` lists them
```

## Make it yours

A short checklist after creating a repo from this template:

1. `LICENSE` - replace `<your name>` with the copyright holder.
2. `.github/CODEOWNERS` - replace `@your-username`.
3. `make install-hooks` - install the pre-push backstop (blocks direct pushes
   to the default branch, runs the hygiene gate).
4. `make apply-ruleset` - apply server-side branch protection (needs `gh` and
   admin on the repo). Requires a plan that supports rulesets on the repo's
   visibility.
5. Wire `ci-build` and `ci-test` in the `Makefile` for your stack, and add the
   matching toolchain setup step in `.github/workflows/pr-gate.yml`.
6. Install the review bots you want on the repo: a blocking reviewer
   (this template is pre-wired for CodeRabbit via `.coderabbit.yaml`) and,
   optionally, an advisory one (Gemini via `.gemini/config.yaml`). See
   docs/process/06-review-guidelines.md.
7. Fill in the `docs/` skeletons for your project, deleting the ones you do not
   need. Start with `docs/01-prd.md`.
8. Delete this section and rewrite the top of this README for your project.

## The workflow at a glance

- **Docs first.** Requirements and design live in `docs/` before the code that
  implements them (ADR-0001).
- **Everything rides a PR.** No direct pushes to the default branch; the ruleset
  and pre-push hook enforce it. Squash merges, linear history.
- **Two local gates.** `/review-gate` before every push, `/pre-merge-gate`
  before every merge - a persona review loop that iterates to zero
  Critical/High/Medium findings.
- **Independent reviewers.** A blocking bot review must pass on the final commit;
  an advisory one adds signal. Full protocol in
  docs/process/06-review-guidelines.md.
- **Iterations.** Plan, execute one story at a time, QA, retro - see
  docs/process/08-iteration-cycle.md.

Start with docs/process/README.md, then docs/process/00-principles.md.

## AI-agent commands

`.claude/commands/` holds the workflow as commands an AI coding agent can run:

| Command | What it does |
|---|---|
| `/review-gate` | Full persona review loop over the outgoing diff, before a push |
| `/pre-merge-gate` | Final review over the PR's cumulative diff + dependency closure |
| `/doc-gate` | The documentation review gate |
| `/batch-commits` | Consolidate related local commits before pushing |
| `/sprint-plan` | Open the next iteration |
| `/sprint-execute` | Work the open iteration, one story at a time |
| `/sprint-qa` | The iteration-end QA pass |
| `/sprint-retro` | The iteration retrospective |

They are plain Markdown - portable to whichever agent harness you use.

## License

MIT. See [LICENSE](LICENSE).
