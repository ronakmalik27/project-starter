# Onboarding

Your first hour with this template, in order. It is the guided path; the
[README](README.md) is the full tour and `AGENTS.md` is the contract. If you are
an AI agent, read `AGENTS.md` first, then this.

## What you are looking at

A docs-first, review-gated, AI-assisted project template. The `docs/` knowledge
base is the source of truth; code implements it. Nothing here is stack-specific
until you wire two Makefile targets. You will either be starting a brand-new
project from this, or joining one already built on it.

## If you are STARTING a new project from the template

1. **Read `AGENTS.md` in full.** It is the operating contract every tool and
   teammate follows: the working principles, the gates, and the one rule that
   drives everything - for each knowledge-base doc, refine it if it exists, else
   create it from the skeleton.
2. **Make the repo yours.** Work the checklist in the README's "Make it yours"
   section: set `LICENSE` and `.github/CODEOWNERS`, run `make install-hooks`
   (the pre-push backstop) and `make apply-ruleset` (server-side branch
   protection), wire `ci-build` / `ci-test` in the `Makefile` for your stack,
   and install the review bots you want (a blocking one, optionally an advisory
   one - see `docs/process/06-review-guidelines.md`).
3. **Pick your starting point** (see the README's "Two ways to start"). If you
   already have material (problem statement, research, MVP specs, tech/brand
   decisions), map each into the matching `docs/` file and refine it. If you have
   only an idea, create each doc from its skeleton. Either way, work front to
   back starting at `docs/00-vision.md`; never let a downstream doc run ahead of
   the upstream one it depends on.

## If you are JOINING a project already on the template

1. **Read `AGENTS.md`, then `docs/process/README.md` and
   `docs/process/00-principles.md`.** That is how work is done here.
2. **Skim the filled-in `docs/`** front to back for the feature you are touching:
   its requirements and design exist before its code, by rule.
3. **Find the current iteration** in `docs/sprints/` (its `plan.md` and
   `state.md`) to see what is in flight.

## The loop you will run every day

- **Docs first, same PR.** A change to behavior, data, interfaces, or process
  updates the doc that describes it in the same PR (or one that lands first).
- **Everything rides a PR.** No direct pushes to the default branch; the ruleset
  and the pre-push hook enforce it. Squash merges, linear history.
- **Two local gates.** Run `/review-gate` before every push and
  `/pre-merge-gate` before every merge - a persona review loop that iterates to
  zero Critical/High/Medium findings. Run `/doc-gate` on any docs change.
- **Independent reviewers.** A blocking bot review must pass on the final commit;
  an advisory one adds signal. Full protocol in
  `docs/process/06-review-guidelines.md`.
- **Iterations.** `/sprint-plan` opens one, `/sprint-execute` works it one story
  at a time, `/sprint-qa` then `/sprint-retro` close it. See
  `docs/process/08-iteration-cycle.md`.

The gates and iteration steps live in `.claude/commands/` as plain-Markdown
commands; if your agent harness is not Claude Code, perform the same loop by
hand.

## If you are an AI agent

- `AGENTS.md` is your contract; the per-tool files (`CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`) are thin pointers to it.
- Route to the cheapest model and effort that will do the task well; reserve the
  expensive models for hard reasoning and high-stakes changes.
- Keep author and reviewer separate. `.claude/agents/` has example subagents (a
  read-only explorer, per-persona reviewers, a doc author) that make both habits
  concrete; port the pattern to your tool if needed.

## Next

Open the [README](README.md) for the full layout and the workflow at a glance,
then `docs/process/README.md` for the playbook.
