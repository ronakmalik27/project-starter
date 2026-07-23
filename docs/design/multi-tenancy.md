# Multi-tenancy and the SaaS control plane: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
the full SaaS control plane a product built on this template typically grows
into: tenant isolation, tenant onboarding, tenant-scoped RBAC, workspaces,
teams, custom roles, a tenant-admin control-plane API, and a platform
super-admin plane with audited impersonation. Adapt the specifics to your
stack, or replace the model if your product needs a different one. Docs-first
applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the
design-level companion to
[docs/adr/0002-multi-tenancy-and-tenant-isolation.md](../adr/0002-multi-tenancy-and-tenant-isolation.md),
which records the decision; this document elaborates the model and mechanics.
Being a generic reference, it deliberately carries no build-sequence or
built-versus-proposed status sections (a concrete product's own design doc
would): treat every part as a menu, adopt the pieces your product needs.

## 1. The decision, in brief

ADR-0002 covers the load-bearing choices; this section only points at them:
shared database and schema with a tenant discriminator on every tenant-owned
row, enforced at a single choke point the application cannot bypass (the
"pool" end of the pool-vs-silo spectrum, the default most B2B SaaS run); a
thin access token carrying identity and the active tenant id, never roles;
users global and membership per tenant (one account, many tenants, like a
GitHub account across organizations); and crossing tenants as an explicitly
granted capability, not an in-band bypass flag. ADR-0002 is maintained to
also cover the workspace, scoped-RBAC, and team model in sections 7 to 10;
where the two overlap, the ADR is the decision record and this doc is the
how.

## 2. Isolation: the authoritative boundary, plus an ergonomic second layer

Every tenant-owned table carries a not-null `tenant_id`.

**If your database supports row-level security, use it as the authoritative
boundary** (Postgres RLS with `FORCE ROW LEVEL SECURITY` is the reference
case): a policy on every tenant-owned table restricts every verb to rows
matching the tenant set for the session or transaction. `FORCE` matters
because without it the table-owning role, usually the app's own connection
role, silently bypasses its own policies. A null-safe tenant lookup fails
closed on a missing tenant (zero rows on read, a failed check on write), so
a forgotten filter, a raw query, or an ad hoc admin tool cannot cross
tenants. **Without an equivalent**, enforce the tenant predicate in exactly
one place (a query interceptor or repository base layer every tenant-scoped
read and write goes through), never inline per handler, and add an
isolation test proving it cannot be bypassed.

**An ORM-level query filter is a second layer, never the boundary.** EF Core
global filters, Rails default scopes, Django managers, and similar make the
common path read cleanly and stamp the tenant on writes from server-side
context, never client input. Raw SQL and ORM escape hatches can slip past
them, so keep both: the ORM filter for ergonomics, the authoritative
boundary for the guarantee.

**Crossing tenants safely.** Platform operations, migrations, provisioning,
and genuinely cross-tenant jobs run through a separate, RLS-bypassing
connection or data source reached only through a code path request-scoped
code cannot obtain. No in-band bypass switch: anything a request could flip
would reintroduce the gap the boundary removes (section 15 covers the test
that proves it).

## 3. The single choke point that sets the tenant

Every tenant-scoped unit of work, reads and writes alike, sets the current
tenant through exactly one seam: one transaction-start (or connection-scoped)
interceptor, or one repository base layer, that every tenant-scoped path runs
through, including reads that would otherwise be transactionless. A read with
no tenant context is fail-closed, never a leak.

Binding the tenant to the transaction, not the connection, is what matters: a
pooled connection is reused across requests, so a tenant merely trusted to
reset at connection-open time is one missed reset from a cross-tenant leak.
Binding it to the unit of work means it cannot outlive the work it was set
for.

## 4. The async and event-consumer path gets the same isolation as requests

The event/outbox spine is first-class, so consumers get the same
authoritative isolation as requests, not a "background work" bypass.

- **Events carry their tenant.** Every domain event and outbox row gains a
  `tenant_id`: set for tenant-owned work, null only for a platform-level
  event, stamped by the emitter from the ambient tenant context at enqueue
  time, never from the event body.
- **Consumers run under the tenant context.** Before a tenant-scoped
  consumer opens its unit of work, the dispatcher sets a consumer-scoped
  tenant context from the event's `tenant_id`, and the choke point from
  section 3 applies it, so a consumer that forgets to filter still cannot
  cross tenants. Dedup bookkeeping and any write run under the same context.
- **Platform consumers are the exception, marked as such:** a consumer that
  must legitimately span tenants declares that explicitly and runs on the
  bypass path, a small named set, never the default.

## 5. Tenant context resolution and the thin token

A resolution step establishes the tenant from a configurable, ordered list of
sources, typically: the active-tenant claim on an authenticated token
(authoritative once signed in); a subdomain (`acme.app.example.com` -> slug
`acme`); a path prefix (`/t/{slug}/...`); an explicit header (for API clients
and tests). A tenant-scoped request with no resolvable tenant is a 400; one
naming a tenant the caller no longer belongs to is a 403.

The token gains only the active tenant id, still no role. A user in several
tenants selects one (a token-mint or tenant-switch endpoint); refresh
preserves the selection. The still-a-member check runs at mint time and per
request, so a removed member cannot mint or keep using a token for a tenant
they left, even before it would otherwise expire.

## 6. Authorization: three layered checks

In order: **tenant boundary** (section 2, plus the active-tenant claim: the
caller only sees rows of the active tenant, enforced below the application);
**tenant role capability**, a gate that resolves the caller's role in the
active tenant per request, from the membership table, refusing below a
minimum (typically `owner > admin > member`: member management and
invitations need `admin`+, deleting the tenant or transferring ownership
needs `owner`); and **resource ownership**, the same per-resource check a
single-tenant app already needs, where the owner rule is unchanged and a
second rule additionally grants a caller `admin`+ in the active tenant. Either
succeeding grants access, so the effective rule is resource-owner OR
tenant-admin+: a
`member` manages only what they own, an `admin` may manage any resource in
the tenant.

The role is read per request and cached for it, mirroring how ownership is
already resolved per request rather than baked into the token.

## 7. Workspaces: a scope inside the tenant, not a second isolation tier

Real customers subdivide their own account: production/staging/dev, or one
space per team or project. A **workspace** is a named scope within one
tenant, never spanning tenants; a tenant has one or many, named however the
customer likes.

`workspaces` (tenant id, unique-per-tenant slug, name, status, timestamps)
is tenant-owned and lives under the tenant boundary, so listing workspaces
is an ordinary tenant-scoped read; a workspace id is deliberately NOT a
second mandatory boundary. A tenant-owned table may gain a nullable
`workspace_id` (null is tenant-level, visible tenant-wide subject to role; a
set value binds the row to that workspace), and the example module's
records gain this as the worked example.

**Why authorization scope, not a second mandatory boundary.** The tenant
boundary is cross-customer: a leak is a breach, so it belongs in the
database. A workspace boundary is intra-customer, and its admins routinely
need to act across every workspace. A mandatory workspace-level boundary
would turn "everything in my tenant, across all workspaces" into many
queries or a bypass, and workspace membership is fluid where a database
boundary is coarse. The industry splits it this way already (GCP Org ->
Folder -> Project IAM, GitHub Org -> Team -> Repo, LaunchDarkly Project ->
Environment: cross-tenant is physical, intra-account is authorization). So a
workspace-owned row carries `workspace_id`, queries filter on it, and the
scoped-RBAC layer (section 8) refuses a caller with no grant there, with the
tenant boundary still underneath as defense in depth.

Workspace context is per request, not in the token, resolved from the route
or the resource's `workspace_id`, the same stance as tenant roles. The silo
escape hatch still applies at workspace granularity: a workspace needing
regulator-grade isolation (production kept separate from dev) uses the silo
indirection from section 16, keyed additionally on the workspace.

## 8. Generalized RBAC: permissions, roles, and grants

The fixed `owner > admin > member` ordering is the degenerate case of a
three-part model; the generalization is additive, preserving existing
behavior with the fixed roles becoming the code-defined system roles.

- **Permissions**: enumerated atoms of capability, a closed catalogue the
  product ships and customers compose into roles, never invent (as GitHub
  and Auth0 do for custom roles). Stable string keys, e.g.
  `members:manage`, `invitations:manage`, `roles:manage`, `teams:manage`,
  plus the example module's `records:read/write/delete`. Owner-reserved
  permissions (managing or deleting the tenant, ownership transfer) can
  never appear in a custom role.
- **Roles**: system roles (`owner`, `admin`, `member`) are defined in code, not
  rows: the fixed permission sets the membership base role names, so they stay
  outside the tenant boundary entirely. Custom roles are per-tenant rows in the
  `roles` table (tenant id not null, tenant-owned) with a tenant-chosen subset of
  the catalogue (section 10), recording whether they may be assigned at tenant
  scope, workspace scope, or both, and, when workspace-local, which workspace
  owns them.
- **Grants** (`role_assignments`) bind a CUSTOM role to a principal at a scope:
  tenant id, principal type (`user`/`team`), principal id, role id, scope
  type (`tenant`/`workspace`), scope id. Only a custom role is grantable this
  way; a system role is conferred solely through the membership base role, so
  cross-cutting system power is never handed out through a grant. Grants layer
  finer, scoped, or team-held permissions on top of the base role, GitHub's
  org-role-plus-repo/team-grants shape. Creating a grant validates that the scope
  type is one of the role's assignable scopes and, for a workspace-local role,
  that the scope id equals the role's owning workspace, so a role is never bound
  wider than intended.

**Effective permissions** at a scope are the union of the caller's tenant
base-role permissions (tenant-wide, inheriting into every workspace) plus
every grant whose principal is the caller or a team they belong to (section
9), scoped to the tenant or exactly the workspace in context. Inheritance is
downward only: a workspace-scope grant never confers tenant-wide power.
Resolution is per request, cached, fail-closed, considers only an active
membership (a suspended membership confers nothing, so a suspension takes effect
on the next request), and runs under the tenant boundary.

**"Roles" and "policies".** A role is a named set of permissions; a policy is a
grant, the binding of a role to a principal at a scope (not the database RLS
policy of section 2). That is role-based
access control (RBAC), the right default for B2B SaaS and what most run (GitHub,
Slack, Linear). Rules that also depend on request attributes (time, IP, resource
labels) are ABAC: a documented grow-into (section 18) that plugs into this same
per-request check, not a day-one need. Start with roles and scoped grants.

**Gates.** The coarse tenant-role gate (section 6) stays for coarse checks;
a finer gate resolves effective permissions at the request's scope and
refuses when absent. Ownership composes with permissions exactly as
tenant-admin composes with ownership in section 6: write permission at
workspace scope plus ownership admits the owner or any workspace writer.

## 9. Teams as principals

A **team** is a named group of users inside a tenant that can hold grants,
so access is managed for a group instead of user by user (GitHub teams).
`teams` and `team_members` (unique per team and user) are tenant-owned, under
the tenant boundary. A team is a principal in `role_assignments`
(`principal_type = team`); the resolver unions the grants of every team the
caller belongs to. Because resolution is per request, adding or removing a
team member grants or revokes on the next request, with no token churn. Team
management requires `teams:manage`.

## 10. Custom roles and guardrails

**Who authors what.** The product owns the permission catalogue and the system
roles; a tenant composes its own roles from that catalogue. This is the
industry-standard split (GitHub custom organization roles, Auth0 roles): the
application defines the vocabulary of permissions, the customer arranges them
into roles. So a tenant admin with `roles:manage` self-serves custom roles with
no platform operator in the loop, and the platform decides only what permissions
exist and, optionally, gates custom roles behind a plan tier. The super-admin
plane may additionally publish global role templates seeded into every tenant
(section 18).

A custom role is a name, an optional description, a chosen subset of the
permission catalogue, and where it may be assigned, stored as a role row plus its
permission rows, both tenant-owned and under the tenant boundary (system roles
are code, not rows). A role's definition is owned at a scope: a tenant-owned role (no
workspace) is assignable across the tenant per its scope setting, while a
workspace-local role (tagged with a workspace) is defined by a workspace admin
with `roles:manage` there and assignable only in that workspace, so each
workspace can carry its own roles without cluttering the rest (as GCP allows a
custom role at the organization or at a single project).

Guardrails: the catalogue is closed (only shipped permissions, never
owner-reserved ones, so cross-cutting control cannot be handed out piecemeal); a
permission the tenant's plan does not include cannot be added (the entitlements
seam from section 18, a no-op filter until billing exists); a workspace-local
role's grants never reach tenant scope (no upward inheritance, section 8);
editing a role's permissions changes what every holder can do on their next
request; and a custom role currently assigned to anyone cannot be deleted, so
access never silently dangles.

## 11. Scope-aware invitations

A base invitation invites a user to a tenant with a base role. A scope-aware
invitation can also target a workspace and a role there: `invitations` gains
a nullable `workspace_id` and role reference, alongside the base-role field.
On accept, in the one bypass transaction of section 12 (seat check under a
row lock, email match, single-use consume): the membership is created if the
invitee is new to the tenant (base role `member` unless stated otherwise),
and when the invite carries a workspace and role, the matching grant is
created at that scope. The invited role must be a custom role owned by that same
workspace (the section 8 grant validation applies here too), so an invitation
cannot bind a role wider than its scope. One step invites straight into, for
example, "developer on the staging workspace."

## 12. Provisioning atomicity

Creating a tenant establishes a new isolation boundary, so it runs before
any tenant context exists, on the bypass path, through two entry points.
**Self-serve**: an anonymous, rate-limited signup creates the user, tenant,
and owner membership atomically in one transaction, emitting
tenant-created and membership-created events; a failed signup must not
leave a tenant with no owner, or a user with no tenant. If staging the
identity write on a shared transaction is too invasive, the fallback is to
create the user normally, then provision the tenant idempotently on first
authenticated request, treating a transient user-with-no-membership state
as benign, the same as an invited-but-unaccepted user; prefer the
single-transaction path where supported. **Invited**: an invitee accepts
into an existing tenant (section 11); no new tenant is created.

**Accepting an invitation is authorized differently from every other
tenant-admin action:** the invitee holds no role or active-tenant claim yet,
so it cannot sit behind the tenant-role gate. It is authorized by
possession of a hashed, single-use, expiring invite token plus an
authenticated user id, read by token hash on the bypass path. In one
transaction: re-check the seat limit under a row lock (so concurrent
accepts cannot overrun it), create the active membership, consume the
token, and emit a membership-created event.

## 13. Platform super-admin plane and audited impersonation

A separate authorization plane, gated by a platform-admin check backed by
its own table, never a tenant role, run on the bypass path. Surface:
list/search/view tenants; suspend, reactivate, soft-delete a tenant;
grant/revoke platform admins; start/stop impersonation. `platform_admins` is
tiny and separate from tenant membership; the first admin is an
out-of-band seed, never self-granted through the API.

**Impersonation is audited, time-boxed, and revocable.** A platform admin
starts a session against a target tenant (optionally a target user) with a
written reason. In one transaction, the server writes an
`impersonation_grants` row and emits an impersonation-started event, then
mints a short-lived token carrying the target tenant id plus a signed,
unforgeable impersonation claim naming the admin, so no token can exist
without its audit row. Every impersonation-bearing request re-checks the
grant (not ended, not expired), so an early end takes effect immediately,
not just at token expiry. Destructive operations may be refused outright
while impersonating, tightened per endpoint. When the grant names no target
user, the session acts as the admin's own identity in the tenant with a
read-only default: it can view but not mutate unless an endpoint opts in. The
grant auto-expires at its cap with no rotation; an early end writes an end time
and emits an impersonation-ended event.

## 14. Data model summary

Generic relational concepts, each with an id primary key; all tenant-owned
tables also carry `tenant_id` and sit under the tenant boundary unless noted:

- `tenants`: case-insensitive-unique slug, name, status (`active`,
  `suspended`, `deleted`), plan, seat limit, timestamps. Soft-delete via
  status, never a hard delete; administered on the bypass path.
- `memberships`: tenant id, user id, role, status, invited-by, timestamps.
  Unique per tenant and user.
- `invitations`: tenant id, case-insensitive email (unique per tenant among
  pending invitations, a partial index), role, hashed token, expiry,
  accepted-at, invited-by, timestamps, plus nullable `workspace_id` and role
  reference (section 11).
- `workspaces` (section 7): tenant id, unique-per-tenant slug, name,
  status, timestamps.
- `roles` (custom roles only; system roles are code, not rows): tenant id (not
  null), key, name, description, `assignable_at` (`tenant`/`workspace`/`both`),
  workspace id (null for a tenant-owned role, set for a workspace-local one,
  section 10), timestamps. Tenant-owned, under the tenant boundary. Unique on
  (tenant id, workspace id, key).
- `role_permissions`: role id, tenant id (not null, denormalized from the role),
  permission key. Tenant-owned and under the tenant boundary like every other
  tenant table, so a raw read cannot cross tenants; custom-role rows only.
- `role_assignments`: tenant id, principal type (`user`/`team`), principal
  id, role id (a custom role), scope type (`tenant`/`workspace`), scope id (null
  for tenant scope), granted-by, timestamps. Uniqueness is a partial unique index
  per scope kind, since a null scope id would not collide under a plain unique
  constraint.
- `teams`, `team_members` (section 9): tenant id and the obvious columns.
- `platform_admins`: user id, granted-by, granted-at. Not tenant-scoped.
- `impersonation_grants` (section 13): platform admin user id, target
  tenant id, target user id (nullable), reason, issued-at, expires-at,
  ended-at. Not tenant-scoped; the audit spine.

Domain events and the outbox gain `tenant_id` (section 4). The permission
catalogue and the system-role permission sets are code, not tables.

## 15. Tests: isolation is the crown jewel

Behaviors the integration suite must prove, whatever framework a stack uses,
blocking not nice-to-have:

- **Cross-tenant leakage.** Tenant A gets not-found (not forbidden, to avoid
  confirming existence) on every tenant B resource: read, update, delete,
  list. A raw query on the ordinary role with the wrong or missing tenant
  set returns zero rows, proving the boundary, not just the ORM filter.
  Interleaving many tenants across a pool proves no connection carries a
  stale tenant.
- **Bypass containment.** An ordinary session cannot cross tenants by any
  means, including setting a bypass flag; only the bypass path crosses.
- **Consumer isolation.** A tenant-scoped consumer on tenant A's event
  cannot touch tenant B's rows; a marked cross-tenant consumer can.
- **RBAC.** A `member` is refused member-management; an `admin` is granted
  it; owner-only operations refuse an `admin`.
- **Ownership within a tenant.** A `member` cannot edit another member's
  resource; an `admin` in the same tenant can.
- **Impersonation.** Starting writes the grant and emits the event; the
  token carries the claim; a refused destructive op stays refused; an early
  end blocks the next request immediately; the grant expires at its cap.
- **Provisioning and invitations.** Self-serve signup creates tenant plus
  owner membership atomically (failure leaves neither); acceptance creates
  membership and consumes the token exactly once; concurrent accepts cannot
  exceed the seat limit.
- **Custom roles.** A role granting only `invitations:manage` lets its
  holder invite but not manage members; editing permissions changes
  behavior next request.
- **Guardrails.** A custom role containing an owner-reserved permission is
  rejected on create or edit; assigning a workspace-local role at tenant scope,
  or at a different workspace, is rejected.
- **Scoped RBAC and inheritance.** A tenant-scope grant is honored in every
  workspace; a workspace-scope grant is honored only there, conferring
  nothing tenant-wide.
- **Workspace isolation within a tenant.** A workspace-A record does not
  appear listing workspace B; a tenant admin sees both; another tenant
  still gets not-found by the tenant boundary.
- **Teams.** A team's grant reaches its members; removing a member revokes
  it next request.
- **Scope-aware invitation.** Accepting a workspace-scoped invite creates
  the membership and the workspace grant in one transaction; concurrent
  accepts still cannot exceed the seat limit.

## 16. Placement, deletability, and the silo escape hatch

The platform/shared layer gains only cross-cutting primitives (tenant
context, the tenant-owned-row convention, the tenant-setting interceptor,
tenant resolution, the bypass data source, platform-admin authorization),
since every module's data access depends on the tenant filter. A dedicated
tenancy module/service owns tenants, memberships, invitations, workspaces,
roles, grants, teams, provisioning, and the tenant-admin and platform
control-plane operations behind its own internal API. The example feature
module migrates to tenant-owned as the copy-me reference, layering the
tenant boundary, the ORM filter, ownership, and (after Part II) a nullable
workspace id. Identity is nearly untouched: users stay global; the
additions are minting the active-tenant claim into a token, and a seam to
stage registration on a provided transaction for atomic provisioning.

**Deleting the whole SaaS layer is a design goal**: remove the tenancy
module, revert the example module to owner-only, drop the shared-layer
tenant pieces, the token claim, and the bypass data source. The rest of the
product does not depend on any of it, since building it as a bolt-on from
day one avoids retrofitting isolation onto data that has already
commingled.

**Silo path.** Because a module's data access is constructed against a
connection and schema, moving a tenant to its own schema or database is a
change in connection resolution (a per-tenant connection factory keyed off
the tenant context), not a code change. Shared schema stays the default; the
interceptor and filter become redundant-but-harmless under a silo, so a
mixed fleet (mostly pooled, a few siloed) needs no fork.

## 17. Lifecycle: onboarding and offboarding

Every entity here has an onboarding and an offboarding path, and offboarding is
the one teams forget. The template provides the control-plane operations; the
tenant-admin portal and the platform super-admin portal are UI built over them.

- **Tenant.** Onboard by self-serve signup or an invited owner (section 12).
  Offboard as a state machine (`active -> suspended -> deleted`, a soft delete),
  then a retention window, then a hard delete that also produces a data export
  (the data-portability and erasure path, section 18). Suspending stops new
  access at once; short-lived tokens age out within the access window.
- **Workspace.** Onboard by create (section 7). Offboard by archive
  (`active -> archived`): its resources become read-only (workspace-scoped writes
  are refused with a stable problem) and no new resources or grants can be created
  in it, while reads still work; nothing is destroyed, so unarchive restores it.
- **Team.** Onboard by create, then add and remove members. Offboard by delete,
  removing the team's grants first so none dangles.
- **Person (membership).** Onboard by invite and accept, or as a self-serve
  owner. Offboard by remove or suspend, revoking the member's grants and team
  memberships on the next request. Resources they owned are reassigned or
  transferred, never silently orphaned (a tenant admin can already manage any
  resource, section 6). Enterprise deprovisioning (SCIM, section 18) drives this
  same path from the customer's directory.
- **Role and policy.** Onboard by defining a custom role and granting it
  (sections 8, 10). Offboard by revoking grants and deleting the role; a role in
  use cannot be deleted until its assignments are removed or reassigned.

Two rules cut across all of them: an offboarding action revokes access on the
next request (per-request resolution, never waiting for a token to expire), and
it is recorded on the event spine (who offboarded what, and when), which is what
an incident review reconstructs.

## 18. Beyond this blueprint: the SaaS grow-into surface

The tenancy layer, plus the product's existing spine (outbox, idempotency
keys, sessions, structured error responses, rate limiting), already carries
the hooks for the rest of the control-plane surface a typical B2B SaaS grows
into. None of this is built here; each hangs off an existing mechanism
rather than a rewrite. Build on demand, not ahead of need:

- **API keys, service accounts, PATs**: a non-human principal type, hashed
  like other one-time tokens, carrying scoped grants (section 8). DESIGNED
  and being built out - see [service-accounts.md](service-accounts.md).
- **SSO (SAML/OIDC) and SCIM**: a per-tenant identity-provider config; SCIM
  maps directory groups to teams (section 9) and roles. DESIGNED and being
  built out - see [sso-and-scim.md](sso-and-scim.md).
- **MFA/TOTP**: an identity-module add-on on the sign-in path; no tenancy
  change. DESIGNED and being built out - see [mfa-totp.md](mfa-totp.md).
- **Billing (plans, subscriptions, seats, metering) and entitlements**: plan
  and seat-limit already exist on the tenant; entitlements gate the
  permission catalogue (section 10) and features per plan. DESIGNED and
  being built out - see
  [billing-and-entitlements.md](billing-and-entitlements.md).
- **Feature flags**: rollout and kill-switch gating, the operational
  counterpart to entitlements above - a global operator catalogue plus
  tenant and workspace overrides (section 7), fail-closed where
  entitlements fail open. DESIGNED and being built out - see
  [feature-flags.md](feature-flags.md).
- **A first-class, queryable audit log**: distinct from the domain-event
  stream; a projection off the outbox (impersonation is the first audited
  action). DESIGNED and being built out - see
  [audit-log.md](audit-log.md).
- **Outbound webhooks**: a consumer fanning events to tenant-registered
  endpoints, reusing the outbox's at-least-once delivery. DESIGNED and
  being built out - see [webhooks.md](webhooks.md).
- **Data export and account deletion (GDPR/DSAR)**: tenant-scoped reads and a
  soft-delete-to-hard-delete lifecycle on the tenant status field. DESIGNED
  and being built out - see
  [data-export-and-erasure.md](data-export-and-erasure.md).
- **Usage quotas**: per-tenant, plan-driven limits on resource counts
  (workspaces, seats) and metered consumption (API calls, jobs run) over a
  billing period. Distinct from the edge rate limiter: that limiter throttles
  abuse by IP or credential regardless of tenant or plan, on a seconds-scale
  window, while a usage quota enforces a commercial ceiling per tenant over a
  billing period; the two compose but share no mechanism. DESIGNED and being
  built out - see [quotas.md](quotas.md).
- **In-app notifications**: a per-recipient projection off the existing
  event/consumer spine, the same shape as the audit log but keyed to one
  user instead of the whole tenant. DESIGNED and being built out - see
  [in-app-notifications.md](in-app-notifications.md).
- **Data residency**: rides the silo indirection (section 16).
- **Global role templates and platform policy defaults**: the super-admin plane
  authors role templates seeded into every tenant, plus platform-wide defaults
  (password, session, lockout policy) a tenant inherits and may tighten.
  DESIGNED and being built out - see
  [role-templates-and-policy-defaults.md](role-templates-and-policy-defaults.md).
- **A policy engine (ABAC)**: conditional grants (time, IP, resource attributes)
  via an engine such as Cedar or Open Policy Agent, evaluated at the same
  per-request permission check (section 8); RBAC stays the default, ABAC layers
  on when a rule needs a condition. DESIGNED and being built out - see
  [abac.md](abac.md).
