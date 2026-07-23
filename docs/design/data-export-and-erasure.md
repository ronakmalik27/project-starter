# Data export and erasure (GDPR / DSAR): a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how data export and tenant erasure grow out of the multi-tenancy control
plane in [docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into
bullet in that doc's section 18, "Data export and account deletion
(GDPR/DSAR)"): adapt the specifics to your stack, or skip it if your product
has a simpler compliance surface. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the
seventh worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), and [quotas.md](quotas.md).

It builds directly on multi-tenancy.md's isolation boundary (section 2), its
offboarding state machine (section 17: `active -> suspended -> deleted`), and
its platform super-admin plane (section 13); read those first. It also
reuses audit-log.md's synchronous platform-audit write (sections 2 and 4)
and catalogue-completeness discipline (section 10), and echoes quotas.md's
own load-bearing-trap framing (section 5) for a different trap: this
document's is a missing table, not a missing map key. Being a generic
reference, it carries no build-sequence section (a concrete product's own
design doc would): treat every part as a menu, adopt the pieces your product
needs.

## 1. The decision, up front

- **Two distinct rights, two distinct mechanisms.** Data EXPORT (GDPR
  Art. 15/20, access and portability) is a tenant-scoped READ that assembles
  the tenant's data into a machine-readable bundle. Data ERASURE (Art. 17,
  the right to be forgotten) is a hard DELETE of the tenant's rows. They
  share nothing mechanically and are gated differently: a tenant admin
  self-serves an export; only a super-admin erases.
- **The offboarding lifecycle is a state machine, and the hard delete is the
  only new state transition.** `active -> suspended -> deleted` (soft,
  status-only) already exists (multi-tenancy.md section 17): both a
  super-admin and a tenant owner can soft-delete, and the row is never hard
  deleted, only `status = deleted`. This document adds: a `deleted_at`
  stamp, a RETENTION WINDOW after soft-delete, and the HARD DELETE that
  purges the tenant's rows once the window elapses. A soft-deleted tenant is
  recoverable (reactivate); a hard-deleted tenant is gone.
- **The retention window is meaningless without recoverability.** A window
  that exists but cannot be undone during it is not a grace period, it is
  just a delay before the same irreversible outcome. So reactivate MUST
  accept a `deleted` source state, not only `suspended`, and clear
  `deleted_at` on the transition - the standard "restore within N days"
  model (GitHub's organization-deletion grace period, Google Workspace's
  account-recovery window). A HARD-deleted tenant cannot be reactivated: its
  rows are gone.
- **The hard delete PRODUCES a final export before it purges.** Erasure is
  preceded by a portability snapshot: the operator captures everything about
  to be destroyed, which is both the compliance record and the customer's
  last chance at their data. The self-serve export is the tenant-facing
  portability artifact; the hard-delete snapshot is the operator's pre-purge
  record. Both draw from the same tenant; one is shaped for the subject, one
  is raw for the operator.
- **THE ARCHITECTURAL CRUX: export runs on the request path under the
  tenant boundary; erasure runs on the privileged, cross-tenant path. This
  split is forced by the isolation model, and it drives the whole design.**
  A self-serve export reads only the caller's OWN tenant, so the ordinary
  request-scoped, tenant-bound context is exactly the right boundary and no
  privileged role is needed. A hard delete is a cross-tenant super-admin act
  on a target tenant, so it needs the bypass/privileged control-plane role
  the platform layer already owns (multi-tenancy.md sections 2, 13, and 16).
  Where a stack's architecture tests (or an equivalent lint/allowlist rule)
  forbid ordinary business modules from touching that privileged role at
  all, erasure CANNOT be a per-module bypass operation. Instead each module
  DECLARES its tenant-owned tables and a central, platform-hosted executor
  issues the deletes on the privileged path. Modules stay privilege-free;
  the platform layer, which legitimately owns the cross-tenant control
  plane, does the privileged work.
- **Erasure safety is an explicit `where tenant_id = @tenantId` on every
  statement, not the tenant boundary.** The privileged role exists precisely
  to bypass row-level isolation, so isolation does NOT scope an erasure
  delete the way it scopes an ordinary request. A missing `where` clause
  would purge every tenant in the system. So every erasure statement carries
  an explicit, parameterized tenant filter, and a test proves erasing tenant
  A leaves tenant B's rows intact in every table. This is the single most
  dangerous operation in the whole system, and it is treated that way.

## 2. The offboarding state machine and retention

- States (unchanged vocabulary, multi-tenancy.md section 17): `active`,
  `suspended`, `deleted`. Soft-delete sets `status = deleted`. This document
  adds a nullable `deleted_at` timestamp on the tenant row, stamped when
  status becomes `deleted` (both the super-admin delete path and the tenant
  owner's own soft-delete path), and cleared (set null) on reactivate.

  ```
  active -> suspended -> deleted -> (retention window elapses) -> hard-deleted
                ^                        |
                |________________________|
                     reactivate (clears deleted_at)
  ```

- The RETENTION WINDOW is a validated, bound-on-start configuration value (a
  number of days, default 30). A hard delete is permitted only when
  `deleted_at + retention_days <= now` (compared against an injectable clock
  abstraction, never the platform's raw current-time call, so a test can pin
  the clock and cross the window deterministically), OR when the super-admin
  passes an explicit `force` flag - a documented break-glass for a legal
  erasure demand that cannot wait out the window. A tenant that is not
  `deleted` cannot be hard-deleted (a conflict response): erasure follows
  soft-delete, it never skips it.
- **Reactivate must accept `deleted` as a source state, not only
  `suspended`.** If a stack's reactivate operation today only widens
  `suspended -> active` and refuses a `deleted` source as a conflict, a
  soft-deleted tenant has no way back, which contradicts the whole point of
  a retention window. Widen the allowed source state to include `deleted`
  (so both `deleted -> active` and `suspended -> active` reactivate) and
  clear `deleted_at` on the transition. A HARD-deleted tenant, by contrast,
  cannot be reactivated: there is no row left to flip back.

## 3. Data export (Art. 15/20), request path, tenant-bound

- A module contributor port: each module contributes one or more named
  sections of the ACTIVE tenant's data, read through its OWN request-scoped,
  tenant-bound context. No privileged role anywhere, so every module,
  including the sample/example module, implements this without touching a
  control-plane privilege:

  ```
  section_name() -> string                       // e.g. "workspaces"
  export(cancellation) -> object | null           // the section's rows, shaped
  ```

- A central export service resolves every registered contributor, invokes
  each one, and assembles the bundle:

  ```json
  {
    "formatVersion": 1,
    "tenantId": "<uuid>",
    "generatedAt": "<iso-8601>",
    "sections": { "tenant": { ... }, "memberships": [ ... ], "workspaces": [ ... ] }
  }
  ```

- **Secrets are EXCLUDED from the export by each contributor.** The bundle
  is the tenant's own data, but a credential artifact is not "data the
  subject is entitled to a copy of" and must never leave the system in a
  portable file. Concretely: the service-account section omits the
  credential key hash; the webhook-endpoint section omits the encrypted
  signing secret. Everything else (memberships, roles, workspaces, teams,
  invitations, notes, audit log, usage counters, flag overrides) is
  included. This is a per-contributor obligation, called out in each
  contributor and generalized in section 8.
- Contributors by module, in the reference build: the tenancy module
  contributes the tenant profile, memberships, workspaces, teams and team
  members, custom roles and role permissions, role assignments, invitations,
  and service accounts (no credential hash). The sample/example module
  contributes its own records. The platform/shared layer contributes the
  audit log, webhook endpoints (no secret) and deliveries, usage counters,
  and feature-flag overrides.
- Endpoint: a tenant-scoped `GET .../tenant/export`, gated by a dedicated
  permission (`data:export`, in the owner-and-admin default role set - a
  bulk export of all tenant data is an administrative act, not a routine
  read). The atom is ALSO added to whatever allowlist a stack uses to keep
  the highest-risk permissions off a service-account principal (alongside
  role management and API-key management, service-accounts.md section 4):
  a bulk-exfiltration primitive on an unattended, always-on service-account
  credential is a distinct risk class from self-escalation, and a leaked
  credential that can pull the entire tenant data set in one call is exactly
  what to refuse. So `data:export` is a human-admin capability only, never
  grantable to a service account. The endpoint returns the bundle and emits
  a tenant-scoped, deliverable domain event (the audit-log and webhook
  projections both pick it up, audit-log.md sections 2 to 4, webhooks.md
  section 3) carrying the actor and a per-section row-count summary, never a
  payload copy - a bulk data access is worth auditing and worth a webhook (a
  security team may want to know).
- Synchronous assembly is fine for a starter (a tenant's data is small).
  Async export to an object-store artifact with a signed, expiring download
  URL, for a large tenant, is a documented grow-into (section 9); the
  contributor seam does not change.

## 4. Data erasure (Art. 17), privileged path, centrally executed

- A tenant-erasure declaration port: each module DECLARES its tenant-owned
  tables, schema-qualified, in FK-safe delete order (children before
  parents), each paired with the column that carries the tenant id. No
  module touches the privileged role; declaration only.

  ```
  // (table, tenant_key_column) pairs, in delete order.
  tenant_owned_tables() -> [ (table: string, key_column: string), ... ]
  ```

  Nearly every table keys on `tenant_id`; the tenant row itself is the sole
  exception, since it carries no `tenant_id` column - its own `id` is the
  discriminator, so its pair is `(tenants, id)` and it is declared LAST.
- A central erasure service, run only on the privileged/bypass path, purges
  a target tenant: open ONE transaction on the privileged connection, and
  for every declared table across every module (the platform layer's own
  tables included), execute

  ```sql
  delete from {table} where {key_column} = @tenant_id;
  ```

  with the tenant id always a bound parameter, never string-interpolated.
  The table and column names come only from the trusted, code-side
  declarations, never from client input, so building the statement from
  them is safe; only the tenant id is a runtime value, and it is always
  bound. Commit once, after every declared table has been swept.
- Tables to erase, in the reference build: the tenancy module's
  `role_assignments`, `role_permissions`, `team_members`, `teams`, `roles`
  (custom roles), `invitations`, `service_accounts`, `memberships`,
  `workspaces`, then `tenants` LAST (its own `id` is the key column); the
  sample/example module's own tenant-owned tables; the platform layer's
  `audit_log`, `webhook_deliveries`, `webhook_endpoints`, `usage_counters`,
  `feature_flag_overrides`, plus the tenant's rows on the event spine
  (domain events, and any pending outbox entries) since those carry tenant
  payloads too. The PLATFORM audit log (as opposed to the tenant audit log)
  is NOT tenant-owned - it records operator actions under a separate legal
  basis - and is never touched by erasure: it is where the erasure records
  ITSELF (section 6).
- **Index the event-spine tenant columns.** If a domain-events table is
  monthly-partitioned and kept forever, and its `tenant_id` column (added
  when tenant scoping was retrofitted onto the event spine) has no index, a
  `delete .. where tenant_id = @t` over it sequentially scans an
  ever-growing table inside the single transaction that also holds locks on
  every other declared table, contending with the live event dispatcher and
  getting slower every month. Index it (on Postgres, a plain
  `create index on domain_events (tenant_id)` propagates to every partition
  via the parent) and index the outbox's tenant column the same way. On an
  empty or lightly-populated table a plain index build is fine; on a
  populated production table build it concurrently, out of band, as an ops
  note rather than inside the increment that adds erasure.
- **Revoke the tenant's live sessions, as defense-in-depth.** A global
  session table is not tenant-owned (sessions belong to the global user
  identity, not to any one tenant), but a session carries a `tenant_id` set
  on tenant-select or refresh, so an erased tenant is still referenced by any
  unexpired session until it ages out naturally. As part of the same
  erasure transaction, revoke every live session carrying the erased
  tenant's id (`update sessions set revoked_at = now() where tenant_id = @t
  and revoked_at is null`), killing any live token for the tenant
  immediately rather than waiting out its natural expiry. The blast radius
  of skipping this is bounded: the tenant boundary still isolates every
  other tenant, and the erased tenant's own tables are now empty, so a stale
  tenant claim in an unrevoked session resolves to nothing. This is
  defense-in-depth, not a correctness fix, and the revoked session rows
  themselves are retained (session history, no PII beyond what a session row
  already carries).
- A consumer-side dedup-claims table (tracking which event ids a given
  consumer has already processed, with no `tenant_id` of its own and no
  foreign key into the event spine) is left in place, unswept, after a
  tenant's `domain_events` rows are purged: its rows carry a consumer name,
  an event id, and a timestamp, no PII, and no foreign key can be violated
  by leaving them orphaned. Documented, not treated as a leak.
- **The append-only guarantee on the audit log is not violated by erasure.**
  Whatever mechanism grants only insert-and-read to the ordinary request
  role on the tenant audit table (audit-log.md section 8) does not apply to
  the privileged role that performs migrations and retention purges - it is
  the same privileged role, doing the same kind of maintenance work, that
  now also performs a lawful erasure. Append-only binds the request path; it
  does not bind the control plane doing a documented, audited erasure.
- Cross-module delete ordering is not guaranteed FK-safe purely by whatever
  order modules happen to register their declarations in (a registration
  order is a wiring detail, not a contract). It is safe as long as no
  foreign key crosses a module boundary - every FK stays intra-module (role
  assignments and role permissions pointing at roles, team members pointing
  at teams, and so on). A future cross-module foreign key needs an explicit
  ordering mechanism (a declared priority per contributor), not reliance on
  registration order; call this out in the declaration port's own
  documentation so it is never silently assumed.

## 5. The hard-delete operation

A platform-only endpoint, `POST .../platform/tenants/{tenantId}/erase`,
gated by the platform-admin check (multi-tenancy.md section 13), accepting
an optional `force` flag:

**All steps run in ONE transaction on the privileged connection, committed
once**, so an erased tenant can never exist without its audit record, and no
concurrent status change can race the purge. This matches every other
control-plane write in a well-built system (granting or revoking a platform
admin, impersonation, catalogue edits all commit state and audit together,
audit-log.md section 2).

1. Load the target tenant with a row lock (`select ... for update`, or the
   store's equivalent). The lock is essential: once `deleted -> active`
   reactivate exists (section 2), a concurrent reactivate could otherwise
   flip the tenant back to active between the retention check and the
   delete, erasing a just-restored tenant. The tenant MUST be
   `status = deleted` (otherwise refuse with a conflict), and either the
   retention window has elapsed or `force` is set (otherwise refuse with a
   conflict naming when the window elapses). A missing tenant is a
   not-found.
2. PRODUCE the final snapshot from the erasure declarations: for each
   declared table, read every row matching the tenant id into a raw
   snapshot, with every column marked sensitive (section 8) REDACTED. This
   is the operator's pre-purge compliance record; return it in the response
   so the operator captures it before the data is gone. It is a raw,
   per-table row snapshot, distinct from the shaped, per-section self-serve
   export in section 3 - one shaped for the subject, one raw for the
   operator, both drawn from the same tenant at the same instant.
3. ERASE via the central erasure service (section 4): the per-module
   declared deletes, plus the session revoke.
4. RECORD the erasure on the platform audit log (audit-log.md sections 2
   and 4: the same synchronous, transactional write pattern used for
   granting a platform admin or editing a catalogue) - the durable record of
   who erased which tenant, and when, on the log that is never purged by
   this operation. Then COMMIT.

A second erase attempt against an already-gone tenant is a not-found: the
row is gone, so there is nothing left to lock or check.

## 6. Events and audit

- The self-serve export emits a tenant-scoped, deliverable domain event
  (section 3): a bulk data access is worth auditing and worth a webhook.
  Payload: the actor and a per-section row-count summary, never a data copy.
- The hard delete records its own action on the platform audit log,
  synchronously, inside the erasure transaction (section 5, step 4). It is
  deliberately NOT a tenant-scoped domain event: a tenant-scoped event would
  ride the tenant's own outbox or audit log, which erasure is in the process
  of purging, so the record would be destroyed or left dangling mid-flight.
  The platform log is the correct, surviving home for a record of an action
  that erases the very mechanism a tenant-scoped event would ride.
- The existing soft-delete event is unchanged; `deleted_at` is now stamped
  alongside the status change, carried in the same event payload.

## 7. Individual-user DSAR (documented, not built)

The committed scope here is tenant-scoped: the tenant is the controller in
this B2B model, and an individual's request is served through their tenant
(the tenant admin runs the export or asks the operator to erase). A
per-USER export (one data subject's personal data across the tenant) and
per-user ERASURE are the natural next step and reuse these same seams:

- **Per-user export**: the export contributor port gains a user-filtered
  overload, so a contributor can return "this user's rows within this
  tenant" instead of the whole tenant's section.
- **Per-user erasure is anonymization, not deletion.** A user is a global
  identity shared across tenants (multi-tenancy.md section 1), so deleting
  their row outright would break referential integrity everywhere an audit
  actor id, a `created_by` column, or a membership row points at them,
  including in tenants that never asked for the erasure. The correct
  operation is a tombstone: overwrite the user's PII-bearing fields (email,
  display name) with a stable placeholder while retaining the user's id, so
  every reference that points at that id keeps resolving, just to an
  anonymized identity rather than a named person.

Both are deferred; the seam is intentional, not an oversight, and it is
worth naming explicitly so a future implementer does not have to rediscover
that per-user erasure needs a different verb (anonymize, not delete) than
tenant erasure does.

## 8. The secret-exclusion obligation, as a completeness mechanism

Some tenant-owned columns hold credential material and must never appear in
an export or a snapshot: a service-account credential hash, an encrypted
webhook signing secret, and whatever else a future increment adds (an SSO
client secret, an outbound API token). The self-serve export omits them by
shaping in each contributor (section 3); the operator snapshot redacts them
by name (section 5, step 2).

**Enforce this with a COMPLETENESS mechanism, not an enumerated test.** A
test that names today's two secret columns by hand cannot catch a THIRD
secret column a future increment adds: the fixed test keeps passing, and the
new secret leaks in both artifacts, silently, the moment the column is
added and nobody remembers to update the test's list. The fix is the same
shape as audit-log.md's own catalogue-completeness discipline (section 10):
mark every secret-bearing field with a "sensitive" marker at its
declaration, and add an automated, reflection- or introspection-based check
(whatever a stack's equivalent of a reflection scan is) that fails the build
if ANY marked field appears in either the export bundle or the operator
snapshot. A new secret column is then caught by construction - the check
walks every tenant-owned type looking for the marker, rather than a human
remembering to extend a hand-written list - the same "enumerate the
universe, not the known exceptions" discipline that keeps a catalogue
honest as it grows.

## 9. Residual references, honestly

Not every table that carries a tenant id is in the tenant-owned set that
erasure purges. A global session table is the example already worked
through in section 4: it is not tenant-owned (it belongs to the user
identity, which outlives any one tenant membership), but it can carry a
now-meaningless tenant id until the session ages out on its own. This is
acknowledged rather than hidden: erasure revokes live sessions as
defense-in-depth (section 4), and the residual reference's blast radius is
bounded, because the tenant boundary still isolates every other tenant and
the erased tenant's own data is gone, so a stale reference resolves to
nothing rather than to live data. A product built on this template should
audit its own event spine and any cross-cutting tables for the same shape
of residual reference (a tenant id that outlives the tenant for a
legitimate reason) and document each one the same way, rather than assuming
the declared tenant-owned set is automatically the complete set of every
table that ever mentions a tenant.

## 10. What is never purged

- **The platform audit log.** Operator actions, including the erasure
  action itself, are retained under a separate legal basis (the operator's
  own compliance record of its staff's actions, audit-log.md section 4) and
  are never in the tenant-owned set erasure sweeps. Purging the log that
  records an erasure, as part of that same erasure, would destroy the very
  compliance record the operation exists to produce.
- **Operator-owned catalogues.** The plans catalogue, the feature-flag
  catalogue, the permission catalogue, and any other global operator
  vocabulary (billing-and-entitlements.md section 2, feature-flags.md
  section 2) carry no tenant discriminator at all: erasing one tenant
  cannot touch rows that were never tenant-owned in the first place, and
  nothing in the declared tenant-owned set should ever be widened to
  include them.

## 11. Deferred (documented grow-into, not built)

- Async export to an object-store artifact with a signed, expiring download
  URL, for a tenant whose data is too large to assemble synchronously (the
  self-serve endpoint returns a job handle instead of the bundle).
- Per-user DSAR: user-scoped export and PII anonymization (section 7).
- A scheduled sweeper that hard-deletes tenants whose retention window has
  elapsed on its own, instead of an operator calling the endpoint (reuses
  the same erasure service).
- Export format negotiation (CSV/JSONL per section) and a documented schema
  for the bundle, for machine re-import elsewhere.
- Legal-hold: a flag that blocks erasure for a tenant under investigation,
  checked before step 1 of section 5.

## 12. Placement and deletability

The export contributor port, the erasure declaration port, the two central
services, and the two endpoints belong in the platform/shared layer, not
inside any business module - the identical placement argument audit-log.md
section 9, webhooks.md section 11, and quotas.md section 10 each make for
their own cross-cutting piece: both mechanisms consume every module's
declarations through a generic contract (a section name and a read
function; a table name and a key column), so neither depends on any
specific module's data, and the erasure service needs the same cross-tenant
privileged access the platform layer already owns and exposes to a small,
named set of platform operations (multi-tenancy.md sections 2, 13, and 16).
Placing either piece inside a business module instead would force that
module to invent its own version of a privilege that already exists in
exactly one place for exactly this reason.

Each module's own contributor and declaration implementations live inside
that module, next to the tables they describe - only the two central
services, the two ports, and the two endpoints are shared-layer concerns.

**Deletability**: drop the export contributor port, the per-module
contributors, the export service, and the export endpoint and its
permission atom; drop the erasure declaration port, the per-module
declarations, the erasure service, and the erase endpoint. Drop the
`deleted_at` column, the retention-window configuration, the two
event-spine indexes, and the sensitive-field marker plus its completeness
check. Two small edits are modifications rather than pure additions and
would need to be reverted, not just deleted, on removal: the `deleted ->
active` widening of reactivate, and the `deleted_at` stamping and clearing
in the soft-delete and reactivate paths. The rest of the offboarding
lifecycle (multi-tenancy.md section 17) is untouched. Nothing else
references export or erasure.

## 13. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(audit-log.md section 10; quotas.md section 11):

- **Erasure completeness.** Erasing a tenant leaves zero rows behind in
  EVERY declared tenant-owned table, across every module - not just the
  tables a hand-written test happens to check, but every table the
  declaration ports name, walked generically.
- **Cross-tenant safety.** Erasing tenant A leaves tenant B's rows fully
  intact, in every declared table - the single most important assertion in
  this whole document, since the privileged path that performs erasure has
  no isolation boundary of its own to fall back on.
- **Retention gate.** A tenant not yet in the `deleted` state cannot be
  hard-deleted; a `deleted` tenant inside its retention window cannot be
  hard-deleted without `force`; pinning the clock past the window allows the
  hard delete to proceed without `force`.
- **Recoverable reactivate.** A soft-deleted tenant inside its retention
  window can be reactivated, clearing `deleted_at`, and behaves as a normal
  active tenant afterward; a hard-deleted tenant cannot be reactivated at
  all.
- **Secret exclusion, as completeness.** Neither the self-serve export
  bundle nor the operator's pre-purge snapshot contains any field marked
  sensitive; adding a new sensitive-marked field to any tenant-owned type
  and re-running the check catches it without editing the test itself.
- **Atomic with audit.** A hard delete either fully erases the tenant and
  records the platform-audit row, or - on a forced failure partway through -
  leaves the tenant exactly as it was before the attempt, with no partial
  erasure and no audit row for an erasure that did not happen.
- **Concurrent reactivate cannot race the purge.** Attempting a reactivate
  and a hard delete against the same tenant at the same time resolves to
  exactly one winner: either the tenant is reactivated and the erase then
  fails its state check, or the tenant is erased and the reactivate then
  fails to find it - never a tenant left active with its data already
  purged, and never a hard-deleted tenant reachable at all afterward.
- **Export gating.** A tenant admin or owner can self-serve the export; a
  plain member is refused; a service-account credential is refused
  regardless of its granted permissions, since the export permission is
  never service-account-grantable.
- **Erasure gating.** Only the platform-admin check admits a caller to the
  erase endpoint; a tenant admin, however senior within their own tenant, is
  refused.
