# Gemini CLI / Antigravity - project instructions

The canonical, cross-agent operating contract for this repo is
**[AGENTS.md](AGENTS.md)**. Read it in full and follow it. It is the source of
truth for the workflow, the gates, the AI-assisted-development rules, the
docs-first + documentation-sync rules, and secrets handling.

Antigravity treats GEMINI.md as its highest-priority rules file and applies
AGENTS.md after it, so this file deliberately defers to AGENTS.md for everything
common - the two never conflict.

## Sync rule

Keep this file thin. Anything meant for ALL agents goes in AGENTS.md, never
here - this file holds only Gemini CLI / Antigravity-specific notes.

## Gemini / Antigravity-specific notes

- AGENTS.md carries the full contract; do not restate it here.
- The gates and iteration loop live in `.claude/commands/` as Markdown; run the
  equivalent loop (review -> fix -> full re-review) even though the slash-command
  runner itself is Claude Code's.
- The `.gemini/config.yaml` at the repo root configures the Gemini Code Assist
  PR-review bot; it is unrelated to these agent instructions.
