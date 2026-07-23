# Usage quotas: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a per-tenant, plan-driven usage-quota mechanism grows out of the
multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "Usage quotas"): adapt the specifics to your stack,
or skip it if your product has nothing worth metering or capping. Docs-first
applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the sixth
worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
and [feature-flags.md](feature-flags.md).

This document is the ENFORCEMENT half of a split billing-and-entitlements.md
draws: that document DEFINES and exposes a plan's numeric limits (a seat
limit, a maximum workspace count, and whatever else a plan wants to cap) and
says enforcing them - counting current usage against the limit and refusing
at the boundary - is "the usage-quota concern .. a separate grow-into
feature" (billing-and-entitlements.md section 6). This document owns that
enforcement. Read billing-and-entitlements.md first, sections 1 through 3
and 6 especially; a quota has no limit to check without a plan behind it.
It also builds on multi-tenancy.md's isolation boundary (section 2), its
tenant plan and seat-limit fields (section 14), and its row-locked seat
check in provisioning (section 12) - the one limit already enforced end to
end before this increment exists, and the closest thing to a prior-art
example for the resource-count half of this doc (section 6). It also
contrasts with feature-flags.md's fail-closed default (section 1): a quota
fails OPEN, the same direction as an entitlement but for a different reason,
worked through in section 1 below. Read those first. Being a generic
reference, it carries no build-sequence section (a concrete product's own
design doc would): treat every part as a menu, adopt the pieces your
product needs.

## 1. The decision, up front

- **A quota enforces a plan's numeric LIMIT; it is a commercial gate, so it
  FAILS OPEN, like an entitlement, not closed like a security gate.** A
  quota answers "have you used more of this than your plan allows." When
  the plan declares no limit for a metric, the metric is unlimited and the
  check is a no-op - the same fail-open default entitlements use
  (billing-and-entitlements.md section 1): an unconfigured tenant, or a
  tenant on a plan that names no limit for this metric, is never locked out
  of its own product. Enforcement engages only once an operator publishes a
  plan that names a finite limit for the metric.
- **Feature flags, entitlements, and quotas all resolve a per-tenant value on
  the request path, and look similar for that reason, but two of the three
  fail in opposite directions than the third on purpose:**

  | Mechanism | Answers | Fails | Why |
  |---|---|---|---|
  | Feature flag | is this turned on for you right now | CLOSED (off) | operational: an unresolved flag must never expose an unfinished or a deliberately killed feature (feature-flags.md section 1) |
  | Entitlement | does your plan include this at all | OPEN (available) | commercial: unconfigured must never lock out a tenant nobody meant to restrict (billing-and-entitlements.md section 1) |
  | Usage quota | how much of this have you used against your plan's ceiling | OPEN (unlimited) | commercial, same reasoning as an entitlement, applied to a number instead of a boolean |

  A quota is an entitlement's numeric sibling, not a flag's: both quota and
  entitlement gate a commercial boundary and both must leave a
  not-yet-configured tenant unaffected, while a flag gates an operational
  boundary and must default the other way. Getting a quota's default
  backwards - failing closed on an absent limit - would deny every tenant on
  every plan that has not yet named this specific metric, which is every
  tenant before an operator gets around to it.
- **Two kinds of quota, because SaaS products meter two different shapes of
  thing. This split is the key design decision in this document:**
  - A **resource-count quota** (a gauge) bounds how many of a thing may
    exist AT ONCE: workspaces, seats, webhook endpoints, service accounts.
    Enforced at CREATE time by counting the tenant's current rows and
    refusing at the ceiling (section 6). Not temporal: waiting does not
    free up a slot, so the honest answer is 402 Payment Required (upgrade,
    or delete something first).
  - A **metered quota** (a windowed counter) bounds consumption OVER A
    BILLING PERIOD: API calls, events processed, emails sent, jobs run.
    Enforced by an atomic counter incremented on use and compared against
    the limit (sections 3 and 4); it resets each period. Temporal, so the
    honest answer is 429 Too Many Requests with a `Retry-After` header (the
    period reset). This is the metered-billing shape Stripe usage records,
    Twilio, and the GitHub API all use.

  These are two distinct problem shapes with two distinct status codes.
  Do not conflate them under one error slug: a client that sees "quota
  exceeded" needs to know, from the type alone, whether the answer is
  "wait" or "upgrade or free something up" - two shapes of action that a
  single status code and a single retry policy cannot both drive correctly.
- **HARD enforcement (reject at the ceiling) is what ships; SOFT (allow the
  overage, record it, bill for it later) is a documented grow-into.** The
  metered counter records usage regardless of mode; hard mode adds the
  reserve-and-refuse (section 4). A soft/overage mode is the same counter
  without the guard clause, plus a billing hook - named in section 9, not
  built.
- **Limits are resolved from the tenant's plan, never hard-coded.** Both
  kinds read the tenant's resolved plan limits (billing-and-entitlements.md
  section 3): the maximum-workspace-count key for the resource gauge, an
  arbitrary metric key for a metered quota. A metric or resource key ABSENT
  from the plan's limits means unlimited (fail open) - this is a critical
  correctness point with a well-known trap, worked through in full in
  section 5, because it is easy to get backwards by accident.
- **Quotas are NOT the edge rate limiter.** A typical service already runs a
  rate limiter at the edge - a token bucket over seconds, keyed on the
  caller's IP or API key, indifferent to tenant or plan, there to protect
  the service from abuse. A usage quota is a different mechanism entirely: a
  per-TENANT, plan-driven count over a billing period, there to enforce a
  commercial ceiling. They are both throttles and they compose - an abusive
  caller is stopped by the edge rate limiter first, long before any single
  tenant's monthly counter would matter - but they answer different
  questions, key on different things (an IP or credential vs. a tenant id),
  reset on different clocks (seconds vs. a billing period), and share no
  mechanism. Treating a plan-driven monthly counter as if it were just a
  differently-configured rate limit bucket is a category error: a rate
  limiter has no concept of a plan, a period, or an upgrade path, and a
  quota has no concept of a request rate. If an earlier design note in your
  own docs describes usage quotas as "riding the rate limiter," that
  shorthand is superseded by this document.

## 2. Data model

One counter table, tenant-owned, under the tenant boundary (row-level
security with FORCE enabled, or your store's equivalent authoritative
boundary, multi-tenancy.md section 2). One row per (tenant, metric,
period) - the metered counter only. A resource-count quota needs no table
of its own: it counts the resource's own rows (section 6).

| column | type | notes |
|---|---|---|
| tenant id | not null | the isolation discriminator, stamped from the request-scoped, tenant-bound data context on write, never from client input |
| metric | not null, text | the metered metric key; matches a key in the plan's limits map |
| period start | not null, date | the UTC first-of-month anchor of the billing period (section 3) |
| used | not null, a wide integer type | consumption in this period; wide enough that a high-volume metric cannot overflow it |
| updated at | not null, timestamp | last increment |

- Primary key: (tenant id, metric, period start). Every column is not
  null, so a plain composite primary key is the natural upsert conflict
  target - no partial-index or nulls-distinct games are needed, unlike the
  scope-id null-collision problem multi-tenancy.md section 8 and
  feature-flags.md section 2 both solve for their own tables.
- Lives in the platform/shared layer next to the audit log and webhook
  tables (section 10), tenant-owned under the same boundary as every other
  tenant row. Unlike an operator catalogue (the plans catalogue, the
  feature-flag catalogue), this table takes no boot-time grant hardening:
  it is a normal request-path table, and a tenant's own request legitimately
  writes its own counter row under its own tenant context. There is nothing
  operator-owned here.
- Old-period rows are harmless history (a usage trend line, if your product
  wants one). Pruning them is an operator job (a documented grow-into,
  section 9); nothing reads a period other than the current one.

## 3. The period

- The billing period is the CALENDAR MONTH in UTC. The period start is the
  first of the current month at 00:00:00 UTC (a plain date, no time
  component); the reset instant is the first of the next month at
  00:00:00 UTC. A metered quota's window is `[period start, reset instant)`.
- Computed from an injectable clock abstraction, never a direct call to the
  platform's current-time function, so a test can pin the clock and cross a
  period boundary deterministically (assert a counter resets, rather than
  waiting on a real calendar).
- A per-tenant billing ANCHOR (align the reset to each tenant's own signup
  day, rather than the calendar) and ROLLING windows (a trailing 30 days,
  recomputed continuously rather than reset at a fixed instant) are
  documented grow-into (section 9), not built. Calendar-month matches the
  default billing cycle most payment providers use out of the box, and
  keeps the period key a stable, index-friendly date value.

## 4. The metered quota service

A small service, request-scoped, resolves the request-scoped, tenant-bound
data context (RLS-bound to the active tenant, the same context an
entitlement resolver or a feature-flag evaluator already uses). It owns the
counter mechanics only; it does NOT resolve the plan itself - the caller
passes the resolved limit in. This keeps the counter mechanism free of any
dependency on wherever the plan catalogue lives, the same separation of
concerns billing-and-entitlements.md section 10 already draws between its
entitlement resolver and its gates.

Two operations, conceptually:

- `try_consume(metric, amount, limit)` - attempt to reserve `amount` units
  of `metric` against `limit` for the current period; returns whether it
  was allowed, the current used total, the limit, and the reset instant.
- `get_usage(metrics)` - the current-period used total for each requested
  metric (zero for a metric with no row yet), for the usage report
  (section 7).

**`try_consume`, when the limit is absent (null/unlimited):** FAIL OPEN,
and this is a true no-op. It writes NOTHING - no counter row is inserted or
touched - and returns "allowed, used = 0, limit = none, reset instant".
A hard quota with no configured limit has nothing to enforce, and writing a
counter row on every request to an unlimited metric is pure write
amplification for a number nobody will ever check. (Metering usage WHILE
unlimited - writing the row anyway, so a later switch to overage billing has
history to work from - is SOFT mode, section 9, a deliberately different
and NOT-yet-built behavior. Do not blur the two: hard-mode-unlimited writes
nothing; soft mode is a different code path that writes unconditionally.)

**`try_consume`, when the limit is present:** HARD enforce with an atomic
reserve. Ensure the counter row for the current period exists, then apply a
GUARDED increment that refuses at the ceiling in the same statement that
performs it. On a Postgres-backed store this is one insert followed by one
guarded update, inside the same transaction:

```sql
insert into usage_counters (tenant_id, metric, period_start, used, updated_at)
values (@tenant, @metric, @period, 0, @now)
on conflict (tenant_id, metric, period_start) do nothing;

update usage_counters
   set used = used + @amount, updated_at = @now
 where tenant_id = @tenant and metric = @metric and period_start = @period
   and used + @amount <= @limit
returning used;
```

The `update` takes a row lock on the counter row, so concurrent requests
against the same (tenant, metric, period) serialize on it: there is no
separate check-then-act step for a race to slip between, so the reserve is
atomic and the limit cannot be oversold under concurrency. If the update
returns a row, the amount was consumed: "allowed, used, limit, reset
instant." If it returns ZERO rows, the increment would have breached the
ceiling, so nothing was consumed - the guard clause blocked the write
before it happened, not after - and the caller gets "denied, used (re-read,
unchanged), limit, reset instant." The tenant id is stamped from the
request-scoped context, and the tenant boundary rejects any attempt to
write under a different tenant.

`amount` must be positive; guard it at the service boundary (reject zero or
negative amounts outright, before any write is attempted).

`get_usage` is a plain read of the current-period `used` value per
requested metric, scoped by the tenant boundary like any other tenant read.

## 5. Enforcing a metered quota (the gate)

An endpoint filter or middleware, analogous to the permission gate and the
entitlement gate (multi-tenancy.md section 8; billing-and-entitlements.md
section 4), resolves the caller's plan limit for a metric and calls
`try_consume`.

**Resolving the limit is where the load-bearing trap lives, and it deserves
its own callout.** The plan's limits are a map from metric key to an
integer. Reading that map MUST distinguish "the key is absent" from "the
key is present with some value" - the two mean opposite things (unlimited
vs. a real ceiling), and a plan can legitimately set a limit of zero
(deny-all, no ceiling raised yet). A generic "get this key, or fall back to
a default if it's missing" helper - the kind of utility every stack ships
one flavor of - COLLAPSES that distinction the moment it is used here,
because it cannot express "the key was absent" as a return value distinct
from "the key was present and happened to equal the fallback." Whichever
way that fallback points, it breaks something:

- Fall back to `0`: every plan that has not yet named this metric now
  denies it outright - a metric-by-metric deny-all default that locks out
  every tenant on every plan an operator has not gotten around to yet, the
  exact failure mode section 1 rules out.
- Fall back to "unlimited": a plan that deliberately sets the limit to `0`
  (a genuine deny-all for that metric) is silently treated as unlimited
  instead, defeating a limit the operator explicitly configured.

The fix is to read the map with an operation that can answer "is the key
present" on its own terms - an optional/nullable lookup, a try-get that
returns a found/not-found flag alongside the value, or an explicit
contains-key check before reading - never a lookup-with-fallback. This is
not a hypothetical: it is the specific, well-documented shape of bug that a
convenient default-value helper invites, and it is worth a dedicated code
comment at the call site, not just a design-doc mention, because the next
person to touch this code will reach for the convenient helper by default.

Once the limit is resolved (present-with-a-value, or absent-meaning-none):

- Call `try_consume(metric, amount, limit)`.
  - Allowed -> the request proceeds.
  - Denied -> short-circuit `429 Too Many Requests`, a problem type
    dedicated to metered exhaustion (for example `quota-exceeded`) -
    distinct from the resource-count refusal's problem type in section 6,
    which uses `402` instead of `429`. Keep the two on separate slugs even
    though both are "a quota was hit": a client dispatching purely on the
    problem type must never have to also branch on the HTTP status to know
    whether the honest answer is "wait" or "upgrade." Set the
    `Retry-After` header to the whole number of seconds until the reset
    instant, clamped at zero (never negative). The problem detail names
    the metric, the limit, and the reset instant, so a client can back off
    precisely instead of guessing.
- **Composition order: cheap, read-only rejections run before the quota
  consume, because the quota consume is a WRITE.** Compose the gate chain
  as: the tenant-boundary and authentication checks first (a request with
  no resolvable tenant, or no valid caller, is rejected before anything
  else runs); then the permission check (an unauthorized caller is
  rejected next); then the entitlement check, if the route has one (a
  caller on a plan that does not include the feature at all is rejected
  next); then, LAST, the quota gate. Every one of the first three checks is
  read-only and answers a yes/no question with no side effect; the quota
  gate is the only step in the chain that writes anything. Putting it last
  means a request that was always going to be rejected - wrong permission,
  wrong plan - never burns a unit of the tenant's metered budget on its way
  to being rejected anyway. This is the same ordering discipline
  billing-and-entitlements.md section 4 and feature-flags.md section 4
  each establish for their own gate, extended one step further.
- Consuming a quota is a write. Apply the gate only to routes that should
  count against a metered budget, and count each qualifying request
  exactly once. A route that only reports usage (section 7) never carries
  this gate - reading your own usage must never itself consume budget.

## 6. The resource-count quota

- Enforced at the resource's CREATE path by counting the tenant's current
  rows of that resource and comparing against the resolved limit - the same
  absent-vs-present resolution as section 5, and the same trap: read the
  plan's limit for this resource with an operation that can say "absent,"
  never a lookup-with-fallback.
  - Absent -> unlimited (fail open); create proceeds unchanged.
  - Present -> count the tenant's CURRENT rows of the resource, under the
    tenant boundary; if the count is already at or above the limit, refuse
    before inserting the new row; otherwise create it. The count and the
    insert share one transaction, so the count that decides is the count
    at the moment of the decision.
- **Not temporal, so the honest response is different from the metered
  case.** Waiting does not free up a slot the way a metered window resets:
  the only way past a resource-count ceiling is to upgrade the plan or
  delete an existing resource. The response is `402 Payment Required`, a
  problem type dedicated to a resource-count ceiling (for example
  `resource-quota-reached`) - a DISTINCT slug from the metered `429` in
  section 5, on purpose (section 1's status-code split).
- **Concurrency is a judgment call, not a hard requirement.** A brief
  create-create race could in principle admit one resource over the
  ceiling under extreme concurrency, because counting current rows and
  then inserting is a check-then-act pair, not the single guarded statement
  section 4 uses for the metered case. For a resource that is created at
  human pace (a person clicking "new workspace," not a hot API path), this
  is an acceptable, documented trade-off, not an oversight. If your product
  already ships a seat-limit check (the prototype resource-count quota
  many products build first, and the closest prior art here), it likely
  already takes a row lock on the tenant row before counting, precisely
  because invitation-accept is a path worth making race-proof - re-check
  the count under that same lock, in the same transaction as the count and
  the create, if your product needs the hard guarantee for a given
  resource. This is named as a documented grow-into (section 9), not the
  default every resource gauge must take on day one.

## 7. The usage report

A single endpoint - the standard usage dashboard shape (Vercel, LaunchDarkly,
and most B2B billing UIs all ship one) - returns, for the active tenant
under the tenant boundary:

- **limits**: the plan's declared numeric limits, verbatim, so a client can
  render "X of Y" without a second call.
- **metered**: for each KNOWN METERED metric, its current-period used total,
  its limit (or none, meaning unlimited), and the reset instant. The metered
  set is a deliberate code-side list, NOT "every key in the plan's limits":
  a resource-count limit (a maximum workspace or seat count) belongs under
  `resources` below, with a real current count, never under `metered` with a
  meaningless zero that reads as "metered, no activity." The plan's limits map
  is flat (key -> number) and does not itself tag a key as metered vs.
  resource, so the application decides which keys are metered; a product adds
  a new metered metric by adding its key to that set. When the limit is absent
  the metric is unlimited and therefore NOT metered at all (section 4's true
  no-op), so its used total is always zero - surface that case explicitly as
  "not tracked," not as a bare zero that a client would misread as "no activity
  this period." A response consumer should key its rendering off "limit is
  absent," not off the used value.
- **resources**: the resource-count gauges - each as
  `{ metric, used, limit }`, current count vs. the resolved limit (or none).

This composes read-only from the plan's resolved limits (entitlements,
billing-and-entitlements.md section 3) and the metered service's
`get_usage` (section 4); neither source needs to know about the other.

## 8. Events and audit

- Quota consumption itself is high-frequency and is NOT a domain event; the
  counter row already is the durable state. Nothing is written to the
  event/domain-event stream on every consume - doing so would multiply a
  single metered request into an event per unit consumed, on the hottest
  path in this whole document.
- A quota REJECTION is a real business signal worth surfacing (an upsell
  moment, an alerting trigger), but emitting an event per rejection risks
  flooding the event stream the moment a tenant sits at its ceiling and
  keeps calling. So no dedicated "quota exceeded" event ships in this
  increment. The counter row already holds everything a notification needs
  to compute "you are at N percent of your limit"; a throttled "limit
  reached" notice (at most once per period, read directly off the counter)
  is the in-app-notifications feature's job (multi-tenancy.md section 18),
  reading this state rather than subscribing to an event - a documented
  hook (section 9), not a flood-prone event per rejection.
- **Plan-limit CHANGES are already audited elsewhere.** Assigning or
  editing a plan is a platform-audited operator action
  (billing-and-entitlements.md section 7): a tenant's effective limits
  change only through those already-audited operations, so there is no
  audit gap to close here - this document only enforces the limit that
  operation already recorded.

## 9. Grow-into (documented, not built)

- **Soft / overage mode**: the same counter, minus the guard clause, plus a
  billing hook that reports the overage to the payment provider (Stripe's
  usage-based billing is the reference shape). The counter is built
  soft-ready already - it records before the guard is even checked - so
  only the guard and the billing bridge differ between hard and soft mode.
- A throttled "limit reached" / "approaching your limit" (for example, 80
  percent) notification, at most once per period, read off the counter
  table by the in-app-notifications feature.
- Per-tenant billing ANCHOR (reset aligned to each tenant's own signup day)
  and ROLLING windows (a trailing N days), instead of the calendar month.
- Old-period counter PRUNING, a scheduled operator job, once usage history
  grows large enough to matter.
- A hard concurrency guarantee on the resource-count race (the row-locked
  count-then-create section 6 names), for a product that needs a given
  resource gauge to be race-proof rather than human-paced.
- More metered metrics and more resource gauges: the model is generic (any
  key in a plan's limits map), so a new quota is a new limit key plus a
  gate on the metered route, or a count-check at the resource's create
  site - no schema change either way.

## 10. Placement and deletability

The counter table, the metered quota service, the metered gate, and the
usage report endpoint belong in the platform/shared layer, not inside any
business module - the identical placement argument audit-log.md section 9,
webhooks.md section 11, billing-and-entitlements.md section 10, and
feature-flags.md section 7 each make for their own cross-cutting piece: the
counter mechanism reads nothing module-specific, and gating a metered route
depends on no particular module's data.

The counter table is one more addition to the small, deliberate list of
tenant-owned tables living inside an otherwise tenant-agnostic platform
layer that feature-flags.md section 7 and webhooks.md section 11 already
name (the audit log, the service-account table, the webhook tables, the
flag-override table). A platform-layer design note claiming "nothing here
is tenant-owned" needs updating to name this table too; the table itself
needs no change to stay correct.

The resource-count CHECK for a given gauge, by contrast, lives in the
module that owns that resource's create path (the workspace-create flow in
the tenancy module, the invitation-accept flow for seats) - it is not
itself a shared-layer concern, only the metered half of this document is.

**Deletability**: drop the counter table and its migration, the metered
quota service, the metered gate, the usage report endpoint, and the
resource-count check at each create site it was added to. If your product
already shipped a seat-limit check before this increment, it predates this
generalized model, is already its own race-proof path (section 6), and is
untouched by removing everything else here. Nothing else references
quotas.

## 11. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(billing-and-entitlements.md section 11; feature-flags.md section 9):

- **Fail open by default.** A metric or resource absent from a plan's
  limits passes every check, unmetered and uncounted; no counter row is
  written for an unlimited metric under any amount of traffic.
- **The absent-vs-present trap, caught explicitly.** A plan with a limit of
  zero for a metric refuses immediately, on the very first unit; a plan
  that simply omits the key stays unlimited. These two must never collapse
  into each other - test both against the same resolution code path so a
  regression back to a lookup-with-fallback fails a test immediately, not
  in production.
- **Atomic reserve under concurrency.** Firing many concurrent requests at
  a metered metric with a small limit consumes exactly up to the limit,
  never one unit over it, no matter how the requests interleave.
- **Metered exhaustion and reset.** Reaching the ceiling returns 429 with a
  `Retry-After` that reflects the real time to reset; pinning the clock
  past the period boundary and calling again succeeds, with the counter
  back at zero for the new period.
- **Resource-count ceiling.** Creating at the ceiling is refused with 402;
  deleting one existing resource and retrying succeeds.
- **Enforcement order.** An unauthorized caller is refused before any
  counter write happens; a caller whose plan lacks the entitlement for the
  route is refused (402) before any counter write happens; only a caller
  who clears both checks can consume metered budget, successfully or not.
- **Usage report accuracy.** The report's numbers match the counter table
  and the resource counts exactly; an unlimited metric reports "not
  tracked," never a bare zero that reads as "no activity."
- **Isolation holds.** Tenant A's counter is invisible to, and unaffected
  by, tenant B's consumption of the same metric - the same isolation
  assertion multi-tenancy.md section 15 runs for every other tenant table.
- **Distinct problem types.** The metered 429 and the resource-count 402
  carry different problem types; a client dispatching purely on type never
  needs to also branch on status to know which one it got.
