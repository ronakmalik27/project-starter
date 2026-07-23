# In-app notifications: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a per-recipient in-app notification inbox grows out of the multi-tenancy
control plane in [docs/design/multi-tenancy.md](multi-tenancy.md) (the
grow-into bullet in that doc's section 18, "In-app notifications"): adapt
the specifics to your stack, or skip it if your product has no need for an
in-product inbox. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the
eighth worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), [quotas.md](quotas.md), and
[data-export-and-erasure.md](data-export-and-erasure.md).

It is the closest sibling to the audit log: read audit-log.md sections 2 and
5 first. Both are consumers that project the same event stream into a table
shaped for a reader; the audit log answers "who did what, across the whole
tenant," a notification answers "what happened to me." Where they answer
that question differently is the whole design: the audit log subscribes to
every tenant-scoped event and keys its dedup on the source event id alone
(one row per event, full stop), because it is the comprehensive projection.
A notification only makes sense for an event that names one clear
recipient, so it subscribes to a small curated set and keys its dedup on
the (event, recipient) pair, because it is the targeted projection - the
same pattern, aimed at one person instead of the whole audience. It also
builds on multi-tenancy.md's isolation boundary (section 2), its single
choke point that sets the tenant (section 3), its consumer-path isolation
(section 4), and its thin token carrying one active tenant at a time
(section 5); read those first. Being a generic reference, it carries no
build-sequence section (a concrete product's own design doc would): treat
every part as a menu, adopt the pieces your product needs.

## 1. The decision, up front

- **A notification is a targeted projection of a domain event, not a new
  write path.** The event already happened and is already on the outbox; a
  domain-event consumer turns a curated subset of events into per-recipient
  inbox rows, the same shape as the audit projection (audit-log.md section
  2) but keyed on one recipient user instead of the whole tenant. Nothing
  new is emitted. Notifications ride the existing consumer spine - the same
  dispatcher, the same tenant-context binding, the same outbox delivery
  guarantees every other consumer already gets (multi-tenancy.md section
  4).
- **Two channels, one concept; in-app is what this document adds.** A
  typical product's identity module already emails a user off certain
  events (a password changed, a sign-in from an unrecognized device) through
  an existing domain-event consumer that sends transactional email - that is
  the EMAIL channel, and it already demonstrates the general pattern this
  document extends: react to an event, tell the person it happened to. This
  document adds the IN-APP channel: a persisted inbox the user reads through
  an API, alongside the email that already goes out. A per-user, per-type
  channel PREFERENCE (in-app vs. email vs. both vs. off) is a documented
  grow-into (section 7), not built here; the two channels are independent
  consumers today, and neither asks the other whether it should fire.
- **Notifications are TARGETED; the audit log is COMPREHENSIVE.** The audit
  projection subscribes to every tenant-scoped event. A notification only
  makes sense when an event has a clear single user it happened TO, so the
  notification consumer subscribes to a small curated set (section 3), not
  the whole catalogue. Most events (a workspace renamed, a plan changed)
  have no one natural recipient and are deliberately not notified in-app -
  that is a design choice, not a gap to close later.
- **The inbox is per (user, active tenant).** A user can belong to many
  tenants (multi-tenancy.md section 1); a notification is created within one
  tenant (it is tenant-owned, under row-level security like every other
  tenant table), and a reader sees only their own notifications within the
  tenant they are currently acting in - the tenant named by their token's
  active-tenant claim (multi-tenancy.md section 5). This matches the
  one-tenant-at-a-time session model the rest of the product already uses:
  there is no cross-tenant inbox view, the same way there is no cross-tenant
  request of any other kind.
- **Reading your own inbox needs no permission.** Any authenticated tenant
  member reads, counts, and marks read their own notifications. It is their
  own data, not an administrative capability, so the endpoints (section 5)
  gate on the tenant boundary plus authentication only, and filter every
  query and every write to the caller's own recipient id. No new permission
  atom is added to the permission catalogue (multi-tenancy.md section 8): a
  member can never see or touch another member's notifications, but not
  because a permission check stops them - the row-level isolation boundary
  scopes the tenant, and the recipient filter scopes the user, so another
  member's row is never in the result set to begin with.

## 2. Data model

One table, tenant-owned, under the same row-level-security boundary as
every other tenant table (multi-tenancy.md section 2: FORCE row-level
security, or your store's equivalent authoritative boundary). It lives in
the platform/shared layer next to the audit log and webhook tables (section
8), not inside any business module.

| column | type | notes |
|---|---|---|
| `id` | uuid | primary key, generated at insert time |
| `tenant_id` | uuid, not null | the isolation discriminator, stamped from the event's tenant context on write, never chosen by the consumer |
| `recipient_user_id` | uuid, not null | the user this notification is for, derived from the event by the per-type rule (section 3) |
| `source_event_id` | uuid, not null | the domain event this row was projected from; half of the dedup key |
| `type` | text, not null | the notification type; the source event's own type string, e.g. `tenancy.member.role_changed` |
| `data` | jsonb, not null | render fields - ids and scalars only, no PII, inheriting whatever "no PII on the event stream" discipline the event catalogue already enforces (the source payload is already PII-free) |
| `created_at` | timestamptz, not null | when the row was projected |
| `read_at` | timestamptz, null | null means unread; set once, when the recipient marks it read |

```sql
-- the dedup key: at-least-once redelivery of the same event re-projects the
-- same (event, recipient) pair and hits this constraint.
create unique index ux_notifications_dedup
    on notifications (source_event_id, recipient_user_id);

-- the inbox LIST read path: newest-first, keyset-friendly.
create index ix_notifications_inbox
    on notifications (tenant_id, recipient_user_id, created_at desc, id desc);

-- the unread-count and mark-all-read path: see below for why this is
-- PARTIAL rather than a plain index on the same columns.
create index ix_notifications_unread
    on notifications (tenant_id, recipient_user_id)
    where read_at is null;
```

- **The dedup key is the (source event, recipient) pair, not the source
  event id alone.** This is the one place this projection's shape differs
  from the audit log's: the audit log's primary key is just the source
  event id, because it writes exactly one row per event, always. Here, a
  single event MAY fan out to more than one recipient later (section 7's
  broadcast grow-into), so the key has to be the pair, not the event alone,
  even though every curated event type today resolves to exactly one
  recipient. A redelivery of the same event for the same recipient hits the
  unique index and is treated as success - the same idempotent-by-construction
  discipline audit-log.md section 5 argues for and rejects a separate
  "mark processed" table in favor of, applied here to a two-column key
  instead of a one-column one. Read that section's reasoning in full; it
  transfers unchanged.
- **The LIST index backs the ordinary inbox read**: newest-first, filtered
  to one tenant and one recipient, the same keyset-friendly shape every
  other list read in the product should already use (occurred-at-and-id
  descending, so a cursor pages without gaps or duplicates as new rows
  arrive).
- **The PARTIAL "unread" index is what keeps a polled badge cheap, and it is
  worth explaining why it is partial rather than plain.** The unread-count
  endpoint (section 5) is designed to be polled every few seconds to drive a
  badge, and the inbox is append-mostly with no purge (section 7): nothing
  deletes old, read notifications. An index on `(tenant_id,
  recipient_user_id)` covering EVERY row would let a count-of-unread query
  find the right rows, but a plain covering index still has to skip past
  every already-read row that shares the same tenant and recipient to
  count only the unread ones, and that skipped set only ever grows over an
  account's lifetime. A `where read_at is null` partial index instead
  contains only the rows that are currently unread, and unread rows are
  self-limiting: a user who reads their notifications removes them from the
  index by the same action that satisfies them, so the index stays small
  regardless of how long the account has existed or how much history has
  piled up underneath it. This is the standard skewed-nullable-flag idiom
  (the same shape as an "active session" or "pending job" partial index):
  index the sliver that is queried constantly, not the whole table it lives
  inside.
- **This table is NOT append-only enforced the way the audit log is.** The
  audit log restricts its ordinary application role to insert-and-read only
  (audit-log.md section 8), because nothing should ever mutate an audit
  row. This table's `read_at` column is legitimately mutated by the
  recipient's own mark-read request (section 5), so the ordinary
  request-role grant here is the normal one: insert (the consumer), and
  read plus a narrow update (the recipient, under the recipient filter). Do
  not copy the audit log's restrictive grant onto this table by reflex; it
  would break mark-read.

## 3. The projection consumer

A domain-event consumer, the same shape as the audit projection
(audit-log.md section 2 and 5): it references no business-module type,
reads the event payload as untyped structured data, resolves the
request-style, RLS-bound data context (never the privileged bypass path),
and relies on the dispatcher to have already bound the unit of work to the
event's own tenant (multi-tenancy.md section 4) before it opens. Two things
make it different from the audit projection, both deliberate.

**First, it is a pure in-process write, not an outbound call.** Projecting
a notification is one insert against the tenant's own database, nothing
more - no HTTP call, no provider timeout, no retry-with-backoff logic. This
is the same shape as the audit projection and the webhook fan-out stage
(webhooks.md section 3: writing the delivery row, not sending it), and it
is a meaningfully different shape from the EMAIL channel (section 1), which
makes an outbound call to a mail provider and needs its own timeout and
retry handling because that call can be slow or fail independently of the
database. Keep these as separate consumers reacting to overlapping events,
never one consumer that does the in-process write and then the outbound
call in sequence: a slow or down mail provider must never head-of-line-block
an in-app badge update that has nothing to do with it, and a fast in-app
write must never be delayed behind a slow send it does not depend on.

**Second, it subscribes to a small, curated set of event types, not the
tenant-scoped catalogue the audit log subscribes to.** Each subscribed type
carries an explicit rule mapping the event to a recipient and to the data
the notification renders:

| Event type | Recipient | Render data |
|---|---|---|
| `tenancy.membership.created` | the new member (the event's own actor) | the granted role |
| `tenancy.member.role_changed` | the affected member (a payload field, not the actor) | the new role |
| `tenancy.team.member_added` | the added user (a payload field) | the team id |
| `tenancy.ownership.transferred` | the new owner (a payload field) | the previous owner |

These are the event types that name exactly one clear recipient user.
Everything else in the catalogue - a workspace renamed, a plan changed, a
custom role edited - has no single natural recipient and is deliberately
left out; adding a type here is a product decision, not a mechanical
default. `tenancy.membership.removed` is also deliberately excluded: a
removed member can no longer see the tenant at all, so an in-app row they
can never read is pointless - an email is the right channel for that one
(section 7).

**Recipient resolution reads only the event itself** (its actor field, its
subject-entity field, and whatever scalar payload fields the type defines).
It does not query membership, does not resolve "every admin in this
tenant," and does not look anything up beyond the envelope it was handed. A
broadcast or a fan-out-to-many-recipients notification needs exactly that
kind of lookup, which is why it is a documented grow-into kept out of this
consumer (section 7): a projection that stays a pure function of its input
event is trivially testable and depends on no other module's data; one that
resolves recipient sets by querying another module's tables is a different,
heavier kind of component and deserves to be designed as one deliberately,
not backed into.

**Dedup**: insert the row; on the (source_event_id, recipient_user_id)
unique violation, treat it as success rather than an error (an
`on conflict do nothing` upsert, or catching the violation and returning
normally, are equivalent ways to express the same idempotent write - pick
whichever your stack's data-access layer makes more natural). This is
exactly the audit projection's construction (audit-log.md section 5),
applied to the two-column key section 2 explains.

## 4. The load-bearing subtlety: why there is no actor-exclusion check

**There is no "skip if the actor is the recipient" rule anywhere in this
consumer, and none should ever be added.** The recipient for a given event
is whatever that event type's rule (section 3) reads, full stop - that is
the entire recipient-resolution story. It is tempting to add a blanket
guard - "never notify someone about their own action" - because it sounds
like an obviously correct piece of hygiene, the kind of check a reviewer
might ask for on reflex. For this consumer, it would be a serious, silent
bug.

Look at what the actor actually IS for each curated type. For the three
admin-driven events (a role changed, a team membership added, ownership
transferred), the recipient is read from a payload field naming the
AFFECTED user, which is inherently a different person from the acting
admin - most products already reject a self-targeting change of this kind
at the point the action is taken, so the recipient is never the actor there
regardless of any notification-side check. But for `membership.created`,
the recipient IS the actor: that event's actor field is the joining member
themselves (a self-service join or an invitation accept has no separate
"who added them" identity to name instead), and notifying them - "you
joined as {role}" - is exactly the intent of subscribing to that event type
at all. A blanket `if actor == recipient: skip` check would see that
identity, conclude "this looks like someone being notified about their own
action," and silently drop every `membership.created` notification forever
- not intermittently, not under some edge condition, but on every single
join, because that event's actor and recipient are the same person by
construction, every time.

The general lesson, worth carrying into any other curated notification
catalogue: "who is this for" is answered per event type by what actually
happened, never by a global rule comparing the actor to the candidate
recipient. Some event types are inherently about someone acting on someone
else (their recipient is never the actor); other event types are inherently
self-directed (their recipient is definitionally the actor). One project-wide
filter cannot be correct for both shapes at once, so do not write one - trust
the per-type recipient rule, and if a new curated type is ever added, ask
"who is the recipient for THIS type" on its own terms rather than reaching
for a shared exclusion helper.

## 5. The inbox endpoints

All four endpoints sit behind the tenant boundary and an authentication
check (an endpoint filter, or your framework's equivalent middleware - no
new permission atom, per section 1), and every one of them further filters
to `recipient_user_id = caller` under row-level security. Between the
tenant boundary and the recipient filter, another user's row - in this
tenant or any other - is never visible to begin with.

- **List, paginated.** The caller's notifications, newest first,
  keyset-paginated on `(created_at, id)` descending - the same pagination
  contract every other list read in the product should already use - with
  an optional filter to unread-only.
- **Unread count.** The caller's current unread total, meant to be polled
  every few seconds to drive a badge (the reason the partial index in
  section 2 exists).
- **Mark one read.** Sets `read_at` on one notification if it is currently
  null; idempotent, so marking an already-read notification read again is
  a no-op, not an error. If the given id is not the caller's own
  notification - it belongs to another user, or does not exist at all -
  the response is a plain not-found, never a forbidden. Row-level security
  plus the recipient filter make another user's or another tenant's row
  indistinguishable from a nonexistent one, so the honest response is the
  one that does not confirm the row exists in the first place; a forbidden
  response would leak that information instead.
- **Mark all read.** Flips every one of the caller's currently-unread rows
  to read in one statement, and returns the count it changed.

Marking read is a write the caller makes to their own rows: the
`recipient_user_id = caller` predicate on the update is the guard (a caller
can only ever flip their own rows), with the tenant's row-level-security
boundary underneath it as the layer that scopes everything to begin with.

## 6. What this is not

- **Not a message bus or a pub/sub layer between services.** That
  mechanism already exists - the domain-event stream and its outbox are the
  actual publish/subscribe spine (multi-tenancy.md section 4). This
  document is the human-facing inbox built on top of that spine, one more
  consumer among the ones already subscribed to it, not a second messaging
  mechanism alongside it.
- **Not real-time push.** The API is poll-based: the unread-count endpoint
  is designed to be polled to drive a badge, not pushed to a connected
  client. A live transport (WebSocket, server-sent events, or your stack's
  equivalent) is a documented grow-into (section 7); the persisted inbox
  this document builds is the source of truth such a channel would read
  from and publish out of, not something it would replace.

## 7. Deferred (documented grow-into, not built)

- **Per-user, per-type channel preferences** (in-app / email / both / off),
  read by both the in-app consumer and the email consumer before either one
  delivers, so a user can quiet one channel for a given event type without
  losing the other.
- **Broadcast / fan-out-to-many-recipients notifications** (notify every
  tenant admin of a plan change, every member of an announcement). This
  needs the consumer to resolve a recipient SET by querying membership,
  which couples it to the tenancy model the way section 3 explains this
  consumer deliberately does not - so it belongs behind a small, dedicated
  platform-owned lookup the consumer calls, rather than folded into the
  pure, module-free projection this document builds.
- **Real-time push** (WebSocket / server-sent events) reading the
  persisted inbox as its source of truth, rather than the client polling
  for it.
- **Email for the excluded events**, starting with `tenancy.membership.removed`:
  the removed user has no inbox left to read in that tenant, so an email is
  the only channel that can still reach them.
- **A retention / auto-purge policy** for old, already-read notifications;
  the inbox is otherwise append-mostly and unbounded, the same open item
  quotas.md section 9 and data-export-and-erasure.md section 11 each name
  for their own tables.
- **The quota limit-reached notice.** quotas.md section 9 explicitly defers
  its "you are near, or at, your usage limit" notice to this feature: a
  throttled notification (at most once per billing period), read directly
  off the usage-counter table rather than subscribed to an event, since a
  quota rejection is deliberately not itself a domain event (quotas.md
  section 8, to avoid flooding the event stream the moment a tenant sits at
  its ceiling and keeps calling).

## 8. Placement and deletability

The table, the consumer, and the inbox read/mark-read surface all live in
the platform/shared layer, not inside any business module - the identical
placement argument audit-log.md section 9, webhooks.md section 11, and
quotas.md section 10 each make for their own cross-cutting piece: the
consumer reads nothing module-specific (an untyped event envelope), and the
inbox itself depends on no business module's data. Placing it inside a
business module instead would tie a cross-cutting, product-wide feature to
whichever module happened to host it first, for no reason connected to what
the feature actually needs.

This table is one more addition to the small, deliberate list of
tenant-owned tables living inside an otherwise tenant-agnostic platform
layer, alongside the audit log and the webhook and usage-counter tables
(quotas.md section 10; feature-flags.md section 7; webhooks.md section 11
each name their own entries in this same list). A platform-layer design
note claiming "nothing here is tenant-owned" needs updating to name this
table too; the table itself needs no change to stay correct.

Projecting a notification emits nothing further: no new domain event, no
webhook, no re-entrant loop - it is a terminal projection, exactly like the
audit log. Marking a notification read emits nothing either; it is private
per-user inbox state, not a tenant event worth auditing or fanning out to a
webhook subscriber.

**Deletability**: drop the table and its migration, the projection
consumer's registration, the inbox read/mark-read surface, and the four
endpoints. The email channel is untouched: it predates this feature and
shares nothing with it beyond reacting to some of the same events. Nothing
else in the product references the inbox.

## 9. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring audit-log.md section 10's own
framing:

- **Projection per curated type, with the correct recipient.** Each curated
  event type produces exactly one notification, for the recipient section
  3's table names, with the right type and render data. Especially:
  `tenancy.membership.created` DOES notify the joining member - the
  actor-is-recipient case section 4 walks through, and the one a naive
  exclusion check would silently drop - and the three admin-driven event
  types notify the affected member, never the acting admin.
- **A non-curated event produces nothing.** An event type outside the
  curated set (a workspace renamed, say) creates no notification row at
  all.
- **At-least-once redelivery is idempotent.** Forcing a redelivery of an
  already-projected event does not create a second row for the same
  (event, recipient) pair; the unique index's violation is treated as
  success, not an error surfaced to the caller.
- **Cross-tenant isolation.** A caller acting in tenant A never sees a
  notification that was projected under tenant B, even for the same user
  id, the same isolation assertion every other tenant table already carries
  (multi-tenancy.md section 15).
- **Cross-user isolation, including the 404 behavior.** Within one tenant,
  user X never sees user Y's notifications in the list or the count, and
  marking read against another user's notification id returns a plain
  not-found (never a forbidden), leaving that row's `read_at` unchanged.
- **Mark-read and unread-count.** Mark-one and mark-all flip only the
  caller's own rows; the unread count reflects the change immediately
  afterward; marking an already-read notification read again is a
  no-op, not an error.
- **List pagination.** The keyset cursor pages the caller's inbox
  newest-first without gaps or duplicates as new rows are projected
  concurrently, and the unread-only filter returns exactly the rows with a
  null `read_at`.
