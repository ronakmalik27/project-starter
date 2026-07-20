# 05 - Documentation standards

Docs come first (see 01-lifecycle.md): a feature's requirements, design, data
model, and contracts exist in the knowledge base before its implementation
starts. This doc covers how the knowledge base is organised and how to write in
it.

## 1. The knowledge base

The numbered docs in `docs/` are the source of truth. This template ships them
as empty section-only skeletons for you to fill in:

| Doc | Purpose |
|---|---|
| 01-prd.md | Product requirements: who, what, why, success metrics |
| 02-srs.md | Software requirements + system invariants |
| 03-ux-user-flows.md | Screens and user flows |
| 04-ui-design-system.md | Design tokens, components |
| 05-hld.md | High-level design / architecture |
| 06-lld.md | Low-level design of the modules |
| 07-database-design.md | Schema, indexes, migrations |
| 08-api-spec.md | API contracts (link the OpenAPI file) |
| 09-events-messaging.md | Domain events, catalogue, delivery semantics |
| 10-security.md | Threat model, authn/authz, secrets, data handling |
| 11-devops-infra.md | Environments, CI/CD, cost, runbooks |
| 12-testing-strategy.md | The project's concrete test plan |
| 13-engineering-playbook.md | How this project builds day to day |
| 14-ai-integration.md | Where and how the product uses AI (if it does) |

Delete the docs a given project does not need, and add your own. Keep the
process docs (`docs/process/`) as the reusable "how we work" layer and these as
the project-specific "what we are building" layer.

Give requirements stable ids (FR-1, SCR-2, INV-3, ...) and reference them from
code, tests, and PRs so a change can be traced to the requirement it satisfies.

## 2. Writing style

Plain, clean, concise prose that anyone on the team can read. `make hygiene`
(via `scripts/check_doc_style.py`) enforces the character rules mechanically.

- **No em or en dashes.** Use a plain hyphen with spaces " - ", a comma, a
  colon, or rewrite the sentence into two.
- **No section signs.** Write "section 6.4".
- **No typographic Unicode**: straight quotes only; ".." not the ellipsis
  character; "x" not the multiply sign; "<=" ">=" "!=" not the math glyphs;
  "+/-" not the plus-minus sign; "sum(...)" not the sigma.
- **Arrows** ("->") only in state flows and tables (e.g. `planning -> active`),
  never as a prose connector.
- Table checkmark characters are fine.
- Prefer short sentences over clause chains. If a sentence needs three dashes,
  it needs to be two sentences.
- `docs/reviews/` logs and `docs/reference/` frozen drafts are exempt from the
  character scan (a review may quote a violation verbatim; a frozen draft is
  kept as-is by design). The checker encodes both exemptions.

## 3. Structure and cross-references

- One `# Title` per doc, then `##` sections numbered so they can be cited
  ("section 3.2").
- Link between docs with relative Markdown links; `make hygiene` (via
  `scripts/check_doc_links.py`) fails on a broken relative link, so renames stay
  honest.
- When you change a doc, walk its inbound references (what links to it) and fix
  both sides. Cross-doc drift is the most common review finding.
- Record significant, hard-to-reverse decisions as ADRs (09-decision-framework.md),
  not as buried prose.
