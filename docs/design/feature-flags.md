# Feature flags: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a rollout/kill-switch feature-flag mechanism grows out of the
multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "Feature flags"): adapt the specifics to your stack,
or skip it if your product ships every change straight to every tenant.
Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the fifth
worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), and
[billing-and-entitlements.md](billing-and-entitlements.md), and mirrors the
billing document's structure almost exactly (a global operator catalogue +
tenant-owned overrides under the tenant boundary + a request-path resolver),
so read billing-and-entitlements.md first; this document is mostly the delta
and the one inverted default. It also builds on multi-tenancy.md's isolation
boundary (section 2), its workspace scope (section 7), and its platform
super-admin plane (section 13); and on audit-log.md's synchronous
platform-audit write (sections 2 and 4) and catalogue-completeness
discipline (section 10). Read those first. Being a generic reference, it
carries no build-sequence section (a concrete product's own design doc
would): treat every part as a menu, adopt the pieces your product needs.

## 1. The decision, up front

- **Feature flags are for rollout and operations, not commerce, and they
  fail CLOSED - the deliberate opposite of entitlements.** An entitlement
  (billing-and-entitlements.md section 1) answers "does your plan include
  this," a commercial question that fails OPEN: an unconfigured tenant, an
  unknown plan key, or a plan that restricts nothing leaves every feature
  available, because a commercial gate with nothing configured must never
  lock out a tenant nobody meant to restrict. A feature flag answers a
  different question: "is this capability turned on for you right now" -
  a dark launch, a gradual release, a per-tenant beta, or a kill switch in
  an incident. An unknown or archived flag resolves OFF: a flag name only
  ever exists for a capability that is in progress, gated, or being pulled,
  so defaulting an unknown one ON would expose an unfinished or a
  deliberately killed feature the moment a typo, a stale reference, or a
  half-finished removal left a flag key unresolved. The two mechanisms
  therefore default in opposite directions on purpose, because getting the
  default wrong costs opposite things: an entitlement defaulting closed
  would lock out every tenant before a single plan is ever defined; a flag
  defaulting open would ship an unfinished feature to everyone the instant
  its key goes missing. This is the standard flag-service shape (LaunchDarkly,
  Unleash, Flagsmith all resolve an unrecognized flag key to off), the exact
  mirror image of the standard entitlement shape. A single capability can sit
  behind BOTH: gated by a plan entitlement (may this tenant use it at all)
  AND a rollout flag (is it turned on for them yet); they compose, and
  neither substitutes for the other (section 4 works through the ordering).
- **Three resolution layers, most specific wins.** A flag's value for a
  caller follows one precedence chain: a WORKSPACE override for the active
  workspace (multi-tenancy.md section 7) if one exists, else a TENANT
  override, else the GLOBAL default - a fixed on/off, or a deterministic
  percentage rollout (section 3). Read as a chain, it is workspace override
  -> tenant override -> global default, the same most-specific-wins shape
  multi-tenancy.md's own scoped-RBAC grants already use (section 8). This is
  the standard flag-service shape (LaunchDarkly, Unleash, Flagsmith): a
  global default with progressively narrower overrides layered on top.
- **Percentage rollout is deterministic and sticky, never random per call.**
  A 10-percent rollout is ON for the same tenants on every call, not a coin
  flip per request, which would flicker a feature on and off mid-session for
  the same tenant. The bucket is a stable hash of the flag key and the
  tenant id, reduced modulo 100 and compared against the rollout percentage,
  so a tenant is stably in or out, and raising the percentage only ever adds
  tenants, never drops one already in. Getting this wrong is a specific,
  well-documented trap, not a hypothetical one: many languages randomize
  their built-in string or object hash per process as a hash-flooding
  defense - .NET's `string.GetHashCode()`, Python's default `str` hash
  (randomized since PEP 456), and Ruby's `String#hash` all do this on
  purpose - so reaching for a language's default hash function gives a
  DIFFERENT bucket on every process, every replica, and every restart, and a
  same-process repeat-call test cannot catch it, because the randomized seed
  is fixed for the lifetime of the one process the test runs in. Section 3
  names a fixed, cross-process-stable hash and the golden-value test that
  catches the mistake on the very first run, in any single process.
- **Two audiences, two write paths, like billing.** The operator owns the
  global catalogue: define a flag, its default, its rollout percentage, and
  whether tenants may override it at all. A tenant admin owns its own
  tenant or workspace overrides, but only for flags the operator marked
  overridable - a tenant can never flip a flag the operator holds centrally,
  such as a kill switch or a feature that is not yet generally available
  (billing-and-entitlements.md section 1 draws the identical
  operator-catalogue-versus-tenant-assignment line for plans).
- **Placement mirrors billing.** The global catalogue is operator-managed,
  carries no tenant discriminator, and is writable only from the operator's
  own admin surface: the same boot-time grant-hardening discipline
  billing-and-entitlements.md section 2 applies to the plans catalogue
  applies here identically, revoking insert, update, and delete on the
  catalogue from the ordinary request role after whatever blanket grant your
  migration tooling applies, so no tenant-scoped code path can ever mutate
  it. The overrides are tenant-owned, under the same authoritative isolation
  boundary as every other tenant row (multi-tenancy.md section 2). A
  resolver reads both, on the request path, in one call (section 3).

## 2. Data model

A global catalogue, carrying no tenant discriminator (operator vocabulary,
the same shape as the permission catalogue and the plans catalogue,
multi-tenancy.md section 8 and billing-and-entitlements.md section 2):

- **key**: the catalogue's primary key, the identifier code checks against.
- **description**: what the flag controls, for the operator's own benefit.
- **default enabled**: the global default when no rollout percentage is set
  and no override applies.
- **rollout percentage**: 0 to 100, nullable. When set, it overrides the
  plain default via the deterministic bucket (section 3); null means use
  the plain default enabled value instead.
- **tenant overridable**: whether a tenant admin may set an override for
  this flag at all (section 6).
- **archived at**: nullable. An archived flag resolves OFF and is hidden
  from the tenant-facing surface - the operator's way to retire a flag
  without deleting the row a caller might still reference.
- **created at** / **updated at**: as usual.

Unlike the plans catalogue, which needs at least one seeded row so a freshly
provisioned tenant has somewhere to land (billing-and-entitlements.md
section 2), **the flag catalogue is seeded EMPTY**: a flag is a deliberate
operator act naming a specific capability, and there is nothing to gate
until one is defined. An empty catalogue is the correct starting state here,
not an oversight the way an empty plans catalogue would be.

A tenant-owned overrides table, under the same authoritative isolation
boundary as every other tenant row (multi-tenancy.md section 2):

- **id**: primary key.
- **tenant id**: not null, the isolation discriminator.
- **flag key**: the flag this row overrides.
- **scope type**: `tenant` or `workspace`.
- **scope id**: the workspace id for a workspace-scope override; null for a
  tenant-scope override.
- **enabled**: the override value.
- **set by** / **updated at**: as usual.

**Unique per (tenant, flag key, scope type, scope id)**: exactly one
tenant-scope override per flag, and one workspace-scope override per (flag,
workspace) pair. Because scope id is null on every tenant-scope row, a
plain unique constraint cannot express this on its own - the identical
null-collision problem multi-tenancy.md section 14 solves for
`role_assignments` with two partial unique indexes, one per scope kind (a
tenant-scope index that needs no scope id in its key, since it is always
null there, and a workspace-scope index where scope id is never null).
Making scope type part of the key is what keeps the two kinds from
colliding with each other: a null scope id only has to be unique within the
tenant-scope rows, never across both kinds at once. A store whose unique
indexes natively treat two NULLs as equal (Postgres's `NULLS NOT DISTINCT`
is the reference case) can instead express the whole rule as a single index
across all four columns - a convenience, and what lets a single
upsert-style write replace an override in one statement, but a different
encoding of the identical one-override-per-scope rule, not a different
guarantee.

The evaluator (section 3) reads the catalogue and the overrides through the
ordinary request path, never a bypass source - the identical discipline
billing-and-entitlements.md section 3 holds its own entitlement resolver to.

## 3. Resolving a flag on the request path

A flag's value for a caller resolves in order:

1. The flag's catalogue row. If the flag is unknown or archived, resolve OFF
   (fail closed, section 1).
2. If a workspace is in scope and a workspace-scope override exists for
   (flag key, workspace) in this tenant, return its enabled value.
3. Else if a tenant-scope override exists for this flag in this tenant,
   return its enabled value.
4. Else the global default: if a rollout percentage is set, return whether
   this tenant's bucket falls under it; otherwise return the plain default
   enabled value.

The read spans both tables in one pass, under the tenant's own context so
the override read stays isolation-scoped, mirroring exactly how
billing-and-entitlements.md section 3 resolves a tenant's plan: one call
gives a caller its full picture, ready for either kind of gate in section 4.
Resolution is worth caching per request on (flag key, workspace) - a request
rarely evaluates the same flag twice, but a loop over many records might.

**The rollout bucket must use a fixed, cross-process-stable hash - never a
language's built-in default hash function.** Section 1 named the trap:
.NET's `string.GetHashCode()`, Python's default `str` hash, and Ruby's
`String#hash` are all randomized per process on purpose, as a
hash-flooding defense, which means each gives a different bucket on every
replica and every restart - the same tenant would flicker in and out of a
rollout depending on which replica happened to answer. Name a fixed,
well-known non-cryptographic hash instead - FNV-1a is the reference choice,
MurmurHash3 or a similar fixed hash works identically - computed over the
bytes of the flag key concatenated with the tenant id (for example
`flagKey + ":" + tenantId`, UTF-8 encoded), accumulated as an UNSIGNED
integer end to end so there is no negative-value edge case to special-case
at the final step, then reduced modulo 100. A tenant is ON when its bucket
is less than the rollout percentage; because the hash is fixed, the SAME
tenant lands in the SAME bucket forever, so a tenant is stably in or out and
raising the percentage only ever adds tenants.

**Catch the mistake with a golden-value test, not a same-process repeat-call
test.** Pin the bucket for one known flag key and one known tenant id to a
hardcoded expected literal, computed once and committed alongside the test.
A test that merely calls the bucket function twice in the same process and
checks the two calls agree will pass even on a randomized per-process hash,
because the seed is fixed for the lifetime of that one process - the bug
only shows up as two different processes (two replicas, or the same replica
before and after a restart) disagreeing about the same tenant, which a
single test run can never observe by construction. A golden-value test
catches it immediately, on the very first run, in any single process,
because a randomized hash could never reproduce a value pinned in advance;
only a fixed, correctly implemented hash can.

For code that needs many flags at once (a client bootstrap that hydrates a
UI on session start), a batch evaluate-all operation resolves the whole map
in one pass over the catalogue and the overrides, rather than one round trip
per flag.

## 4. Gating

Two ways to gate, because flags are checked in more places than an
entitlement (billing-and-entitlements.md section 4 gates only at the
endpoint; a flag is routinely also checked deep inside a code path):

- **In code**: inject the resolver and branch on its result. This is the
  common case - a flag guards one branch of a larger code path, not a whole
  endpoint.
- **At an endpoint**: a filter or middleware that resolves the flag and
  returns 404 (NOT 403 and NOT 402) when it is off. A not-yet-released
  feature should look like it does not exist at all, not like it is
  forbidden or paywalled: either 403 or 402 confirms to a prober that the
  endpoint exists and is merely gated, which is exactly the surface a
  kill-switched or unreleased feature must not reveal. This composes after
  the tenant-boundary check, the same ordering the permission and
  entitlement gates already follow (multi-tenancy.md section 6;
  billing-and-entitlements.md section 4).

A flag gate and an entitlement gate are independent and may both apply to
the same route: a feature can require a plan entitlement (your plan
includes it, billing-and-entitlements.md section 4's 402) AND a rollout
flag (it is turned on for you, this section's 404). Order matters when both
are composed on one route: put the flag check OUTERMOST when hiding the
feature's existence matters more than the paywall message, so a caller on
the wrong plan for a still-unreleased feature gets 404, never a 402 that
would confirm the feature exists at all. The default worked examples in
this series keep each concern on its own route, so no single route needs
both composed in the base build; a product that does need both documents
its own composition order at the route.

## 5. Feature flags vs. entitlements (why both exist)

They look similar (a per-tenant boolean, resolved on the request path) but
answer different questions and default in opposite directions, so keeping
them as two separate mechanisms is correct, not redundant:

| | Feature flag | Entitlement |
|---|---|---|
| Answers | "is this turned on for you right now" | "does your plan include this" |
| Nature | operational | commercial |
| Default when unset | OFF (fail closed) | available (fail open) |
| Changes on | a release/rollout/kill-switch timeline | a billing/plan timeline |
| Typical use | dark launch, gradual release, kill switch, per-tenant beta | a paid tier unlocking a GA feature |
| Owned by | operator catalogue + tenant/workspace overrides (section 2) | operator catalogue + tenant plan assignment (billing-and-entitlements.md section 2) |

A GA feature that a paid tier unlocks is an entitlement
(billing-and-entitlements.md section 1); a feature being rolled out to 10
percent of tenants, dark-launched ahead of general availability, or
kill-switched during an incident, is a flag. A single capability can sit
behind both (section 4). Folding them into one table would force one
default direction onto two problems that need opposite ones: a fail-open
commercial gate can safely ship with an empty catalogue, because nothing is
restricted yet; a fail-closed rollout gate could never safely default the
other way without exposing every in-progress capability the moment the
catalogue went live. Keeping them as two mechanisms, each defaulting the
direction its own failure mode demands, is what lets both ship safely on
day one.

## 6. Admin surfaces

- **Super-admin (global catalogue)**, on the platform super-admin plane
  (multi-tenancy.md section 13), cross-tenant on the bypass path, the same
  posture billing-and-entitlements.md section 8 uses for the plans
  catalogue: list and create catalogue entries; update a flag's default,
  rollout percentage, tenant-overridable setting, or archive it. Catalogue
  edits are audited synchronously on the platform audit log
  (audit-log.md sections 2 and 4), transactionally with the write - the
  identical posture billing-and-entitlements.md section 7 holds its own
  plan-catalogue edits to, and the same posture multi-tenancy.md section 13
  already uses for granting a platform admin.
- **Tenant admin (own overrides)**, on the tenant-admin control-plane
  surface (multi-tenancy.md section 16), gated by a new permission atom
  (added to the closed permission catalogue and the default admin role,
  multi-tenancy.md section 8, for example `feature-flags:manage`): read the
  resolved flags plus which ones are overridable; set a tenant or workspace
  override; clear an override, falling back to the layer below it. A set or
  clear for a flag the operator did NOT mark overridable is refused with a
  clear error - a tenant cannot touch an operator-held flag, the same
  allow-list shape billing-and-entitlements.md section 5 uses to check a
  requested permission against a plan's grantable-permission list. Override
  changes emit a tenant-scoped domain event (an override-set and an
  override-cleared pair), picked up by the audit projection as an ordinary
  tenant-audit row (audit-log.md section 2's asynchronous tenant path) and,
  where your product enables tenant-registered webhooks, a candidate for
  fan-out like any other deliverable event (webhooks.md section 3).

## 7. Placement and deletability

The catalogue, the resolver, and the endpoint filter belong in the
platform/shared layer, not inside any business module: the catalogue is
global operator vocabulary, exactly like the permission catalogue, the
plans catalogue, and the platform-admin roster it sits next to
(multi-tenancy.md sections 8 and 13; billing-and-entitlements.md section
2), and gating on a flag depends on no specific module's data. This is the
identical placement argument audit-log.md section 9,
webhooks.md section 11, and billing-and-entitlements.md section 10 each
make for their own cross-cutting piece, for the identical reason.

The overrides table is tenant-owned and sits under the same authoritative
isolation boundary as every other tenant table (multi-tenancy.md section
2) - one more addition to the small, deliberate list of tenant-owned tables
living inside an otherwise tenant-agnostic platform layer that
webhooks.md section 11 already names (the audit log, the service-account
table, the webhook tables). A platform-layer design note claiming "nothing
here is tenant-owned" needs updating to name this table too; the table
itself needs no change to stay correct.

**Deletability**: drop the two tables, the resolver, the endpoint filter,
the permission atom, and the two override events, and every call site
either removes the flag check or hard-codes the value it was gating - the
pre-flag state, the same bolt-on, cleanly-removable posture the other
worked examples in this series already commit to. No event-spine change:
the catalogue and the overrides are the only new state this feature adds.

## 8. Grow-into (documented, not built)

Multivariate flags (string or number variants, not just a boolean),
targeting rules (enable for tenants matching an attribute - the
ABAC-adjacent case multi-tenancy.md section 18 already reserves as its own,
separate grow-into), scheduled rollouts, and a streaming evaluation
endpoint for a client to subscribe to flag changes without polling - all
layer onto the catalogue and override tables without a rewrite, and are
where a team graduates to a hosted flag service (LaunchDarkly, Unleash,
Flagsmith) if the need outgrows the built-in resolver. The built-in
resolver is the correct starting bar for an MVP; the seam is the resolver's
own interface - swap the implementation for a provider SDK and keep every
call site unchanged, the same swap-the-implementation posture
billing-and-entitlements.md section 9 documents for its own
payment-provider seam.

## 9. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring audit-log.md section 10's own
framing:

- **Fail closed.** An unknown or archived flag resolves OFF; the endpoint
  filter for it returns 404.
- **Resolution precedence.** A workspace override beats a tenant override
  beats the global default; clearing the workspace override falls back to
  the tenant override, then to the global default.
- **Deterministic rollout.** A flag at 50 percent resolves the SAME value
  for a given tenant across repeated calls; a tenant already in the bucket
  stays in, and raising the percentage never flips an in-tenant tenant back
  out (test with two tenant ids that land on opposite sides of a chosen
  percentage). PLUS a golden-value test that pins one known (flag key,
  tenant id) pair's bucket to a hardcoded expected literal - this fails on
  the first run, in any single process, if the implementation reaches for a
  language's randomized default hash instead of the fixed one section 3
  names.
- **Isolation holds.** A tenant sees and sets only its own overrides;
  tenant A's override never affects tenant B's resolution - the same
  assertion multi-tenancy.md section 15 already runs for every other
  tenant table.
- **Overridable gate.** A tenant admin can override a tenant-overridable
  flag but is refused on one the operator holds centrally.
- **Super-admin only.** Catalogue create, update, and archive require the
  platform-admin check; a tenant admin is refused; the tenant override
  surface requires its own permission, and a member without it is refused.
- **Entitlement and flag are independent.** A route gated by both admits
  only when the plan includes it AND the flag is on; failing either blocks
  it, with the flag's 404 taking precedence over the entitlement's 402 when
  both are composed on the same route (section 4).
- **Audited.** A catalogue edit lands a platform-audit row, transactionally
  with the write; an override set or clear lands a tenant-audit row and is
  webhook-deliverable where that feature is enabled; the
  catalogue-completeness check (audit-log.md section 10) stays green with
  the two new event types accounted for.
