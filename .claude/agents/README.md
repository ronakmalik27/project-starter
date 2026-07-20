# Example subagents

These are example Claude Code subagents - specialized agents dispatched with
their own tools, model, and system prompt. Claude Code auto-dispatches one by
its `description`, or you invoke it explicitly. They are examples and templates:
keep the ones that fit, edit the personas and models, delete the rest.

If your agent harness is not Claude Code, treat these as the reference pattern
and port them to your tool's equivalent (Codex, Gemini, and others each have
their own subagent or profile mechanism). The instructions themselves are plain
Markdown.

## What is here

| Agent | Role | Tools | Model |
|---|---|---|---|
| [codebase-explorer.md](codebase-explorer.md) | Read-only search and orientation; returns conclusions, not file dumps | read-only | haiku (cheap) |
| [doc-reviewer.md](doc-reviewer.md) | One persona of the doc review gate | read-only | sonnet |
| [code-reviewer.md](code-reviewer.md) | One persona of the code review gate | read-only + tests | sonnet |
| [doc-author.md](doc-author.md) | Refine-or-create a single doc (the constructor) | read + write docs | sonnet |

## How they map to the workflow

- **Explore before you act.** Dispatch `codebase-explorer` to locate things
  without spending a capable model's context on search. This is the
  cheapest-sufficient rule (AGENTS.md section 5) made concrete: cheap model,
  read-only, frugal output.
- **Review is multi-persona.** The gates in
  `docs/process/06-review-guidelines.md` ask for one reviewer per persona the
  change touches. Dispatch several `doc-reviewer` or `code-reviewer` instances
  in parallel, one per persona, and let the driving session reconcile their
  findings.
- **Author and reviewer stay separate.** `doc-author` (and, for code, whatever
  constructor built the change) drafts; the reviewer agents and the driving
  session judge. Fixes for review findings go back to the constructor, never to
  the reviewer - that independence is the point of the gate (see
  `.claude/commands/sprint-execute.md`).

## Model choices

Models are set with stable aliases (`haiku`, `sonnet`, `opus`) so they track the
current generation. Routing follows cheapest-sufficient: read-only search runs
on the cheap model; review and authoring run on a mid model. Escalate a
high-stakes review (money path, security, hard to reverse) by setting the
agent's `model` to `opus`, or have the reviewer flag it and re-run at higher
effort.

## Make it yours

1. Rename personas and adjust the reviewer prompts to your domain (add a Data
   Engineer, a Mobile lead, whatever your stack needs).
2. Set `model` per your budget and the task's stakes.
3. Keep authoring and reviewing in separate agents. Do not give a reviewer write
   access to the code it reviews.
4. Anything that should apply to ALL agents (not just one subagent) belongs in
   `AGENTS.md`, not here.
