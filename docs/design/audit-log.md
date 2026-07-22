# The audit log: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a first-class, queryable audit log grows out of the multi-tenancy control
plane in [docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into
bullet in that doc's section 18): adapt the specifics to your stack, or skip
it if your product's audit needs are simpler. Docs-first applies here too
(see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It builds
directly on multi-tenancy.md's event/outbox spine and platform super-admin
plane; read that doc's section 3 (the single choke point that sets the
tenant), section 4 (the async consumer path gets the same isolation as
requests), section 13 (the platform super-admin plane and audited
impersonation), and section 14 (data model) first. Being a generic
reference, it carries no build-sequence section (a concrete product's own
design doc would): treat every part as a menu, adopt the pieces your product
needs.

## 1. The decision, up front

- **The audit log is a queryable projection built off the event stream, not
  a new write path.** Every module already emits domain events onto the
  append-only event stream and, when a consumer is registered for a given
  event type, onto the outbox. The audit log is a consumer that projects
  those events into a table shaped for the two questions an audit log
  answers: "who did what, to what, and when, in my tenant" and, for the
  platform operator, "what did my staff do across tenants." This is the
  industry-standard shape: Stripe, GitHub, and AWS (CloudTrail) all expose
  an audit trail as a queryable projection distinct from the raw event
  stream, with the raw stream retained underneath as the source of truth.
- **Two scopes, because there are genuinely two audiences.** A TENANT audit
  log records actions inside one tenant, readable by that tenant's own
  admins and, cross-tenant, by the platform operator - this mirrors a
  GitHub organization's audit log. A PLATFORM audit log records
  platform-staff actions that are not scoped to any one tenant (granting or
  revoking a platform admin), readable only by the platform operator - this
  mirrors GitHub's enterprise audit log, or an AWS organization trail
  sitting above each account's own CloudTrail. Keeping them separate is not
  extra work for its own sake: the two logs have different readers,
  different isolation requirements, and different retention rules, and
  folding them into one table would either leak platform-staff actions to
  tenant admins or force every tenant row through a platform-only gate.
- **The tenant audit log sits under the same authoritative boundary as
  every other tenant table.** It carries the tenant discriminator
  (multi-tenancy.md section 2) and is enforced by the identical mechanism,
  so a tenant admin reading their audit log is bound by the same boundary
  as every other tenant read, not a bespoke filter written just for this
  feature. If your isolation mechanism is database row-level security, the
  tenant audit table is very likely the first RLS-bearing table living
  alongside otherwise platform-only tables, and that is worth calling out
  explicitly wherever your platform-vs-tenant table split is documented (a
  "platform tables carry no tenant discriminator" note gains a named
  exception).
- **The impersonation grant is the first audited action, end to end.** It
  already emits start and end events carrying the target tenant
  (multi-tenancy.md section 13), so the moment the audit consumer ships, an
  operator impersonating a user lands a row in that tenant's audit log with
  no further wiring. That was the point of emitting the event when
  impersonation was first built: an audit log is worth little if its first
  and most sensitive action needs new plumbing before it shows up in it.
- **Append-only, integrity over convenience.** Audit rows are inserted,
  never updated or deleted by the application. The natural primary key is
  the source domain event's id, which makes the projection idempotent under
  the outbox's at-least-once delivery for free: a redelivery is a
  primary-key no-op, not a duplicate row. Retention and purge are an
  operator concern (section 8), run on the bypass path, never an
  application-level mutation.

## 2. What is audited, and on which path

Audit entries come from two paths, matching the two scopes.

**Tenant scope: an asynchronous projection off the event stream.** A
consumer subscribes to the tenant-scoped event catalogue: every event type
that carries a tenant id (tenant, membership, invitation, workspace, team,
role, and role-assignment lifecycle events; the tenant-scoped half of the
impersonation events; and whatever business-module events your product
decides belong in the audit trail). Per multi-tenancy.md section 4, the
dispatcher sets a consumer-scoped tenant context from each event's own
tenant id before the consumer opens its unit of work, and the same choke
point that binds every request to its tenant (section 3) applies here too.
So the consumer writes under that tenant's context and the boundary stamps
the row to exactly one tenant: no bypass, no cross-tenant write. The audit
consumer is an ordinary tenant-scoped consumer, not the marked,
legitimately-cross-tenant exception section 4 calls out for a small named
set of platform consumers.

**Platform scope: synchronous, transactional, at the action site.**
Platform-admin actions that carry no tenant id at all (granting or revoking
a platform admin) are deliberately NOT routed through the tenant-scoped
consumer. A null-tenant event has nothing for the dispatcher to set a
tenant context from, and an insert attempted into a tenant-isolated table
with no tenant context set would, correctly, fail the boundary's check.
That failure is a feature, not a bug to route around: it is the isolation
mechanism doing exactly its job on a row that does not belong in a tenant
table. So instead of forcing a null-tenant event through the tenant path,
these actions write directly to the platform audit log, in the same
transaction that performs the grant or revoke, at the point in the code
where the action happens. Writing the audit row transactionally with the
action it records is strictly stronger than an eventual projection for the
highest-sensitivity actions in the system: there is no window where the
grant exists but its audit row has not landed yet.

Two constraints keep this correct rather than merely convenient. First, the
audit write sits inside the same guard that decides whether the action
actually took effect: a repeat grant of an existing admin, or a revoke of
someone already revoked, is a no-op that changes nothing and emits nothing,
and the audit row is written only on the branch where the action really
happened, sharing its id with the emitted event. There is never an audit
row without a real action behind it, and never a duplicate. Second, the
code that performs the platform action often lives in a different module
than the one that owns the platform audit table (in the reference case, a
tenancy/admin module calling into a platform module); it should not
hand-roll the insert against another module's table. It calls a narrow,
platform-owned write interface, passing its open transaction, so the column
list and the table itself stay owned in one place even though the call
site lives elsewhere.

**Identity and sign-in traffic is deliberately NOT folded into this audit
log.** Registration, sign-in, sign-out, and session events are
user-activity signals, valuable in their own right, but they belong in a
separate security-events or login-history feature projecting them into
their own table, not in the administrative audit trail. Folding raw sign-in
traffic into the admin audit log is below the bar: high-volume, low-signal
events drown out the comparatively rare administrative actions an auditor
is actually looking for. GitHub and AWS both keep sign-in/session activity
logs distinct from the administrative or organization audit trail for the
same reason.

## 3. The tenant audit log

One row per audited domain event, tenant-owned and under the same
authoritative boundary as every other tenant table. Its shape:

- **id**: the source domain event's own id, used as the primary key (this
  is what makes the projection idempotent - section 5).
- **tenant id**: not null, the isolation discriminator, stamped from the
  event, never chosen by the consumer.
- **occurred at**: the event's own timestamp, i.e. when the action
  happened.
- **recorded at**: when the projection wrote the row, i.e. when it was
  observed. The two can differ under redelivery or a processing backlog,
  and both are worth keeping.
- **action**: the event type, e.g. `tenancy.member.role_changed`, a stable
  string an auditor or a filter can match on, including by dotted prefix.
- **actor**: the acting user's id from the event, null for a
  system-initiated action.
- **entity**: the primary subject id the action was about.
- **summary**: a short, human-readable rendering of the action, built from
  the action type and a few well-known fields, bounded and non-PII.
- **data**: the event payload, essentially verbatim - ids and scalars only,
  never PII, inheriting whatever "no PII on the event stream" discipline
  your event catalogue already enforces.

Index the reverse-chronological feed (tenant, then time, descending) as the
default read path, and the two common filters (tenant plus actor plus time,
tenant plus action plus time) alongside it; this is the same kind of
keyset-friendly indexing every other list read in the product needs.

**There is deliberately no workspace-scoped filter column.** If no domain
event in your catalogue carries a workspace id in its own payload today (as
is the case in the reference build: workspace lifecycle events put it in
`entity`, and workspace-scoped role grants drop the scope id from the
payload entirely), a workspace-id column on the audit log would be
permanently null and would advertise a filter that does not actually work.
That is worse than not having the column: a caller sees a filterable field
and gets silence back. Workspace-scoped audit filtering is a documented
extension, not a missing feature: it needs the relevant event payloads
enriched with their workspace id first, and the column and index added
after, mirroring multi-tenancy.md section 7's own rule that a scope only
gets a column once something actually populates it. In the meantime, a
workspace lifecycle action is still findable by its `entity` id.

## 4. The platform audit log

One row per platform-staff action that is not scoped to a tenant, not under
the tenant boundary at all (there is no tenant to scope it to), readable
only through the platform super-admin plane. Its shape mirrors the tenant
log with the tenant discriminator removed and the subject reframed as a
user rather than a generic entity:

- **id**: the source domain event's id.
- **occurred at** / **recorded at**: as above.
- **action**: e.g. `platform.admin.granted`.
- **actor**: the platform staff member who acted.
- **subject**: the user the action was about.
- **summary** / **data**: as above.

Because this table is written only from an allowlisted, transactional call
site (section 2) and read only behind the platform-admin check, it needs no
tenant discriminator and no isolation-boundary machinery. Keep the same
discipline of writing through a single, narrow, platform-owned interface
even where multiple call sites across modules need to write to it, so the
column list and any future field additions stay owned in one place.

## 5. The projection consumer

The audit consumer is an ordinary tenant-scoped event consumer, run under
whatever consumer or worker mechanism your outbox uses (multi-tenancy.md
section 4). For each delivery:

1. The dispatcher has already bound the unit of work to the event's tenant
   and set that tenant's context (multi-tenancy.md sections 3 and 4). The
   consumer maps the envelope into an audit row (id equals the event id;
   tenant, actor, occurred-at, action, and payload copied; summary
   rendered). If the consumer cannot depend on every module's typed event
   payloads (a common shape when the audit feature is owned by a
   cross-cutting layer that must not depend on business modules - section
   9), read the payload as untyped structured data (a generic traversal of
   the JSON, or your stack's equivalent) rather than a typed
   deserialization, and render the summary from the action string plus
   whatever well-known scalar fields are present, tolerating their absence.
2. It inserts the row. The isolation boundary stamps and confirms the
   tenant id. A redelivery of the same event hits the same primary key and
   is rejected as a duplicate-key violation, which the consumer treats as
   success: the row is already there. This is idempotent by construction,
   and it is the correct dedup shape for an audit write specifically.

**Why "mark processed" dedup is the wrong tool here.** A common pattern for
consumer idempotency is a separate "processed event ids" table: check it,
do the work, then record the id as processed, sometimes in a second
transaction from the write itself. That shape is fine for work whose only
requirement is "don't repeat the side effect," but it is the wrong tool for
an audit write, because a claim that commits separately from the write it
guards can drop the record entirely: crash between the write and the claim,
and a naive retry either produces a second row (the claim looks missing) or
skips recording the write at all (some other check makes it look already
done), quietly losing the entry to under-application on the next pass. An
audit log cannot tolerate either failure mode: a duplicate mildly annoys a
reader, but a silently dropped entry is a hole in the compliance record
that nobody discovers until an auditor asks about it. Making the source
event id the row's own primary key removes the two-step race entirely: the
write and the dedup are the same atomic operation, enforced by the
underlying store, not by application bookkeeping that can desync from the
data it is supposed to protect.

The consumer only starts receiving events from the moment it is registered:
events emitted before it existed have their row on the underlying event
stream but were never delivered to it. That is expected and worth
documenting rather than treating as a bug: the audit log begins when it is
turned on, and history before that point still lives on the immutable
event stream underneath it.

## 6. Reading the audit log

**The tenant-admin read** is scoped to the caller's own tenant
automatically, by the same isolation boundary as every other tenant read -
there is no tenant parameter for the caller to supply or for the boundary
to trust. It is gated by a permission (section 7), and supports the filters
an auditor actually needs: actor, action (exact match or dotted-prefix
match, so `tenancy.member.` matches every membership action), entity, and a
time range, with keyset pagination on occurred-at and id - the same
pagination contract every other list read in the product should already
use.

**The platform-operator read** runs on the bypass path (multi-tenancy.md
section 13), so it can cross tenants: a tenant filter narrows to one
tenant, and omitting it returns entries across every tenant, which is the
compliance-wide view a platform operator occasionally needs. A separate
scope selector switches the same read between the tenant-log projection and
the platform log (section 4), rather than exposing them as two entirely
unrelated features.

**Reads are not re-audited by default.** Everything a platform operator
reads through the audit log is itself, in principle, an operator action,
but logging every read would double the write volume for a feature whose
whole point is to be read often by the people entitled to read it. Treat
"audit the audit reads" as a documented, off-by-default extension: turning
it on is a retention-and-volume decision for a specific compliance need,
not a correctness fix the base design is missing.

## 7. Permissions

Gate the tenant-admin read behind one permission atom (`audit:read` in the
reference build), added to the closed permission catalogue and to the
default admin role set (multi-tenancy.md section 8), so tenant admins and
owners can read their own audit log and ordinary members cannot. Because it
is an ordinary permission atom, it composes with the rest of the RBAC model
for free: a tenant can mint a read-only "Auditor" custom role holding only
`audit:read`, with no platform operator in the loop (section 10).
Platform-operator audit access is orthogonal to all of this: it is gated by
the platform-admin check (section 13), never by a tenant permission, since
a tenant permission system has no way to grant cross-tenant access in the
first place.

## 8. Append-only enforcement, retention, and tamper-evidence

**Append-only enforced at the data layer, not just in application code.**
Application discipline ("we just never call update or delete on this
table") is not append-only; it is a convention that an injected query, a
forgotten filter, or a future contributor can break without anything
stopping them. The bar an audit log needs to clear is the one compliance
frameworks check for directly (SOC 2, PCI-DSS): the ordinary application
role should be granted only the ability to read and insert on the tenant
audit table, and nothing at all on the platform audit table; delete and
update stay reserved to a separate, privileged role used only for
migrations and operator-run retention jobs. This is the same posture AWS
recommends for a CloudTrail log bucket (a bucket policy that denies delete
even to the account root) and what WORM (write-once-read-many) storage
enforces at the storage layer: the guarantee has to live below the
application, or it is not really a guarantee. With that grant structure in
place, an attacker who reaches request-role SQL through an injection or a
forgotten filter still cannot edit or erase the tenant audit trail, and
cannot see or forge the platform audit trail at all, because the request
role has no privilege on it whatsoever.

If your platform provisions the application's database role with a blanket
grant (common when a migration tool grants broadly per schema and relies on
narrower per-table revokes layered on top), make sure the audit tables'
restrictive grants are applied AFTER that blanket grant, and re-applied on
every provisioning run, so a future broadening of the blanket grant does
not silently widen the audit tables back open. An audit log that is only as
append-only as the last migration happened to leave it is not reliably
append-only.

**Retention is an operator job, run on the bypass path.** A documented
retention window (a concrete number, for example 400 days for the tenant
log, beats "we retain it as long as we need to," which is not a policy an
auditor can check) is enforced by a purge job running as the bypass role,
the only principal allowed to delete audit rows at all. That purge is
itself worth recording in the platform audit log: a retention job is still
an action someone should be able to account for later. Per-tenant retention
overrides are a natural fit for a billing/entitlements layer if your
product has one (a higher plan buys a longer window), the same way GitHub
and similar platforms tie audit-log retention length to plan tier.

**Tamper-evidence is a documented grow-into, not built on day one.**
Append-only plus database-enforced least privilege is the correct bar for
an MVP audit log; it is not the same guarantee as cryptographic
non-repudiation, and some customers (regulated industries especially) will
eventually ask for the stronger one. The append-only table is the right
foundation to grow that on top of without a schema rewrite: a hash chain,
where each row carries a hash of the previous row for its tenant (the same
idea behind certificate-transparency logs and Git's own commit chain), or
periodic anchoring of a rolling hash to an external, independent notary or
ledger. Both layer onto an append-only table; neither is buildable on top
of a table the application can freely update.

## 9. Placement and deletability

The audit log lives next to the event-stream/outbox mechanism it projects
from, not inside a business module and not as its own top-level module. It
is a cross-cutting concern in the same sense observability or rate limiting
is ([docs/process/04-architecture-principles.md](../process/04-architecture-principles.md)):
it consumes every module's events through a generic envelope (an event-type
string plus a payload), so it depends on no specific module, and its
platform-scope half needs the same cross-tenant read privilege the
platform/control-plane layer already holds. Placing it inside a business
module instead would force that module to invent its own version of the
platform's cross-tenant read privilege, duplicating a mechanism that
already exists in exactly one place for exactly this reason.

The cost of this placement is that the tenant audit table is very likely
your platform/shared layer's first tenant-owned, isolation-bound table, if
everything else there is deliberately kept tenant-agnostic. That is a
deliberate, documented exception, not drift: the tenant audit log has to be
bound by the same authoritative boundary as every other tenant read, full
stop, and if your platform layer carries a design note asserting "nothing
here is tenant-owned," that note is what needs updating to name the audit
log as the one exception, not the audit log that needs to bend to keep the
note true.

**Deletability**: the whole feature comes out cleanly by dropping the two
tables, the consumer registration, the two read paths (tenant and
platform), and the `audit:read` permission atom, leaving the event stream
(the actual source of truth) completely untouched. That untouched event
stream is what makes the audit log addable as a bolt-on in the first place:
turning it on or off changes nothing about what modules emit or how they
emit it.

## 10. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring multi-tenancy.md section 15's
own framing:

- **Isolation.** A tenant admin reading the audit log sees only their own
  tenant's rows; a second tenant's actions never appear - the same
  assertion the rest of the tenant tables already carry, applied here.
- **The projection is real and idempotent.** A tenant action (change a
  member's role, say) produces exactly one audit row keyed to the source
  event's id; a forced redelivery of that same event produces no second
  row.
- **Impersonation is audited end to end.** Starting an impersonation
  session against a target tenant lands a row in THAT tenant's audit log,
  visible to that tenant's own admin, with the operator recorded as the
  actor.
- **Platform actions are audited transactionally.** Granting a platform
  admin writes a platform-audit row in the same transaction as the grant; a
  grant that rolls back leaves no audit row behind.
- **Permission gate.** A caller without the audit-read permission is
  refused on the tenant audit read; an admin succeeds; a custom role
  holding only that permission succeeds on reads and is refused on
  everything else.
- **Platform-operator cross-tenant read.** A platform operator reads across
  every tenant and, with a tenant filter, narrows to one; a non-operator is
  refused.
- **No-PII discipline.** The projected payload is the event payload
  verbatim, so whatever "ids and scalars, never PII" rule the event stream
  already enforces is inherited here, not silently re-violated by a summary
  field that renders more than it should.
- **Catalogue completeness.** Every event type your catalogue defines is
  either subscribed by the audit consumer or explicitly, by name, marked
  "not audited" (identity/session events, and the null-tenant platform
  actions that are audited synchronously instead). A new event type that is
  neither should fail some check before it reaches production - a
  reflection or introspection test if your stack supports one, a lint
  rule, or a checklist item in the PR template if it does not - closing the
  "silently unaudited event type" gap.
- **Append-only is enforced below the application.** After ordinary
  provisioning, an attempt to update or delete a tenant-audit row as the
  application's own role is rejected by the data store itself, not merely
  absent from the API surface, and that same role has no access whatsoever
  to the platform audit table.
