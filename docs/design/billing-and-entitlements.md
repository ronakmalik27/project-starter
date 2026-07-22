# Billing, plans, and entitlements: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a plan/entitlement model grows out of the multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "Billing (plans, subscriptions, seats, metering) and
entitlements"): adapt the specifics to your stack, or skip it if your product
does not sell tiered access. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the fourth
worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md), and
[webhooks.md](webhooks.md), and builds directly on all three: multi-tenancy.md's
tenant `plan` and seat-limit fields (section 14), its platform super-admin
plane (section 13), and its custom-role authoring guardrails (section 10,
which already reserves this exact seam as "a no-op filter until billing
exists"); audit-log.md's synchronous platform-audit write (sections 2 and 4)
and catalogue-completeness discipline (section 10); and webhooks.md's
outbound-webhooks feature, used here as the worked gating example (section
7) and as the contrast point for the inbound, provider-driven webhook this
document introduces in section 9. Read those first. Being a generic
reference, it carries no build-sequence section (a concrete product's own
design doc would): treat every part as a menu, adopt the pieces your
product needs.

## 1. The decision, up front

- **A plan is an operator-owned catalogue entry; a tenant is assigned one;
  a plan carries entitlements.** An entitlement set is three things: a
  feature set (which named capabilities the plan turns on), a
  grantable-permission set (which RBAC permission atoms, multi-tenancy.md
  section 8, a tenant on this plan may put into a custom role), and a
  collection of numeric limits (seats, and whatever else the product wants
  to cap). The operator defines the plans (free, pro, enterprise, ..); each
  tenant's assigned plan names one; the plan's entitlements answer "may this
  tenant use feature X," "may this tenant grant permission Y to a custom
  role," and "what is this tenant's limit for Z." This is the standard SaaS
  shape (Stripe Billing, every B2B tier page): the price tier maps to a
  capability set, and the app gates on the capability, not the price.
- **This is the entitlement model, not a payment processor.** Charging a
  card, running a subscription, prorating, invoicing, and dunning are a
  payment provider's job (Stripe, Paddle, Chargebee). The reusable,
  stack-defining piece is the plan/entitlement model and its enforcement;
  the provider is a plug-in that, on a successful checkout or a subscription
  change, drives the same assign-plan path a super-admin uses (section 8).
  That provider callback is an INBOUND webhook, not to be confused with the
  OUTBOUND webhooks of webhooks.md (there, the tenant registers a receiver
  and this product is the sender; here, the provider is the sender and this
  product is the receiver verifying the provider's own signature). Wiring
  one is a documented seam (section 9), the same posture SSO/SCIM take
  (multi-tenancy.md section 18).
- **Entitlement checks FAIL OPEN, unlike every security gate.** The
  permission gate and the tenant-isolation boundary fail closed: no proof,
  no access (multi-tenancy.md sections 2 and 8). Entitlements invert that on
  purpose, because they are a COMMERCIAL gate, not a security one: when
  billing is not configured at all - no plan on the tenant, an unknown plan
  key, or a plan that declares no restriction - every feature stays
  available. Failing closed here would lock every tenant out of every gated
  feature the moment the filter ships, before any operator has defined a
  single plan; a commercial gate with no plan configured has to leave
  everything available, or the mere act of shipping the filter would revoke
  access nobody meant to revoke. So the check is a no-op until an operator
  deliberately publishes a plan that restricts something; only then does it
  bite. This is a deliberate, documented inversion of the fail-closed
  default, safe precisely because a missing commercial entitlement is not a
  missing security control. It also means the entitlement gate is ADDITIVE
  to the permission gate, never a replacement for it: a caller needs BOTH
  the permission to act and the plan's entitlement to use the feature
  (section 4 works through the ordering).
- **The catalogue is a global, operator-managed table, read on both paths.**
  Plans are not tenant data: the catalogue carries no tenant discriminator
  at all, the same shape as the permission catalogue and the platform-admin
  roster (multi-tenancy.md sections 8 and 13). The request path resolves a
  tenant's entitlements from it (read-only); the super-admin path edits it
  (section 8). Write access is revoked from the ordinary request role, the
  same discipline audit-log.md section 8 applies to its own append-only
  tables, so no tenant-scoped code path, however it is reached, can ever
  mutate the catalogue.

## 2. Data model

A global plans catalogue, carrying no tenant discriminator (an operator
vocabulary table, like the permission catalogue):

- **key**: the catalogue's primary key, and the value stored in a tenant's
  own plan field (multi-tenancy.md section 14), for example `free`, `pro`.
- **name**: a display name.
- **features**: the list of feature keys this plan INCLUDES. Null (not an
  empty list) means unrestricted: every feature is available.
- **permissions**: the list of RBAC permission atoms (multi-tenancy.md
  section 8) a custom role on this plan may hold. Null means unrestricted:
  section 5 covers this half.
- **limits**: a structured map of numeric limits (a JSON object, a
  key-value table, or whatever your datastore's nearest structured-document
  type is), for example seat limit and any other numeric cap the product
  defines, such as a maximum number of workspaces.
- **is_default**: true for exactly one row, the plan a newly provisioned
  tenant gets.
- **created at / updated at**: as usual.

The seed data creates one row: key `free`, `features` and `permissions`
written as an actual null, not an empty list, `limits` holding a seat limit
of, say, 5, and `is_default` true. Writing an empty list instead of null
would be a serious mistake, not a cosmetic one: by the semantics below the
two are opposites, and an empty `features` list would strip every feature
from every tenant the moment the catalogue starts being consulted. With the
seed correct, a freshly provisioned tenant resolves to "every feature, every
grantable permission, 5 seats," and nothing that already works changes
behavior. Operators add restrictive plans (`pro`, `enterprise`, ..) through
the super-admin API (section 8).

**`features` and `permissions` semantics: null means the plan restricts
NOTHING.** A non-null list means the plan is CLOSED to exactly that set:
anything not listed is denied. This is what lets the default plan stay
unrestricted (null) while an operator later gating a paid tier sets an
explicit, closed list. The two states are not "empty means permissive" and
"a list means restrictive" - they are "absent means permissive" and "present
means restrictive," which is why the seed step must write a real null and
never an empty list.

Exactly one `is_default = true` is a real invariant, not merely application
discipline (a concurrent double-promote under load could otherwise violate
it): a partial or filtered unique index restricted to the true rows is the
reference mechanism where the datastore supports one (a `where` clause on a
Postgres or SQL Server unique index); a store without partial indexes
enforces the same invariant with a single-row "current default" pointer
updated in the same transaction that flips the two plan rows. Either way,
promoting a new default demotes the current one and promotes the target
inside one transaction, so a torn state - two defaults, or none - is
impossible by construction, not merely unlikely.

`is_default` DRIVES provisioning: tenant provisioning reads the current
default plan's key and seat limit at signup instead of a hardcoded literal
(falling back to a built-in default only if no default row exists yet), so
changing which plan is default actually changes what a new tenant gets, with
no code change.

**Boot-time grant hardening**, the same discipline audit-log.md section 8
applies to its own tables: after whatever blanket schema grant your
migration tooling applies, revoke insert, update, and delete on the plans
catalogue from the application's ordinary request role, so the request path
may only READ it. Only the bypass path (the super-admin API, section 8)
writes to it. A tenant can never edit the catalogue, no matter what code
path it goes through.

A tenant's own plan field (already present and nullable, multi-tenancy.md
section 14) is the assignment. Assigning a plan also writes the plan's seat
limit onto the tenant's own seat-limit field (both already mutable there,
the same way tenant status already is), so the existing race-proof seat
check in invitation-accept (multi-tenancy.md section 12: re-check the seat
limit under a row lock in the same transaction as consuming the invite)
keeps reading the tenant's own seat-limit field exactly as it does today,
now kept in sync with the plan.

## 3. Resolving entitlements per request

- **A resolved entitlements value**: a feature set and a
  grantable-permission set (each either an explicit set or "unrestricted"),
  plus a limits map. Testing a feature or a permission answers true when the
  set is unrestricted or contains the key; reading a limit returns the
  plan's value or a caller-supplied fallback.
- **An entitlement resolver** loads the plans catalogue and resolves a plan
  key to a resolved entitlements value. An unknown key, or no key at all,
  resolves to UNRESTRICTED - fail open, per section 1. The catalogue is
  global, so this read needs no tenant context or bypass privilege, only
  the ordinary read path. The catalogue is tiny and read fresh on every
  resolve, so there is no stale-after-edit window: a tightened plan takes
  effect on the very next request. A short-lived cache in front of the
  catalogue read is an optional refinement for scale, not a correctness
  requirement.
- **The request-path entry point** reads the active tenant's own plan field
  under the tenant boundary (multi-tenancy.md section 2 - the same
  authoritative boundary every other tenant read goes through, applied here
  to a single-row lookup), then resolves it through the entitlement
  resolver. One call gives a caller its full entitlement picture, ready for
  both kinds of gate below.

## 4. Gating a feature

A feature gate is a request filter modeled exactly on the permission gate
(multi-tenancy.md section 8's finer, per-permission check): it resolves the
caller's entitlements (section 3), and if the feature is not in the
resolved feature set, short-circuits with a 402 Payment Required response
(an "upgrade required" problem, its own dedicated type alongside whatever
problem types the permission and platform-admin gates already own);
otherwise it lets the request continue.

Composition order matters. The feature gate runs AFTER the tenant-boundary
check (a request naming no resolvable tenant answers 400 first,
multi-tenancy.md section 5) and is ORTHOGONAL to the permission gate: a
caller needs BOTH the permission to act and the plan's entitlement to use
the feature - "are you allowed to do this" and "does your plan include
this" are different questions. On a route gated by both, the permission
check composes BEFORE the feature check, so a caller who is not even
authorized for the action gets a plain 403 and never learns whether the
feature exists behind a paywall at all - a 402 would leak that information
to a caller who should not even know the feature is there.

**Worked example**: gate the outbound-webhooks admin API (webhooks.md
section 7) behind the "webhooks" feature. This changes nothing for an
existing tenant on the seeded, unrestricted default plan: its feature set is
unrestricted, so the check passes and every existing webhook test keeps
passing unchanged. The gate bites only for a tenant an operator has since
put on a plan whose feature list omits `webhooks`.

## 5. Gating the permission catalogue

Beyond gating feature endpoints, a plan also bounds which RBAC permissions a
tenant may put into a custom role. Multi-tenancy.md section 10 already
reserves this exact seam in its guardrails list ("a permission the tenant's
plan does not include cannot be added .. a no-op filter until billing
exists"); this section is that seam, implemented.

The plan's grantable-permission list is the catalogue for this check: null
means unrestricted (any non-owner-reserved permission stays grantable - the
pre-billing and default state); a non-null list closes it to exactly that
set, the identical null-versus-list semantics as the feature list (section
2).

Enforcement lives at custom-role AUTHORING time, not at permission
resolution time: wherever custom-role create and update already validate
requested permissions (multi-tenancy.md section 10, which already rejects
unknown and owner-reserved permissions), add one more check - each
requested permission must be allowed under the caller's tenant's
entitlements (resolved the same way section 3 resolves them for a feature
gate), or the write is refused with an upgrade-style error. This is
fail-open by the same rule as everything else here: on the default,
unrestricted plan, every non-owner-reserved permission stays grantable and
no existing custom-role test changes; the gate bites only once an operator
publishes a plan with an explicit, closed permission list.

Because the check runs at authoring time and not at resolution time, a role
that already holds a now-excluded permission keeps working exactly as
before - downgrading a plan does not silently strip a live grant out from
under whoever holds it. Reconciling existing roles against a newly
tightened plan (revoking what a downgrade newly excludes, if the operator
wants that) is a documented operator concern to run deliberately, not a
side effect this design triggers automatically at plan-change time.

## 6. Limits

- **Seat limit is plan-driven.** Assigning a plan sets the tenant's own
  seat-limit field from the plan's seat limit (section 2), so the existing
  seat check needs no change at all; it simply reports a plan-derived
  number now. Because the tenant's seat-limit field is not nullable, a
  positive seat limit is REQUIRED on plan create and update: a plan whose
  limits omit it, or that gives a zero or negative value, is rejected at
  plan-write time. That validation is what keeps assign-plan from ever
  landing a null or zero limit that would silently block every future
  invitation.
- **Other numeric limits** (a maximum workspace count, for example) are
  DEFINED on the plan and surfaced through the same limits read, but
  ENFORCING a countable limit - tracking current usage and refusing at the
  boundary - is the usage-quota concern (multi-tenancy.md section 18's
  "usage quotas" bullet, a separate grow-into feature this document only
  forward-references). This increment defines and exposes limits; quotas
  own metering and enforcement for the countable ones. Seat limit is the
  one limit already enforced end to end, because the seat check already
  existed before this feature; everything else is declared and left for
  the usage-quota layer to enforce when it lands.

## 7. Events and audit

- **Assigning or changing a tenant's plan** emits a tenant-scoped domain
  event (a "tenant plan changed" event, added to the shared deliverable
  catalogue so it is both audited and webhook-deliverable), carrying the
  old and new plan keys as scalars, no PII. Because it is tenant-scoped, it
  flows through the ordinary asynchronous projection: the audit log picks
  it up as a tenant audit row (audit-log.md section 2's tenant-scoped
  catalogue), and it is a candidate for the fan-out consumer if your
  product enables tenant-registered webhooks (webhooks.md section 3),
  exactly like any other deliverable event.
- **Plan-catalogue edits** (creating or updating a plan) are operator
  actions with no tenant to scope them to, so they follow audit-log.md's
  PLATFORM path, not the tenant path: written synchronously, in the same
  transaction as the catalogue write, through the platform's own narrow
  audit-write interface (audit-log.md sections 2 and 4) - the identical
  posture granting a platform admin already uses (multi-tenancy.md section
  13). There is never a window where a plan's features or limits changed
  but the platform audit trail does not yet reflect it.

## 8. Super-admin API

On the platform super-admin plane (multi-tenancy.md section 13), behind the
platform-admin check, on the bypass path:

- **Plan catalogue: list, create, update.** Update covers name, features,
  permissions, limits, and which plan is default. Exactly one plan may be
  default (validated app-side on write, on top of the storage-level
  invariant from section 2). Deleting a plan is deliberately NOT offered
  while any tenant still references it: a dangling plan reference on a
  tenant would resolve to nothing and silently fail open (section 1),
  which is the wrong failure mode for a deleted plan specifically. Retire a
  plan by editing it, or remove it once no tenant is assigned to it
  anymore.
- **Assign a plan to a tenant.** This is a NEW operation, not a reuse of
  whatever generic tenant-status-change helper your stack already has for
  suspend/reactivate-style transitions: a status change typically flips
  one field and emits one simply-shaped event, where assigning a plan sets
  TWO fields (the plan and the denormalized seat limit) and emits an event
  carrying both the old and new plan keys. It follows the same structure
  as any other bypass write bound to one target tenant: a connection bound
  to that tenant, one transaction, the row write, the event enqueue,
  commit. The target plan must exist, or the call fails with a not-found
  error - a tenant is never left pointing at a plan key that does not
  exist in the catalogue.

Tenants do not author their own plans - a tenant cannot buy itself a better
tier by fiat, since the catalogue is operator vocabulary (section 1). A
tenant instead sees its own plan and its resolved entitlements through its
existing tenant-admin surface (for example, whatever endpoint already
reports the tenant's seats, extended to also report the plan and its
limits). A future self-serve checkout is exactly the payment-provider seam
(section 9): it lands the tenant on this same assign-plan path, driven by a
real payment instead of a super-admin call.

## 9. The payment-provider seam (documented, not built)

A payment provider (Stripe, Paddle, Chargebee, ..) owns checkout, the card,
and the whole subscription lifecycle; none of that is built here. The
integration is three pieces:

1. **A checkout link per plan** - the provider's own hosted checkout page,
   requiring no card handling on this product's side at all.
2. **An inbound webhook endpoint.** This is the point worth being explicit
   about, since it is easy to conflate with webhooks.md's feature of the
   same name but the opposite direction. Webhooks.md is OUTBOUND: a tenant
   registers a receiver URL, and this product signs and sends events to it.
   This is INBOUND: the payment provider is the sender, this product is the
   receiver, and the endpoint verifies the PROVIDER's signature scheme (not
   this product's own signing scheme from webhooks.md section 5 - a
   different secret, a different header, a different verification routine,
   owned by the provider's SDK or documented format) rather than producing
   one. On a subscription created, updated, or deleted event, the endpoint
   calls the assign-plan path (section 8) to move the tenant onto the paid
   plan, or back to the default plan on cancellation.
3. **The provider's customer id**, stored on the tenant, for linking out to
   the provider's own billing portal.

The entitlement model above is entirely provider-agnostic: it does not know
or care whether a plan assignment came from a super-admin call or a
provider's webhook, because both drive the identical assign-plan path. That
single seam is what a provider integration plugs into. This is the same
"integrate the standard, do not hand-roll it" posture SSO and SCIM already
take in this control plane (multi-tenancy.md section 18): the seam is
documented and ready; wiring an actual provider is a separate, later piece
of work.

## 10. Placement and deletability

The plans catalogue, the entitlement resolver, and the feature and
permission-catalogue gates belong in the platform/shared layer, not inside
any business module: the catalogue is global operator vocabulary, exactly
like the permission catalogue and the platform-admin roster it sits next
to, and gating a feature or a permission list depends on no specific
module's data. This is the identical placement argument audit-log.md
section 9 and webhooks.md section 11 each make for their own cross-cutting
piece, for the identical reason: a feature that reads across every module
(or, here, reads nothing tenant-specific at all beyond one field) gains
nothing by living inside one.

The tenant's own plan field and its assign-plan action stay in the tenancy
module, which already owns the tenant row and every other tenant-admin and
platform-admin operation (multi-tenancy.md section 16).

**Deletability**: drop the plans catalogue, the entitlement resolver, the
feature and permission-catalogue gates, the 402 problem type, and the
super-admin plan endpoints, and the tenant keeps a harmless free-text plan
field that nothing else consults - the pre-billing state, the same
bolt-on, cleanly-removable posture the other three worked examples in this
series already commit to.

## 11. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring audit-log.md section 10's own
framing:

- **Fail-open by default.** A tenant on the seeded, unrestricted default
  plan, or with no plan set at all, or with an unknown plan key, passes
  every feature gate; every existing feature-gated test (the webhook admin
  API among them) still passes unchanged.
- **Gating bites on a restrictive plan.** An operator creates a plan whose
  feature list omits `webhooks`, assigns it to a tenant, and that tenant's
  webhook calls get 402; a tenant on an unrestricted plan still succeeds.
- **Entitlement is orthogonal to permission.** A caller who holds
  `webhooks:manage` (webhooks.md section 7) but sits on a restrictive plan
  gets 402, not 403; a caller on an unrestricted plan who lacks the
  permission gets 403, not 402 - the two gates are independently testable
  and neither one substitutes for the other.
- **Plan assignment drives the seat limit.** Assigning a plan with a seat
  limit of 2 sets the tenant's seat-limit field to 2, and the existing seat
  check (multi-tenancy.md section 12) then refuses a third member.
- **The permission catalogue is plan-gated.** On a plan whose grantable
  permissions omit `roles:manage`, authoring a custom role that includes
  `roles:manage` is refused; on the default, unrestricted plan the same
  authoring still succeeds, and every existing custom-role test
  (multi-tenancy.md section 15) stays green.
- **Super-admin only.** Plan create/update and assign-plan require the
  platform-admin check; a tenant admin gets 403; a tenant cannot change its
  own plan by any path.
- **Isolation holds.** The entitlement read for one tenant reads only that
  tenant's own plan field, under the same authoritative boundary as every
  other tenant read (multi-tenancy.md section 2); changing tenant A's plan
  never affects tenant B's resolution.
- **Provisioning follows the default plan.** With one plan seeded as
  default, a newly provisioned tenant lands on it with its seat limit;
  changing which plan is default changes what the next new tenant gets. A
  second attempt to mark a different plan default either atomically
  demotes the prior default or is rejected outright, never leaving two
  defaults or zero.
- **Seat limit is required.** Creating or updating a plan whose limits omit
  a seat limit, or give one that is zero or negative, is refused at
  plan-write time.
- **Audited.** A plan create or update lands a platform-audit row,
  transactionally with the write; a tenant plan change lands a tenant audit
  row (and is webhook-deliverable where that feature is enabled), and the
  catalogue-completeness check (audit-log.md section 10) stays green with
  the new event type accounted for.
