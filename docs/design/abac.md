# ABAC: conditional grants over RBAC

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how attribute-based conditions grow out of the multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "A policy engine (ABAC)"): adapt the specifics to
your stack, or skip it if every grant in your product is fine staying
unconditional forever. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the
twelfth and final worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), [quotas.md](quotas.md),
[data-export-and-erasure.md](data-export-and-erasure.md),
[in-app-notifications.md](in-app-notifications.md),
[role-templates-and-policy-defaults.md](role-templates-and-policy-defaults.md),
[mfa-totp.md](mfa-totp.md), and [sso-and-scim.md](sso-and-scim.md).

It builds directly on multi-tenancy.md's generalized RBAC model (section 8:
permissions are a closed catalogue, roles compose them, and a grant binds a
custom role to a principal at a scope) and that same section's per-request
permission check, which resolves the caller's effective permission set once
per request, caches it, and fails closed. Read that section first: ABAC adds
exactly one field to the grant it already defines, and this document is
mostly about the one invariant that keeps that addition safe. Being a
generic reference, it carries no build-sequence section (a concrete
product's own design doc would): treat every part as a menu, adopt the
pieces your product needs.

**Built as an integration SEAM, deliberately, not a from-scratch policy
engine.** Hand-rolling a general attribute-based policy language (a Rego or
Cedar of your own) is below-par and the most expensive option available at
the same time: a policy language is a product in its own right, and a
bespoke one is an unbounded surface with its own evaluation-safety footguns
(non-termination, injection through attribute values, a silent fail-open).
The right engineering call for a starter is a CORRECT minimal path: a grant
may carry ONE optional condition, evaluated at the existing per-request
permission check against a small, fixed request-attribute bag, through a
pluggable evaluator registry. Two built-in condition kinds (an IP-CIDR
allowlist and a UTC time-of-day window) prove the seam end to end; a real
policy engine (Cedar, Open Policy Agent) plugs in as ONE more evaluator
registered for its own condition type, with no change to the check, the
resolver, or the schema (section 4). RBAC stays the default, and the whole
feature is a no-op until a tenant attaches a condition to a grant.

## 1. The decision, up front

- **ABAC layers on RBAC; it never replaces it.** A grant is still a binding
  of a custom role to a principal at a scope (multi-tenancy.md section 8).
  ABAC adds ONE optional field to that binding: a condition. When the
  condition is absent, which is every grant today, the grant behaves exactly
  as it does now. When present, the grant's permissions count only for a
  request whose attributes satisfy the condition.
- **The condition is evaluated at the SAME per-request permission check as
  RBAC**, not in a separate pipeline. One authorization decision point, not
  two: a conditional grant is a variation on how that one check resolves a
  grant, not a second gate bolted on beside it.
- **The evaluation is per request and per check, never memoized as a static
  grant. This is the headline invariant (section 5).** The effective-permission
  set the resolver caches per request is keyed on the caller and the scope, a
  key that OMITS every request attribute a condition might read (the clock,
  the client IP, the resource). A conditional grant must therefore stay OUT
  of that cached set and be evaluated live, against the request's own
  attributes, every time it is consulted. Folding a conditional grant into
  the cached set would memoize a decision under a key that leaves out the
  very attributes the condition reads - the one way a naive design breaks,
  and the reason this document exists.
- **Fail-closed, always.** A condition that is unknown, malformed,
  references a missing attribute, or errors during evaluation denies the
  grant: the permission is simply not conferred. This matches RBAC's own
  fail-closed contract (an unresolved membership resolves to the empty set)
  and is the opposite of the commercial gates a plan-driven feature typically
  has (an entitlement check, billing-and-entitlements.md section 1; a
  usage-quota check, quotas.md section 1), which fail OPEN by design because
  an unconfigured plan must never lock out a tenant nobody meant to restrict.
  A security condition sits on the other side of that line: one that cannot
  be evaluated must never widen access.
- **Built-in conditions are single-clause on purpose.** An IP-range check
  and a time-of-day check each express one attribute test. Arbitrary boolean
  logic ("business hours AND from the office network AND on a resource
  labeled prod") is exactly what a real policy engine is for, and that is
  the documented Cedar / OPA plug-in (sections 4 and 9). Do not grow a
  bespoke AND/OR mini-language here: the moment a condition needs
  composition, that is the signal to register a real engine, not to extend
  the built-ins.

## 2. Data model

One nullable field added to the existing grant row (multi-tenancy.md section
8's grant/role-assignment table); no new table.

| field | type | notes |
|---|---|---|
| condition | JSON document, nullable | null = unconditional (every grant today). When set, holds the condition envelope (section 3). The store validates only that it is well-formed JSON; the evaluator registry owns its semantics. |

The two scope-uniqueness rules that already exist on the grant table
(multi-tenancy.md section 8: a principal holds at most one grant of a given
role at a given scope) are UNCHANGED. A condition is an attribute OF that
one grant, not a way to hold the same role twice under different
conditions - letting a principal hold the same role at the same scope under
several conditions is a documented grow-into (section 9) that would widen
the uniqueness rule, and it is not needed for the seam.

The migration adds only the column: no index change, no data backfill.
Every existing row gets null, which is the unconditional default, so the
migration is behavior-preserving by construction. The column inherits
whatever isolation policy already sits on the table (multi-tenancy.md
section 2); nothing new is needed at that level.

**The condition is tenant policy configuration, not a secret.** Grants are
already part of the tenant's own data export contribution
(data-export-and-erasure.md section 3 lists role assignments among the
tenancy module's exported sections), so the condition value rides along
automatically: it needs no new export contributor and no sensitivity marker.
Contrast this with the fields that document's section 8 does mark
sensitive and exclude (an encrypted client secret, a hashed token) - a
condition is the opposite case, a piece of the tenant's own configuration
the tenant is entitled to see a full copy of.

## 3. The condition envelope and the built-in kinds

A condition is a JSON object with a `type` discriminator plus type-specific
fields:

```json
{ "type": "ip_cidr", "allow": ["203.0.113.0/24", "2001:db8::/32"] }
{ "type": "time_of_day", "startUtc": "09:00", "endUtc": "17:00" }
```

The `type` selects an evaluator from the registry (section 4). Two
built-ins ship, each reading exactly one attribute from the
request-attribute bag:

- **`ip_cidr`** - satisfied only if the request's client IP falls inside one
  of the `allow` CIDR ranges (IPv4 or IPv6). Fails closed if the client IP
  is unknown or unparseable, or if `allow` is empty. This is the classic
  network-conditional-access rule (Okta and Microsoft Entra Conditional
  Access both call it a "trusted network" condition): a grant that only
  counts from the corporate egress range or a VPN CIDR, or a service-account
  key restricted to a CI runner's IP range. Two implementation obligations
  the evaluator must honor: (a) normalize an IPv4-mapped IPv6 address (the
  form a dual-stack listener reports for an IPv4 client) back to plain IPv4
  before matching, else a plain IPv4 CIDR never matches - this fails closed,
  so it locks callers out rather than leaking, but it is still a correctness
  bug worth a one-line implementer note; (b) bound the `allow` list to a
  sane maximum entry count at validation time (section 6), so a pathological
  payload cannot bloat a grant row.

  **Deployment prerequisite, and it deserves saying loudly.** The client IP
  is only trustworthy behind a correctly configured forwarded-headers /
  trusted-proxy setup. The raw connection peer address is the last socket
  hop; behind a reverse proxy, load balancer, or CDN, which is the default
  deployed topology for almost every product, that peer address is the
  PROXY's address, not the caller's. An unconfigured deployment therefore
  makes an `ip_cidr` condition either a silent no-op (the proxy's own
  address happens to sit inside the allowed range) or a silent lockout of
  every caller (it does not). The host MUST wire its forwarded-headers
  handling with an EXPLICIT, non-empty trusted-proxy allowlist, never a
  wildcard-trust default: a client-writable forwarded-for header is a
  spoofing vector the moment an untrusted hop is trusted to set it. Until an
  operator configures that allowlist, treat `ip_cidr` as not-yet-usable
  rather than assume it is quietly doing its job. `time_of_day` has no such
  dependency and is usable immediately.

- **`time_of_day`** - satisfied only if the request time falls within the
  `[startUtc, endUtc)` window (both `HH:mm`, UTC). Wrap-around past midnight
  is supported: `startUtc` greater than `endUtc` means the window spans
  midnight. Reads the current time from the request-attribute bag, which is
  itself stamped from an injected clock abstraction, never a direct call to
  the platform's current-time function - the same discipline quotas.md
  section 3 holds its own period computation to, and for the identical
  reason: a test needs to pin the clock and move it across a boundary
  deterministically, not wait on the real calendar. This is the
  "business-hours only" rule, and it is deliberately the kind that
  exercises the clock path.

Resource-attribute conditions (a grant that only counts on a resource
carrying a given label or status) are NOT a built-in: they need a richer
resource contract than a plain owner-id, which is genuinely more work and is
the province of a real policy engine. The request-attribute bag reserves a
resource-id slot so the seam is shaped for it, but no built-in consumes it
yet; it is a documented grow-into (section 9).

## 4. The evaluator seam (the Cedar / OPA integration point)

One contract, one dispatcher, both living where the rest of the
cross-cutting authorization primitives already live (section 8):

- **A conditional-grant evaluator**, one per condition kind, stateless: it
  names the condition type it handles (`ip_cidr`, `time_of_day`, or later
  `cedar`); it VALIDATES a condition payload at GRANT time (reject a
  malformed one outright: a typo'd CIDR, a bad time string); and it decides
  whether a condition is SATISFIED at CHECK time, given the
  request-attribute bag. The check-time operation must fail closed on any
  doubt - a missing attribute, a parse slip - and must never throw for a
  data reason, since validation already ran at grant time.
- **The request-attribute bag**: a small, fixed, immutable set assembled
  once per request - the current time (from the injected clock), the client
  IP (trustworthy only behind the forwarded-headers setup, section 3), the
  workspace in scope when the request is workspace-scoped, and a
  resource-id slot that no built-in reads yet (section 3, section 9).
- **A registry**, a frozen map from condition type to its evaluator,
  exposing two dispatching operations: validate a condition's JSON against
  its declared type (used by the grant path, section 6), and decide whether
  a condition is satisfied against a set of attributes (used by the
  conditional-grant resolver, section 5). Both are FAIL-CLOSED at the
  dispatch level, not only inside each evaluator: an unknown type denies, a
  parse failure denies, and an evaluator that throws is caught and denies.
  There is exactly one place an "unknown type" gets decided, and it decides
  deny.

**This registry IS the Cedar / OPA integration point.** A real policy
engine ships as ONE evaluator whose condition type is, say, `cedar`, whose
payload is a policy reference rather than an inline rule, and whose
satisfied-check calls the engine with the request attributes projected as
its entity or context set. Registering it adds a condition kind; it changes
nothing in the permission check, the resolver, the schema, or the two
built-ins. That is the whole point of the seam: the grow-into is additive
registration, never a rewrite.

## 5. Evaluation at the permission check (the headline invariant)

The effective-permission resolver (multi-tenancy.md section 8) caches the
caller's effective permission set per request, keyed on the caller and the
scope - a key that OMITS every request attribute a condition reads: the
clock, the client IP, the resource. A conditional grant must therefore
never enter that cached set. The seam splits resolution into two tiers.

**Tier 1 - unconditional grants, cached, unchanged behavior.** Every grant
read the resolver already performs (tenant scope and workspace scope, for a
user's own grants and for a team's or service account's grants) gains a
"condition is absent" filter. The resulting set is exactly today's set,
since every existing grant has an absent condition; it depends on no
request attribute, so caching it per request stays sound. **This filter is
the safety hinge.** Without it, a conditional grant would be read as if it
were unconditional and would be silently always-on, cached and all - the
exact failure mode this whole feature exists to avoid. It is
behavior-preserving today and is covered by an explicit regression test on
every grant-read path (section 10).

**Tier 2 - conditional grants, evaluated live, never memoized as a
decision.** A sibling, request-scoped conditional-grant resolver reads the
caller's grants where a condition IS present, using the SAME union logic
Tier 1 uses (direct and team grants for a user behind the active-membership
gate; grants for a service account; tenant scope plus, when asked, one
workspace's scope), carrying the condition payload along. It is an ordinary
request-path read under the tenant boundary, NOT a bypass-path read, so it
stays OUT of the bypass allowlist, exactly like the effective-permission
resolver it sits beside.

The resolver MAY cache the loaded grant ROWS per request, since they do not
change within one request, but it MUST NOT cache the DECISION: it
re-evaluates the condition against the passed-in attributes on every call.
Loading is lazy - the rows are fetched once, on the first call in a
request - so a caller with no conditional grants at all (every tenant that
has not adopted ABAC) gets an empty load, and every subsequent check
short-circuits to false. The feature costs nothing until a conditional
grant exists. If the row cache is keyed, it MUST be keyed by scope exactly
as the Tier-1 cache is, so a tenant-scope load can never serve a
workspace-scope query.

**The permission check itself** gains a conditional fallthrough AFTER the
existing unconditional check, expressed here as a flow, not any one stack's
syntax:

```
permissions = effective_permission_set(caller, scope)      // Tier 1, cached
if permission in permissions:
    allow                                                   // unconditional grant, unchanged

attributes = request_attributes(clock.now, client_ip, scope)
if conditional_grant_resolver.is_granted(caller, permission, attributes, scope):
    allow                                                   // Tier 2: conditional grant satisfied

deny                                                         // fail closed
```

Tier 2 runs only on a Tier-1 miss, so an authorized-by-RBAC caller pays
nothing extra; a genuine denial pays one extra read, cached thereafter
within the request. Denials are the uncommon path, so this is the right
trade for a starter, and it keeps the plain effective-permission set
returned to every OTHER caller of that resolver unaffected - the
conditional-grant resolver is a sibling port, deliberately not folded into
an already-large tenancy facade, since it is single-purpose and the
permission check resolves it directly.

## 6. The grant path: validation, threading, audit

- **Creating a grant gains an optional condition parameter.** Absent (null)
  is the ordinary unconditional grant; this is not a new capability gated
  by a new permission - it rides whatever permission already gates creating
  a grant at all (multi-tenancy.md section 8's role-management permission
  atom), since attaching a condition is a property of an act an admin can
  already perform, not a new act.
- **Validation at write time.** When a condition is supplied, the create
  path calls the registry's validate operation BEFORE the write. A
  validation failure (an unknown type, a malformed payload: a bad CIDR, a
  non-`HH:mm` time) is rejected outright, at grant time, with a clear
  error - never silently accepted as a condition that will simply never be
  satisfied. Turning a would-be-silent-dead-grant into a write-time
  rejection is the entire point of validating here instead of only at check
  time.
- **Service accounts** hold a conditional grant through the ordinary
  grant-creation path, not through whatever atomic create-account-with-role
  shortcut your product may have (service-accounts.md). Keeping the seam
  minimal here means an IP-restricted service-account key is a two-step
  act: create the account, then grant it a role with a condition. The brief
  window between the two, where the account exists but has no permission
  yet, is harmless precisely because it is fail-closed by default. Atomic
  create-with-conditional-role is a documented grow-into (section 9).
- **Audit.** The grant-created event gains a nullable condition-type field
  (for example `"ip_cidr"`, or null for an unconditional grant), so the
  audit log and any webhook subscribers record THAT a conditional grant was
  created and of WHAT KIND, without ever putting the full condition payload
  on the event. A scope-aware invitation's own grant-on-accept path, where
  one exists, always passes null: an invitation-issued grant is
  unconditional by construction.
- **Visibility.** Wherever grants are listed back to an admin surface, the
  result gains a condition field, so a conditional grant is visible and
  manageable rather than an invisible surprise the next time someone audits
  who has access to what.
- **Revoke** is unchanged: a conditional grant is revoked by id exactly like
  any other grant.

## 7. Fail-closed posture (the matrix)

Every uncertain outcome DENIES. This is RBAC's own fail-closed contract,
extended to conditions.

| situation | outcome |
|---|---|
| grant has no condition | Tier 1, unconditional, as today |
| condition type unknown to the registry | deny |
| condition payload malformed at check time | deny (should not happen: validation ran at grant time, section 6) |
| the evaluator errors at check time | deny |
| `ip_cidr` with an unknown or unparseable client IP | deny |
| `time_of_day` outside the window | deny |
| caller has no active membership | deny - the conditional-grant resolver applies the SAME active-membership gate as the unconditional resolver, so a suspended member reaches no conditional grant either |
| condition satisfied | allow |

The registry is the only place an "unknown type" gets decided, and it
decides deny. There is no path where an unrecognized or unparseable
condition widens access.

## 8. Placement and deletability

- **Platform / shared layer**: the conditional-grant evaluator contract,
  the request-attribute bag, the registry, and the two built-ins live next
  to the rest of the cross-cutting authorization primitives (multi-tenancy.md
  section 16), since all of it is pure, dependency-free logic that any
  module could reference. The conditional-grant resolver's PORT lives here
  too, mirroring the cross-module port pattern sso-and-scim.md section 7 and
  role-templates-and-policy-defaults.md section 6 both already use for a
  tenancy-owned read the shared layer needs to call.
- **Tenancy module**: the Tier-1 "condition is absent" filter change on
  every existing grant query (the safety hinge, section 5), and the
  conditional-grant resolver's IMPLEMENTATION (the request-path read plus
  dispatch), bridged to the shared-layer port the same way every other
  cross-module read in this series is bridged - one implementation, no
  drift. The resolver is a request-path read and MUST stay OUT of the
  bypass allowlist, exactly like the effective-permission resolver it sits
  beside (service-accounts.md section 9 makes the identical placement
  argument for its own resolver).
- **Clock.** The time-of-day evaluator reads the request-attribute bag's
  stamped time; the permission check stamps it from the injected clock,
  never a direct call to the platform's current-time function, so the
  whole feature stays testable end to end (section 3).
- **The permission catalogue is untouched.** A condition is a separate axis
  from a permission: it is never itself a permission atom, so the closed
  permission catalogue and its subset validation (multi-tenancy.md section
  8) need no change.
- **Deployment prerequisite, restated.** `ip_cidr` is meaningful only
  behind a forwarded-headers setup with an explicit trusted-proxy allowlist
  (section 3); ship that off by default (a starter cannot know an
  operator's proxy addresses) and document the obligation; `time_of_day`
  needs nothing extra and works immediately.
- **Deletability.** Drop the condition column (or simply leave it null
  forever), remove the Tier-2 fallthrough from the permission check, and
  unregister the evaluators. Tier 1 is unchanged RBAC, so removal degrades
  cleanly to today's behavior - the same bolt-on, cleanly-removable posture
  the rest of this series commits to.

## 9. Grow-into (documented, not built)

- **A real policy engine (Cedar, Open Policy Agent)**: register one
  evaluator for a `cedar` or `opa` condition type whose payload is a policy
  reference, projecting the request-attribute bag (widened as needed) into
  the engine's own entity or context shape. This is the section-18 "engine
  such as Cedar or OPA" multi-tenancy.md already names, and the seam is
  shaped for it (section 4) with zero change to the check, the resolver, or
  the schema.
- **Resource-attribute conditions**: a grant conditioned on a resource's
  label, status, or owner needs a richer resource contract than a plain
  owner-id. The request-attribute bag's resource-id slot is the seam; a
  resource-loading step would populate a resource-attribute view for the
  evaluator to read.
- **Boolean composition and multiple conditional grants of one role**: an
  all-of / any-of envelope, and/or letting a principal hold the same role
  at the same scope under several different conditions, which would widen
  the grant-uniqueness rule (section 2) to include a condition identity.
  Not needed for the seam; arbitrary logic is better served by the Cedar /
  OPA plug-in than by a bespoke mini-language.
- **Conditions on the tenant base role or other system roles**: conditions
  attach to custom-role grants only. Conditioning a system role would be a
  different mechanism entirely and is out of scope here.
- **Atomic create-service-account-with-conditional-role**: threading a
  condition through whatever atomic account-creation shortcut your product
  has, so an IP-restricted key and its conditional grant are created in one
  call instead of the two-step path section 6 describes.

## 10. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(feature-flags.md section 9; quotas.md section 11):

- **The segregation invariant (headline).** A caller holds a conditional
  grant for some permission whose condition is currently FALSE. The cached
  effective-permission set does NOT contain that permission - assert the
  SET directly, not only an endpoint's resulting status code, and cover
  EVERY grant-read path the resolver has (tenant scope and workspace scope,
  a direct grant and a team or service-account grant). Each path has its
  own "condition is absent" filter; an end-to-end status-code test alone
  would pass by coincidence whenever Tier 2's live evaluation happens to
  agree, so the direct assertion on every path is what actually guards the
  safety hinge. A companion unconditional grant of a different permission
  still resolves normally alongside it.
- **Live evaluation flips as attributes change, and the decision is never
  cached.** The SAME conditional `ip_cidr` grant: a request from an
  in-range IP is allowed, a request from an out-of-range IP is denied, back
  to back, with nothing about the grant itself changing between the two
  calls. The same for `time_of_day`, with the clock moved across the window
  boundary. This proves Tier 2 evaluates live against the request's own
  attributes rather than remembering an earlier answer.
- **The fail-closed matrix (section 7), each row its own test.** An unknown
  condition type denies; an evaluator that errors denies; `ip_cidr` with no
  resolvable client IP denies; a suspended member reaches no conditional
  grant either, mirroring the same active-membership gate the unconditional
  path already enforces.
- **Grant-time validation.** Creating a grant with a malformed condition (a
  bad CIDR, a non-`HH:mm` time, an unknown type) is rejected outright and
  writes no row; a well-formed condition is accepted and round-trips
  through the admin listing surface and the data export.
- **Cross-tenant invisibility.** One tenant's conditional grant is
  invisible to another tenant, under the same isolation boundary every
  other grant already sits behind.
- **The DSAR round-trip.** The condition value appears in the tenant's own
  data export, since it is tenant policy, not a secret; no secret is
  introduced anywhere by this feature, so the completeness check that
  already guards secret-field exclusion (data-export-and-erasure.md section
  8) stays green untouched.
