# 10 - Production readiness

Do not build these documents up front. This checklist is the opposite of a stub
pile: it names the operational, security, and delivery concerns a product grows
into, says WHEN each becomes real, and points at where it already lives as a
section - so you expand it in place (or split it into its own doc) only when the
trigger fires. This is the deferred-readiness idea from 04-architecture-principles.md
applied to operations: keep the hook, expand on demand.

It follows the same refine-or-create rule as every doc here: if your project
already has one of these as its own doc, refine it; otherwise expand the
referenced section when its trigger fires.

## The checklist

| Concern | Create or expand when ... | Lives today in |
|---|---|---|
| Observability and SLOs | anything runs somewhere other than a laptop | [../11-devops-infra.md](../11-devops-infra.md) (Observability) |
| Incident response and on-call | an outage can affect real users | this doc + [../ops/postmortem-template.md](../ops/postmortem-template.md) |
| Disaster recovery and backups | you store data you cannot afford to lose | [../11-devops-infra.md](../11-devops-infra.md) (Backups and DR) |
| Data privacy and compliance | you hold personal or regulated data | [../10-security.md](../10-security.md) (Data handling) |
| Cost and FinOps | cloud or AI-token spend becomes non-trivial | [../11-devops-infra.md](../11-devops-infra.md) (Cost envelope) |
| Performance and load | latency or throughput becomes a user-visible risk | [../12-testing-strategy.md](../12-testing-strategy.md) (Performance) |
| Security review / threat model | you add an external surface or handle secrets/PII | [../10-security.md](../10-security.md) (Threat model) |
| Release and versioning | you cut a first release to anyone but yourself | [11-release-and-versioning.md](11-release-and-versioning.md) |

A concern promoted to its own doc becomes a numbered doc under `docs/` (or an
ADR in `docs/adr/` if it is mostly a decision, see [09-decision-framework.md](09-decision-framework.md)).
Until then, keep it a section so the knowledge base stays honest about what is
actually real.

## Minimum bar before the first production deploy

Whatever the scale, do not put real users on it until:

- Secrets are in a managed secret store, never the repo (see [../10-security.md](../10-security.md)
  and [../../SECURITY.md](../../SECURITY.md)).
- Health checks (liveness + readiness) exist and the deploy blocks on readiness.
- Structured logs and error tracking are on, with a correlation id per request.
- Backups run, and a restore has actually been tested at least once.
- A rollback path is known and has been rehearsed.
- The threat model has been walked for the surfaces you expose.
- An incident can be captured: [../ops/postmortem-template.md](../ops/postmortem-template.md)
  is ready to copy.

## On-call and incidents

Once an outage can affect users, define severity levels, who is paged, and how
you communicate during an incident. Every serious incident gets a blameless
postmortem from [../ops/postmortem-template.md](../ops/postmortem-template.md),
and its action items become tracked work. The retrospective
([08-iteration-cycle.md](08-iteration-cycle.md)) reviews recent incidents.
