# ADR-0002: Multi-tenancy and tenant isolation

- Status: Accepted
- Date: YYYY-MM-DD
- Deciders: the maintainer

<!-- This is a second worked example ADR, alongside ADR-0001. It records the
     tenancy and isolation decision a SaaS project built on this template
     typically makes. It is written stack-agnostic on purpose: adapt the
     specifics (which database, which query layer) to your stack, or replace
     it outright if your project needs a different model. A fuller worked
     example of the whole control plane (the isolation wiring, the choke
     point, workspaces, scoped RBAC, teams, provisioning, impersonation, and
     the grow-into surface) is in docs/design/multi-tenancy.md. -->

## Context

A SaaS product built on this template serves more than one customer
organization ("tenant") from a single deployment. Before any tenant-owned
code is written, three questions need an answer: how tenants stay isolated
from each other, how a caller's role in a tenant is determined, and whether a
platform operator's power is a tenant role or something separate. This is
expensive to get wrong and hard to reverse: isolation is a property of every
table and every query path, not a module that can be swapped out later, and a
design that relies on application code remembering a filter tends to leak
the first time someone forgets it, drops to a raw query, or adds an admin
tool that reads across tenants.

## Decision

**Isolation model: shared database, shared schema, a tenant discriminator
column on every tenant-owned row, enforced at a single choke point the
application cannot bypass.** This is the "pool" end of the pool-vs-silo
spectrum (AWS SaaS Factory's terms) and the default most B2B SaaS run: cheaper
to build and operate than a schema or database per tenant, and it scales to a
large tenant count without a fleet of schemas to migrate in lockstep. If your
database supports row-level security, use it as the authoritative boundary
(Postgres RLS with `FORCE ROW LEVEL SECURITY` is the reference case): the
database itself refuses a query with no tenant set or the wrong tenant set,
so a forgotten application-level filter cannot cross tenants. If it does not,
enforce the tenant predicate in one place only (a single query interceptor or
repository base layer, never repeated inline per handler), and add an
isolation test proving it cannot be bypassed. An ORM-level query filter (EF
Core global query filters, Rails default scopes, and similar) is a good
ergonomic second layer, but it is not the boundary: convenient and readable,
not what an isolation review should rely on, since raw queries and admin
tooling can still bypass it.

**The token stays thin.** The access token carries the caller's identity and
the active tenant id, never roles or permissions. A caller's role in the
active tenant is resolved per request from a membership table, the same way
resource ownership is already resolved per request. A role change or a
revoked membership then takes effect on the caller's next request instead of
waiting for a token to expire.

**Users are global; membership is per tenant.** One user account can belong
to many tenants (like a GitHub account across organizations), each with its
own role. Identity does not change; tenancy is a separate concern layered on
top of it.

**Authorization is three layered checks, in order:** the tenant boundary (the
isolation mechanism above; the caller only ever sees rows of the active
tenant), tenant-role RBAC (what the caller's role in this tenant permits, for
example `owner > admin > member`), and resource ownership within the tenant
(the same per-resource check a single-tenant app already needs). Each layer
is independent and separately testable.

**Sub-tenant structure is an authorization scope, not a second tenant.** A
customer that subdivides its own account into workspaces (for example
production, staging, and development, or one per team or project) gets a scope
inside the tenant, not a new tenant and not a second hard isolation tier.
Workspace-owned rows carry a workspace discriminator and access is enforced by
scoped role grants, while the tenant discriminator stays the only hard,
database-enforced boundary. A workspace that genuinely needs hard isolation
uses the silo escape hatch below. Roles generalize accordingly: from a fixed
set into permissions (a closed, application-defined catalogue) composed into
roles (built-in system roles plus tenant-defined custom roles), granted to
principals (a user or a team) at a scope (the tenant, or a workspace).
Effective permissions are the union of the grants that match, resolved per
request. Adopt the fixed roles first and grow into workspaces, teams, and
custom roles when a customer needs them; the fixed-role model is the
degenerate case of this one.

**A platform super-admin plane is separate from tenant roles, not a tenant
role itself.** Crossing tenants (support tooling, provisioning, platform
operations) is a distinct capability held by a small, explicitly granted set
of platform operators, checked independently of tenant membership, and
reached through a code path ordinary tenant-scoped request handling cannot
obtain. There is no in-band bypass flag that request-scoped code can flip.
When a platform operator needs to act as a tenant user, the session is
audited (who, which tenant, why, start time), time-boxed with a short expiry,
and revocable before that expiry takes effect.

**Escape hatch: silo per tenant.** A handful of tenants may need their own
schema or database, for example a regulatory requirement or a contractual
isolation guarantee. Design the tenant-to-storage resolution as a single
indirection from the start, so moving one tenant to a silo later is a
data-access change, not an application rewrite. Shared schema stays the
default; silo is the documented exception.

## Consequences

- Every tenant-owned table needs a tenant discriminator column from its
  first migration, and the isolation mechanism must be wired before any
  tenant-owned feature ships, not retrofitted after data has commingled.
- Cross-tenant leakage becomes the top isolation risk (docs/10-security.md)
  and needs its own test suite: a caller in tenant A must never see tenant
  B's rows, by any code path, including raw queries and background jobs.
- Background jobs and event consumers need the same tenant context as HTTP
  requests; a consumer that forgets this leaks exactly like an endpoint that
  forgets it.
- The membership lookup adds a query to every authorized request; caching it
  for the life of the request keeps this cheap.
- Impersonation needs its audit trail (who, target tenant, reason, start and
  end time) built before support tooling ships, not added after the first
  incident that needs it.
- Provisioning a new tenant (self-serve signup, or an invited member joining
  one) runs before any tenant context exists, so it needs its own atomicity
  story: a failed signup must not leave a tenant with no owner, or a user
  with no tenant.
- Workspaces and teams are authorization concerns, so they add per-request
  permission resolution, not new isolation plumbing: the tenant discriminator
  and its enforcement point stay the only hard boundary. Keep the permission
  catalogue closed (the application defines the permissions; customers only
  compose them into roles), or custom roles become an unbounded surface.

## Alternatives considered

- **Silo per tenant (schema or database per tenant) as the default.**
  Strongest isolation and the easiest to explain to a security-conscious
  customer, but migrations, connection pooling, and cost all scale with
  tenant count, which does not fit a template meant to start cheap and grow.
  Kept as the documented escape hatch, not the default.
- **Roles embedded in the access token.** Simpler to authorize since there is
  no per-request lookup, but a role change or a removed member stays valid
  until the token expires, and a user in several tenants would need every
  tenant's roles baked into the same token. Rejected in favor of resolving
  role per request, consistent with how ownership is already checked.
- **A single super-admin tenant role instead of a separate platform plane.**
  Simpler to model, one role table instead of two, but it conflates
  "can administer this one tenant" with "can act across every tenant," and
  makes platform-level power a side effect of tenant membership instead of an
  explicitly granted, auditable capability. Rejected: cross-tenant power
  needs to be its own decision, not a role name.
- **A workspace as its own tenant, or as a second hard isolation tier.**
  Modeling an intra-account workspace as a separate tenant loses the
  account-level grouping (billing, admins over all workspaces) and forces a
  super-tenant concept anyway. Making it a second database-enforced isolation
  tier breaks the routine "an admin sees across all workspaces" path and
  multiplies the bypass code that isolation exists to avoid. Rejected in favor
  of a workspace as an authorization scope, with the silo escape hatch for the
  rare workspace that needs hard isolation. This mirrors how GCP (organization,
  folder, project) and GitHub (organization, team, repository) scope access.
