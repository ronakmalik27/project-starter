# Claude Code - project instructions

The canonical, cross-agent operating contract for this repo is
**[AGENTS.md](AGENTS.md)**. Read it in full and follow it before doing anything.
It is the source of truth for the workflow, the gates, the AI-assisted-development
rules, the docs-first + documentation-sync rules, and secrets handling.

## Sync rule

Keep this file thin. Anything meant for ALL agents goes in AGENTS.md, never
here - this file holds only Claude Code-specific notes.

## Claude Code-specific notes

- The gates and iteration loop are runnable slash commands in
  `.claude/commands/`: `/review-gate`, `/pre-merge-gate`, `/doc-gate`,
  `/batch-commits`, `/sprint-plan`, `/sprint-execute`, `/sprint-qa`,
  `/sprint-retro`.
- Parallelize with subagents where the work is independent (AGENTS.md section 5);
  a final pass owns cross-cutting coherence. `.claude/agents/` holds example
  subagents (a read-only explorer, per-persona reviewers, a doc-author
  constructor) with cheapest-sufficient model routing; see its README.
- Put durable, cross-session facts in memory; keep temporary files in the
  scratchpad, never in the repo.
