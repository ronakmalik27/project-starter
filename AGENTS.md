# Agent operating contract

This is the single source of truth for how any AI agent works in this repo.
Read it in full before doing anything. It is tool-agnostic on purpose: Codex,
Claude Code, Gemini CLI, Antigravity, Cursor, and GitHub Copilot all read this
file (directly, or via the thin pointer files described in section 8). Anything
that should apply to every agent belongs HERE, never copied into a per-tool file.

## 1. How to use this repo - two starting points, one rule

This is a docs-first project: the knowledge base in `docs/` is the source of
truth, and code implements it. You will arrive in one of two states, and the
rule is the same either way:

> For each knowledge-base document: if the project already has it, REFINE it
> against this repo's section outline and current industry standards (and any
> reference implementation you have been pointed at); if it does not exist yet,
> CREATE it from the starter skeleton.

- **Flow A - you already have material** (a problem statement, market
  opportunity, target users, a research or MVP-finalization report, MVP specs,
  brand decisions, tech-stack decisions, ...): map each into the matching doc
  and refine it. Do not discard existing content; reconcile it with the outline,
  fill gaps, and raise contradictions.
- **Flow B - you have only an idea**: create each doc from its skeleton, front
  to back, starting with `docs/00-vision.md`.

Either way, work front to back: vision -> discovery -> requirements -> design ->
implementation, and never let a downstream doc get ahead of the upstream one it
depends on.

## 2. Working principles

- **At or above industry standard.** Every significant choice names the
  established practice it matches or beats; a below-par choice is justified in
  writing where it is made.
- **Docs-first.** Requirements and design exist before the code that implements
  them.
- **Small, reversible steps.** Every merge leaves the default branch releasable.
- **Parallelize** independent work; a final integration pass reconciles it.
- **Cheapest-sufficient tooling.** When outcomes are similar, pick the cheaper
  option - including which AI model/effort you use (see section 5).
- **Everything rides a pull request.** No direct pushes to the default branch.
- **Honest reporting.** Failing tests are reported as failing; skipped steps are
  named. Never round status up.

Full detail: `docs/process/00-principles.md`.

## 3. The gates (do not skip)

- **Before every push:** run the `/review-gate` loop (`.claude/commands/`) over
  the outgoing diff - review, fix, full re-review, to zero Critical/High/Medium
  findings.
- **Before every merge:** run `/pre-merge-gate` over the PR's cumulative diff
  plus its dependency closure.
- **Docs:** run `/doc-gate` on any change to `docs/`, `README.md`, or an API
  spec before pushing.
- Independent bot reviewers review each PR (a blocking one and an advisory one).

The gates and severity rubric live in `docs/process/06-review-guidelines.md`.
If your tool has no slash-command runner, perform the same loop by hand.

## 4. The development lifecycle

Idea -> requirements/design doc delta -> doc gate -> implementation with tests
in the same PR -> local quality gates -> PR and review -> merge -> release.
Work in iterations (`/sprint-plan`, `/sprint-execute`, `/sprint-qa`,
`/sprint-retro`). Full detail: `docs/process/01-lifecycle.md` and
`08-iteration-cycle.md`.

## 5. AI-assisted development

- **Route to the cheapest model and effort that will do the task well.**
  Reserve the most capable/expensive models for hard reasoning, ambiguous
  design, or high-stakes changes. Money-path, security, and hard-to-reverse work
  justify spending more; routine edits do not.
- **Manage context deliberately.** Load the minimum a task needs (its docs, the
  code it touches, the decisions it must honor); expand on purpose, do not replay
  whole histories or rescan the repo.
- **Parallelize** independent subtasks (dispatch subagents/tools concurrently);
  a final pass owns cross-cutting coherence.
- **Review every AI-generated change** through the same gates as human-written
  code. AI output is a draft until it passes review.
- **Authorship:** every commit an AI wrote or co-wrote carries a
  `Co-Authored-By: <Model> <noreply@provider>` trailer for each model, and the
  PR body names the models used.
- **Data boundaries:** never feed a secret, credential, or regulated/sensitive
  data to a model or service that is not cleared for it. When in doubt, do not.

## 6. Documentation sync (this is load-bearing)

The knowledge base is one connected system, not a pile of files. Keep it in sync:

- **Docs-first, same PR.** A change to behavior, data, interfaces, or process
  updates the doc that describes it in the same PR (or a PR that lands first).
  Code must never contradict the docs it implements - that is a bug, not drift.
- **Walk references both ways.** When you edit a doc, follow what it links to and
  what links to it, and fix both sides. Cross-doc drift is the most common review
  finding.
- **Record decisions.** Significant or hard-to-reverse choices (tech stack,
  data model, brand) become ADRs (`docs/adr/`, see
  `docs/process/09-decision-framework.md`), not buried prose.
- **Agent files stay thin.** Common instructions live here in AGENTS.md. The
  per-tool files (section 8) carry only tool-specific notes. If you find yourself
  about to add a shared rule to `CLAUDE.md` / `GEMINI.md` / `copilot-instructions.md`,
  put it here instead.

## 7. Secrets

Never write a secret (API key, token, password, credentialed connection string,
private key) anywhere in the repo - code, config, commits, PR/issue bodies,
comments, or logs. Secrets live in a local secret store in development and a
managed secret store in production. A secret that lands anywhere it should not
(including pasted into a chat) is compromised: do not echo it, and rotate it.

## 8. Where instructions live (and the sync rule)

- **AGENTS.md** (this file) - the canonical contract every agent follows.
- **CLAUDE.md** - Claude Code: pointer to this file + Claude-specific notes.
- **GEMINI.md** - Gemini CLI and Antigravity: pointer + notes (Antigravity treats
  GEMINI.md as highest priority and applies AGENTS.md after it, so GEMINI.md
  defers here for everything common).
- **.github/copilot-instructions.md** - VS Code / GitHub Copilot: pointer + notes.

The per-tool files are deliberately short. The rule: **any change meant for all
agents goes in AGENTS.md; a per-tool file only ever holds notes specific to that
tool.** That is what keeps them from drifting.

## 9. Where things live

- `docs/process/` - how we work (principles, lifecycle, governance, standards,
  review, testing, iteration, decisions).
- `docs/00-vision.md`, `docs/00-discovery.md`, `docs/01-*` .. `docs/15-brand.md`
  - what we are building (fill in per section 1).
- `docs/adr/` - decision records (template + example).
- `.claude/commands/` - the gates and iteration loop as runnable commands.
- `.claude/agents/` - example subagents (read-only explorer, per-persona
  reviewers, a doc-author constructor) for tools that support them.
- Writing style for all docs: `docs/process/05-documentation-standards.md`.
