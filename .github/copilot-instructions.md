# GitHub Copilot / VS Code - project instructions

The canonical, cross-agent operating contract for this repo is
**[AGENTS.md](../AGENTS.md)** at the repo root. Read it in full and follow it.
It is the source of truth for the workflow, the gates, the
AI-assisted-development rules, the docs-first + documentation-sync rules, and
secrets handling.

## Sync rule

Keep this file thin. Anything meant for ALL agents goes in AGENTS.md, never
here - this file holds only VS Code / Copilot-specific notes.

## VS Code / Copilot-specific notes

- Follow the docs-first flow in AGENTS.md section 1: refine the doc if it exists,
  otherwise create it from the skeleton, before writing code against it.
- The review gates in `docs/process/06-review-guidelines.md` apply to
  Copilot-suggested code exactly as to any other change.
