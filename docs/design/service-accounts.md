# Service accounts and API keys: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a non-human, API-key-authenticated principal type grows out of the
multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "API keys, service accounts, PATs"): adapt the
specifics to your stack, or skip it if your product has no
machine-to-machine callers. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It builds
directly on multi-tenancy.md's generalized RBAC (section 8: permissions,
roles, and grants) and reuses the tenant-less hash-lookup pattern that
invitation accept already established (section 12); its lifecycle actions
also tie into [audit-log.md](audit-log.md)'s event-catalogue discipline
(sections 2 and 10). Read those first. Being a generic reference, it
carries no build-sequence section (a concrete product's own design doc
would): treat every part as a menu, adopt the pieces your product needs.

## 1. The decision, up front

- **A service account is a non-human principal that authenticates with a
  hashed API key and carries scoped RBAC grants, not a membership.** A human
  is a `user` principal with a membership row (a base role) plus optional
  grants; a service account is a `service_account` principal with NO
  membership and NO base role at all - its effective permissions are exactly
  the grants assigned to it, nothing more (section 4). This is the GCP
  model: a service account is a first-class principal you grant roles to,
  not a lesser kind of user. Simplified for a starter template: one active
  key per service account, rotatable.
- **The key is a bearer secret, stored only as a hash, shown once.** It
  mirrors whatever one-time-token pattern your product already uses for
  invitation and password-reset tokens (a high-entropy random secret, hashed
  once with a fast one-way hash, never a password-style KDF), the same
  "GitHub / Stripe API key" rationale most products already apply to their
  refresh tokens: a high-entropy secret needs no key-stretching, and the
  server keeps only the hash. The raw key is returned exactly once, at
  create and at rotate, and never again in any form.
- **A service-account request flows through the identical authorization path
  as a user request.** The permission check reads the caller's id and asks
  the same permission resolver for the caller's effective permissions; it
  does not care whether the caller is human. The only code that even knows a
  service account exists is the resolver's own active-membership step, which
  gains one additional branch (section 4). Everything downstream - the
  permission gate, tenant scoping, row-level isolation - is unchanged.
- **Revocation is immediate, because there is no token to wait out.** Unlike
  a session token or a signed JWT (valid until it expires), an API key is
  re-resolved from its hash on every request, so revoking or rotating a key
  takes effect on the very next call. An API key is, if anything, MORE
  responsive to revocation than a typical access token, not less.
- **PATs and multiple keys per account are documented extensions, not built
  here.** A personal access token (a key that acts AS a user, inheriting
  that user's own membership) and more than one active key per service
  account are natural follow-ons; section 9 notes where each hangs off this
  model without a rewrite.

## 2. The credential

The raw key has a recognizable shape: a short literal prefix followed by a
large random secret, for example `sk_<32+ random bytes, base64url-encoded>`.
The prefix is deliberate, for two independent reasons: it is what secret
scanners (GitHub secret scanning, gitleaks, and this repo's own gitleaks
gate per CLAUDE.md's hard rules) match on, so a leaked key is detectable
with high confidence instead of looking like an arbitrary string; and it is
how the authentication layer distinguishes an API key from a session token
or JWT on the wire, before it has looked anything up (section 3). Persisted
on the service-account row:

- **key hash**: a one-way hash of the raw key (SHA-256 or equivalent is
  enough - the secret is already high-entropy, so no password-style
  key-stretching is needed), the same hashing idiom your invitation and
  one-time tokens already use. This is the lookup key, and it is GLOBALLY
  unique, not merely unique per tenant, enforced by a global unique index
  or constraint (section 5 explains why that is correct even under
  tenant-row isolation).
- **display prefix**: the first several characters of the raw key (for
  example `sk_ab12cd`), stored in clear, purely for display, so an admin's
  list view can tell two keys apart without the secret ever being
  retrievable from anything stored.

Whatever module or package already owns your token-hashing helpers is the
natural home for a matching one here (new-key / hash / display-prefix), one
more instance of a pattern your invitation tokens and one-time tokens
already established, rather than a new hashing scheme invented for this
one feature.

## 3. Authentication: a second scheme, added additively

A new API-key authentication path is added ALONGSIDE the existing
session/token authentication path, additively, leaving the existing path's
own behavior completely unchanged:

- A request-inspecting selector decides, per request, which of the two
  paths runs: if the credential looks like an API key (a recognizable
  prefix on the bearer value, or a distinct header such as `X-Api-Key`), the
  request goes down the API-key path; anything else goes down the existing
  session/token path, unchanged. Every mainstream stack has an equivalent
  seam for this branch point: a forwarding/policy authentication scheme in
  ASP.NET, an ordered chain of Passport strategies in Node, an ordered chain
  of Warden strategies in Rails, a chain of security filters in Spring, an
  ordered list of authentication middlewares in Go. What matters, regardless
  of stack, is that the SELECTOR is the only new piece; the existing
  scheme's own logic is not touched.
- The unauthenticated CHALLENGE - what an unauthenticated request to a
  protected endpoint gets back - stays the existing scheme's challenge,
  always. The API-key path is additive to the already-protected surface; it
  never becomes the default challenge, and no new anonymous-fallback policy
  is added, so anonymous surfaces (health checks, generated API docs) stay
  exactly as open, or closed, as they were before this feature existed.
- On the API-key path, the handler reads the credential, hashes it, and
  resolves it to `(tenant, service account)` using the SAME tenant-less
  hash-lookup pattern the invitation-accept flow already established
  (multi-tenancy.md section 12): a lookup keyed only by the hash, with no
  tenant bound yet, because the tenant is exactly what the lookup is about
  to produce. This lookup runs on the privileged, cross-tenant path (the
  bypass path, multi-tenancy.md section 2), never on the ordinary
  tenant-scoped path, for the identical reason invitation-accept's token
  lookup does: there is no tenant to scope it to until the lookup resolves
  one.
- A miss - unknown key, revoked key, or expired key - collapses to exactly
  one outcome: authentication failure. A caller cannot distinguish "wrong
  key" from "revoked" from "expired" by probing, the same one-outcome
  discipline invitation accept already applies to its own token lookup.
- On a hit, the handler establishes the request identity as `(tenant,
  service account)`, marking the principal type so downstream code can tell
  it apart from a user when it needs to (section 4). That is the same two
  facts an authenticated user request establishes - tenant and principal -
  just naming a different kind of principal. The single choke point that
  binds every request to its tenant (multi-tenancy.md section 3) runs
  exactly as it does for a user request, with no new code: it only ever
  cared what tenant, never whether the principal was human.

## 4. Authorization: the resolver's service-account branch

A service-account request flows through the IDENTICAL permission-check path
as a user request: the same per-request effective-permissions resolution
(multi-tenancy.md section 8), keyed off the caller id and principal type the
authentication step established, refusing whenever the resolved permission
set does not include what the endpoint requires. One consequence worth
naming explicitly: any endpoint a service account is meant to reach must
already be gated on a specific permission (multi-tenancy.md section 8's
finer gate), not on the coarser tenant-role capability check
(multi-tenancy.md section 6, the owner/admin/member tier) - a service
account has no tenant-role tier to satisfy at all, since it has no
membership row in the first place.

The ONLY divergence is inside permission resolution itself:

- **User principal**: unchanged. Resolution checks the active-membership
  gate, adds the membership's base-role permission set, and unions in every
  grant the user holds directly or through a team (multi-tenancy.md
  sections 8 and 9).
- **Service-account principal**: resolution SKIPS the membership gate and
  the base-role step entirely - a service account has neither - and
  resolves permissions ONLY from the grants held directly by that
  service-account principal, at the requested scope (tenant, or the
  requested workspace). No team union: a service account cannot belong to a
  team. Fail-closed: a service account created with no grant resolves to
  the empty permission set, and every permission check on every endpoint
  refuses it.

**Owner-reserved permissions are structurally unreachable**, with no
separate carve-out needed. Multi-tenancy.md section 8 already forbids
owner-reserved permissions (managing or deleting the tenant, ownership
transfer) from ever appearing in a custom role, for any principal; since a
service account can only ever hold permissions through that same
custom-role grant machinery, the existing guardrail already forecloses the
path before this feature adds anything. A key can never be minted into
tenant takeover.

**TWO further permissions are refused to a service account specifically**,
on top of that: the permission that authors and assigns custom roles
(`roles:manage`, already in the catalogue per multi-tenancy.md section 8)
and the permission that manages service accounts themselves
(`api-keys:manage`, introduced by this feature, section 7). Both are
self-escalation primitives: holding the first lets a principal author a new
role from the whole non-owner-reserved catalogue and assign it to itself;
holding the second lets a principal mint itself further keys. Granting a
role whose permission set intersects either one to a service-account
principal is refused outright, at both direct grant and at
create-with-an-initial-role, so there is no side door around the block.

Why this matters more for a non-human principal than for a supervised human
admin: a human admin who holds `roles:manage` is a session-bound,
interactive actor. Every use of that permission is a deliberate act by a
person, attributable to them, and bounded by whatever session length, MFA,
and account-security controls already gate that person's own sign-in. A
service account holding the same permission is a scriptable, always-on,
unattended credential: if it is ever leaked or over-scoped, the SAME leak
that hands an attacker its current permissions also hands them the means to
use `roles:manage` (or `api-keys:manage`) to mint broader
permissions or entirely new keys for itself, with no human decision point
anywhere in that chain and no session to expire or log out of. A single
leaked key holding either permission would be a silent, unattended path to
near-total tenant compromise; refusing both to every service account closes
that path structurally, rather than relying on whichever admin mints a key
to remember never to grant them. A service account can still hold real
operational power (a members-management or settings-management permission,
say) - what it specifically cannot do is expand its OWN authority without a
human in the loop.

Granting a role to a service-account principal validates that the principal
exists and is neither revoked nor past its expiry, the same shape as
multi-tenancy.md's existing rule that a user principal must be an active
member and a team principal a real team: a revoked or expired service
account can no more receive a new grant than a suspended member can.

## 5. Data model

A `service_accounts` table, tenant-owned and under the same authoritative
boundary as every other tenant table (multi-tenancy.md section 2):

- **id**: primary key, and also the principal id every grant refers to.
- **tenant id**: not null, the isolation discriminator, same as every other
  tenant-owned row.
- **name**: an admin-facing label.
- **key hash**: a one-way hash of the raw key (section 2). GLOBALLY unique,
  not merely unique per tenant, enforced by a global unique index -
  because the lookup that resolves a key is tenant-less (section 3): the
  tenant is the lookup's OUTPUT, not an input it could filter on, so
  whatever guarantees a hash maps to exactly one account cannot itself be
  scoped by tenant. This is not a conflict with row-level isolation: your
  isolation mechanism still governs which rows an ordinary tenant-scoped
  query can SEE, while a global uniqueness constraint separately governs
  which rows can EXIST at all. Existence-uniqueness answering to a
  different scope than read-visibility is two independent guarantees, not
  one weakening the other.
- **display prefix**: clear-text, for admin display (section 2).
- **created by**: the admin or owner who created it.
- **timestamps**: created at, plus the usual.
- **last used at**: nullable, throttled (section 6).
- **expires at**: nullable; a key past it fails to resolve.
- **revoked at**: nullable; set on revoke; a revoked key fails to resolve.

A service account holds permissions through the SAME grant table every
other principal uses (`role_assignments`, multi-tenancy.md sections 8 and
14), with a third principal-type value alongside `user` and `team`
(multi-tenancy.md section 9): no new grant machinery, no parallel
permissions table. The grant table's principal-existence validation
(section 4) gains the service-account branch; wherever your stack documents
that validator, correct it to name all three principal types once this
ships.

A `(tenant id)` index serves the tenant-admin list read; the global unique
index on the key hash is the only thing the resolve (section 3) reads
directly.

## 6. last_used tracking without a per-request write

Writing `last_used_at` on every authenticated request would put a write on
the hot authentication path for every single call - exactly the kind of
per-request write this design otherwise goes out of its way to avoid (the
tenant-less hash lookup is already the only extra read the API-key path
adds). Instead, the update is THROTTLED and COALESCED into the same single
statement that performs the resolve: update `last_used_at` to the current
time only when it is null or older than a configured threshold (five
minutes is a reasonable default). A key hammered by a busy client then
writes at most once per threshold window, not once per call.

The consequence is that `last_used_at` is APPROXIMATE by design, accurate
only to the throttle window, not to the call. That is the right trade for
what the column is FOR: a coarse "is this key still active, and roughly
when" signal for an admin's list view. It is deliberately not the record of
any specific call. The exact per-call record is the audit log (section 7),
which needs the exact time regardless of any throttle, has its own write
path already built to carry it, and does not share this column's economy
goal in the first place.

## 7. Lifecycle

All lifecycle actions are gated by the `api-keys:manage` permission
(section 4), added to the catalogue and to the default admin role set, and
- like any non-owner-reserved permission - grantable in a custom role too.

- **Create**: accepts a name and, optionally, an initial role plus a scope
  (tenant-wide, or a specific workspace). When a role is given, the
  service-account row and its grant are created in the SAME transaction,
  mirroring scope-aware invitations (multi-tenancy.md section 11), so the
  account is immediately usable instead of landing with no permissions and
  a required second step. A service account created with no role has no
  permissions until one is granted - the safe default, and consistent with
  fail-closed resolution (section 4). The raw key is returned in the
  response body EXACTLY once, at creation, and is never retrievable again
  in any form.
- **List**: returns id, name, display prefix, created, last-used, expiry,
  and revoked state. NEVER the secret and never the hash. The same
  keyset-pagination contract every other list read in the product already
  uses.
- **Rotate**: mints a new secret, replaces the stored hash and display
  prefix, and returns the new raw key once. The old secret stops working
  IMMEDIATELY - there is exactly one active hash at a time, so there is
  nothing left for the old key to be valid against. A grace window where
  the old key keeps working briefly alongside the new one is a documented
  extension (section 9): it needs a second hash column with its own
  expiry, not a redesign.
- **Revoke**: marks the account revoked. The key fails to resolve starting
  on the very next request - unlike a session token, there is no validity
  window left to wait out. Its existing grants are left in place but
  inert: a revoked account cannot authenticate at all, so the grants confer
  nothing while it stays revoked. Un-revoking is deliberately not offered;
  mint a new account instead, so "revoked" stays a one-way, unambiguous
  state.
- **Expiry**: an optional expiry timestamp set at creation. Once passed,
  the resolve treats the key exactly like a miss.

Every one of these actions - create, rotate, revoke - emits a domain event,
and each MUST be picked up by the audit projection (audit-log.md section
2's tenant-scoped event catalogue) or explicitly named as a deliberate
exception (audit-log.md section 10's catalogue-completeness test). That is
not incidental: those sections exist precisely so that adding a new
administrative action is always a conscious decision to audit it or to name
it not-audited, never a silent gap a reviewer has to notice by absence. A
service account's lifecycle actions are exactly the kind of "who did what,
to what, and when" event the tenant audit log exists for, so the
expectation here is that all three are audited, not exempted.

## 8. Security posture

- The raw key is never logged and never persisted anywhere; only its hash
  and display prefix are stored. A key that ends up in a log line or a chat
  message is compromised the moment it does, independent of anything else
  this design gets right.
- The prefix (section 2) is what makes a leaked key catchable in the first
  place: secret-scanning tools match on a recognizable, high-entropy
  prefix, and a bare random string with no such marker is far harder for any
  scanner to flag with confidence.
- The only cross-tenant step anywhere in this design is the tenant-less
  hash lookup (section 3), and it returns exactly one of two shapes:
  `(tenant, service account)` for a live key, or one generic miss for
  everything else (unknown, revoked, expired) - the identical discipline
  invitation-accept's own token lookup already uses (multi-tenancy.md
  section 12).
- Rate limiting applies to API-key requests exactly as it does to every
  other request, so a leaked key is still throttled, not a free pass around
  the limiter.
- Revocation and rotation are both immediate: a key is re-resolved from its
  hash on every request rather than trusted for a validity window the way a
  session token is, so there is no token lifetime to wait out.
- Self-escalation is blocked structurally (section 4): a leaked or
  over-scoped key is bounded by the grants it was given and cannot use the
  leak itself to bootstrap to more.

## 9. Placement, deletability, and extensions

The service-account row, its resolver, and its admin-facing lifecycle
operations belong in whichever module already owns tenants, memberships,
and grants (multi-tenancy.md section 16's dedicated tenancy module): the
resolver reached through that module's bypass allowlist, the RBAC branch
running on the ordinary tenant-scoped request path alongside every other
permission check. The authentication scheme or handler itself belongs at
the edge, next to wherever the existing session/token authentication is
already wired up, since it is the one piece that is genuinely about the
transport-level credential rather than about tenancy.

**Deletability**: drop the table, the authentication scheme, the lifecycle
endpoints, the `service_account` principal-type literal, and the
`api-keys:manage` permission atom, and the user authentication path
is completely untouched - the same bolt-on, cleanly-removable posture the
rest of the tenancy layer already commits to (multi-tenancy.md section 16).

Three extensions hang off this model without a rewrite:

- **PATs (personal access tokens, act-as-user)**: a key whose principal is
  a USER rather than a service account, resolving to that user's own
  membership and grants - the existing user permission-resolution path
  (section 4), reached through an alternate credential rather than an
  alternate resolver. A separate credential row keyed to a user id is
  enough; nothing about permission resolution itself changes.
- **Multiple keys per service account**: split the credential out of the
  service-account row into its own table (one account, many hash rows), so
  rotation can overlap instead of being instantaneous, and individual keys
  can be named and revoked one at a time without touching the others.
- **Key scopes narrower than a role**: an OAuth-style scope string carried
  on the key itself and intersected with the resolved permission set at the
  gate (section 4) - additive to the existing check, not a replacement for
  it.

## 10. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring audit-log.md section 10's own
framing:

- **Authenticates and is authorized by its grants.** A service account
  created with a role holding one permission can call an endpoint gated on
  that permission using its key, and is refused (403) on an endpoint gated
  on a permission it lacks. One created with no role is refused everywhere
  - fail-closed.
- **Tenant isolation.** A service account's key resolves only its own
  tenant; it can never read another tenant's data even with a fully valid
  key, the same isolation guarantee every other tenant-scoped caller gets
  (multi-tenancy.md section 15).
- **Revoke, rotate, and expiry all take effect immediately.** A revoked key
  is refused on the very next request; after rotation, the old key is
  refused and the new one works, with no token lifetime to wait out; a key
  past its expiry is refused the same way.
- **The secret is shown once and stored only hashed.** The create and
  rotate responses carry the raw key; the list response never does; the
  stored hash is not, and cannot be turned back into, the raw key.
- **Owner-reserved permissions are unreachable.** Attempting to create or
  grant a service account an owner-reserved permission is refused, because
  the catalogue already forbids it in any custom role (section 4) - there
  is no separate carve-out to test around.
- **The permission gate treats it identically to a user.** The same
  permission-gated endpoint admits a user holding the permission and a
  service account holding it, and refuses both without it, through the
  identical code path.
- **Self-escalation is blocked.** Assigning a role containing the
  role-authoring permission or the service-account-management permission to
  a service account is refused, at both direct assignment and
  create-with-an-initial-role; the identical role assigns fine to a user.
- **last_used tracking is throttled.** Two rapid authenticated calls
  advance `last_used_at` at most once within the throttle window, never
  once per call.
- **Audited.** Create, rotate, and revoke each land a row in the tenant
  audit log, and the catalogue-completeness test (audit-log.md section 10)
  still passes with all three new event types accounted for.
