# Enterprise SSO (OIDC) and SCIM provisioning: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how per-tenant enterprise single sign-on and directory provisioning grow out
of the multi-tenancy control plane in
[docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "SSO (SAML/OIDC) and SCIM"): adapt the specifics to
your stack, or skip it if your product has no enterprise buyer asking for it
yet. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the
eleventh worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), [quotas.md](quotas.md),
[data-export-and-erasure.md](data-export-and-erasure.md),
[in-app-notifications.md](in-app-notifications.md),
[role-templates-and-policy-defaults.md](role-templates-and-policy-defaults.md),
and [mfa-totp.md](mfa-totp.md).

It builds directly on multi-tenancy.md's global-user model (section 1: one
account, many tenants, membership is per tenant), its isolation boundary and
tenant-owned-row convention (section 2), its layered authorization checks
(section 6, the tenant-role gate this feature's config surface reuses), its
closed permission catalogue (section 8), its provisioning atomicity (section
12, the shape just-in-time provisioning mirrors for a brand-new user), its
thin per-tenant token and tenant-context resolution (section 5), and its
offboarding lifecycle (section 17: a SCIM deprovision drives the same
member-deactivation path an admin removal already does). It also reuses
role-templates-and-policy-defaults.md's `settings:manage` permission atom and
its tenant-tightening session-override port (section 6), service-accounts.md's
hashed-bearer-credential pattern and request-inspecting authentication
selector (sections 2 to 3), and data-export-and-erasure.md's sensitive-field
completeness discipline (section 8). Read those first. Being a generic
reference, it carries no build-sequence section (a concrete product's own
design doc would): treat every part as a menu, adopt the pieces your product
needs.

**Built as an integration SEAM, deliberately, not a from-scratch protocol
stack.** Hand-rolling a full SAML stack or a complete SCIM 2.0 server is
below-par and the most expensive option available at the same time: a
well-known footgun class (XML signature-wrapping in SAML, the sprawl of SCIM
filtering and PATCH semantics) that a starter template has no business taking
on before a single enterprise customer has asked for it. The right
engineering call is a CORRECT minimal path over a standards-compliant OIDC
identity provider configured per tenant, plus a SCIM 2.0 Users skeleton, with
the full protocol surface documented as grow-into (section 8). OIDC, not
SAML, is the protocol this document builds: it is the modern default, and,
where the identity module already implements a first-party social sign-in
(Google, Microsoft, GitHub, or similar, which is itself an OIDC
authorization-code exchange plus id_token validation), this seam is that same
flow generalized to a per-tenant configurable issuer instead of one hardcoded
provider. SAML is a documented grow-into (section 8): its extra XML
signature-wrapping care is exactly why it is not the protocol built first.

## 1. The decision, up front

- **SSO is per-tenant enterprise login: a tenant configures its own OIDC
  identity provider** (Okta, Microsoft Entra ID, Google Workspace, Auth0) and
  its members sign in through it. This is distinct from the product's own
  first-party social sign-in (a consumer convenience, one issuer, globally
  trusted): enterprise SSO is a tenant's corporate directory federating INTO
  that one tenant, and every tenant's identity provider is independently
  configured and tenant-CONTROLLED. That difference in trust shape is the
  reason section 2 below is the most important section in this document.
- **The OIDC flow is a minimal, correct authorization-code exchange over a
  per-tenant configured issuer.** The security-critical validation (a
  verified issuer, an audience matching the tenant's client id, a signature
  check against the identity provider's own published keys, `nonce` plus
  `state`) is not hand-waved by "it's just a seam" - it is the part that must
  be exactly right, and it is spelled out in full in section 4.
- **Just-in-time (JIT) provisioning links or creates the user INTO the
  configured tenant, and only that tenant.** On a first SSO sign-in, the
  verified email resolves to an existing global user (link a new
  authentication method to it) or a new user (create one), and a membership
  in the SSO tenant is provisioned just-in-time. A user is provisioned only
  into the tenant whose identity provider authenticated them, never an
  arbitrary tenant chosen from anywhere else in the request.
- **SCIM is the directory's push channel; SSO is the login pull.** The two
  are independent, and either can ship without the other. SCIM (System for
  Cross-domain Identity Management, RFC 7643 and RFC 7644) lets the tenant's
  identity provider PROVISION and, crucially, DEPROVISION members from the
  directory side - and a SCIM deprovision drives the exact same
  member-deactivation and offboarding path an admin removal already does
  (multi-tenancy.md section 17). The seam built here is a SCIM 2.0 Users
  skeleton: the standard resource shape, core CRUD, and deactivate, all
  authenticated by a per-tenant bearer token. Groups-to-teams mapping, PATCH,
  and filtering beyond the one filter a real client needs are documented
  grow-into (section 8).

## 2. Data model, and the critical fix that makes it safe

A tenant-owned, isolated `sso_configs` record, one per tenant, holding the
per-tenant OIDC identity provider:

| column | type | notes |
|---|---|---|
| `tenant_id` | uuid | primary key (one identity provider per tenant) |
| `issuer` | text, not null | the identity provider's OIDC issuer (authority) |
| `client_id` | text, not null | the product's client id AT the identity provider (the id_token audience) |
| `client_secret_encrypted` | text, not null | the client secret, encrypted at rest by a secret-encryption service, write-only, never exported (data-export-and-erasure.md section 8) |
| `enabled` | boolean, not null | SSO is off for the tenant until an admin turns it on |
| `created_at` / `updated_at` | timestamptz, not null | |

The existing authentication-method record (whatever table your stack already
uses to bind a user to one login method: a password credential, a first-party
social login, and now SSO) gains an `issuer` column, and its returning-user
lookup for the SSO kind becomes COMPOUND.

**This is a critical auth-boundary fix, not a convenience, and it deserves
being read twice.** Say a system's existing match for a returning user is
`(kind, provider_subject)`, with a unique index on those two columns. That
shape is safe for a first-party social login kind ONLY because the social
provider is a single, globally-trusted issuer whose subject namespace is that
provider's own and unforgeable by anyone else. Enterprise SSO breaks that
assumption on purpose: a per-tenant identity provider means the `sso`
authentication-method kind is SHARED across every tenant's own,
independently-configured, tenant-CONTROLLED identity provider. Matching a
returning user on `(kind=sso, subject)` WITHOUT the issuer is a cross-tenant
account takeover, and here is exactly how it happens:

1. A malicious tenant admin configures their own OIDC identity provider for
   their own tenant (their own keys, their own issuer). Nothing about this
   step looks abusive on its own: configuring your own tenant's identity
   provider is the entire feature working as designed.
2. That admin mints (or has their identity provider mint) a token asserting a
   `sub` value equal to a VICTIM user's known subject id at some OTHER,
   unrelated identity provider.
3. Every per-token check the flow runs (issuer matches the configured issuer,
   audience matches, signature verifies, nonce matches) passes, because all
   of it is under the attacker's own control: it is their issuer, their keys,
   their token.
4. If the returning-user lookup matches on `(kind=sso, subject)` alone, this
   token now resolves to the VICTIM's existing global user account, and the
   attacker is signed in AS the victim - skipping any email-based
   account-linking check entirely, because the flow believes it has already
   found the returning user by subject and has no reason to look at email at
   all.

**The fix**: add the `issuer` column, make the SSO unique index
`(kind, issuer, provider_subject)` instead of `(kind, provider_subject)`, and
match a returning SSO user on `(kind=sso, issuer, subject)`, where `issuer` is
the one that JUST validated the current token, never a issuer read from
anywhere else. A first-party social-login kind keeps its original
`(kind, provider_subject)` shape unchanged: it has exactly one issuer, so
there is nothing for the issuer column to disambiguate there, and adding it
would be a no-op at best. (The compound key also fixes a real, if less
dangerous, functional bug for free: two different tenants' identity
providers could otherwise assign the same `sub` value to two different
people and collide on the old two-column unique index, breaking
provisioning for the second tenant to hit it.)

**Why a single trusted social issuer does not have this problem, stated
plainly, because the contrast is the whole teaching point.** A social login
provider is one issuer the whole product trusts unconditionally: nobody but
that provider can mint a token bearing that issuer's signature, so a subject
value under that issuer is unforgeable by any other party, and matching on
subject alone is safe. Enterprise SSO deliberately hands each TENANT its own
issuer, chosen and configured by that tenant. The moment more than one
mutually-untrusted party can each configure "an issuer," the issuer stops
being a constant the system can silently assume and becomes a value that must
be part of every lookup key, every time. This is a general lesson worth
carrying into any other multi-issuer feature a product adds later, not a
one-off fact about this table.

A tenant-owned, globally-unique-per-domain `sso_domain_claims` record routes
sign-in traffic to the correct tenant, ONE ROW PER DOMAIN:

| column | type | notes |
|---|---|---|
| `tenant_id` | uuid, not null | the tenant this domain routes to |
| `domain` | citext (or your stack's case-insensitive text type), not null | globally unique across every tenant, never just per-tenant |
| `verified_at` | timestamptz, null | null = claimed but not yet verified; only a verified claim routes (section 3) |
| `created_at` | timestamptz, not null | |

A per-tenant `allowed_domains` array (the simpler-looking alternative) has NO
cross-tenant exclusivity: two tenants could both claim `contoso.com`, and a
`contoso.com` login would route to whichever tenant's config the lookup
happened to match first, possibly an attacker's own identity provider
(a direct credential-phishing setup). A GLOBAL unique index on the normalized
domain makes a duplicate claim a hard CONSTRAINT VIOLATION that an
operator-approval process cannot silently miss (section 3), not merely a
policy convention someone has to remember to enforce by hand.

A tenant-owned `scim_tokens` record holds the per-tenant SCIM bearer
credential, following the exact hashed-bearer-credential pattern
service-accounts.md section 2 already establishes for an API key:

| column | type | notes |
|---|---|---|
| `id` | uuid | primary key |
| `tenant_id` | uuid, not null | the isolation discriminator |
| `token_hash` | text, not null | a one-way hash of the SCIM bearer token (shown once, at creation or rotation), globally unique for the tenant-less lookup - the identical API-key pattern |
| `created_by` / `created_at` | | |
| `revoked_at` | timestamptz, null | rotate or revoke |

Both `sso_configs` and `scim_tokens` are tenant-owned and sit under the tenant
isolation boundary (a tenant's own SSO configuration and SCIM token are its
own, and no other tenant's request path can read them). `client_secret_encrypted`
and `token_hash` are the two fields this feature marks SENSITIVE: excluded
from the tenant's self-serve data export and redacted in an operator erasure
snapshot, which the completeness check data-export-and-erasure.md section 8
already runs automatically once a field carries that marker. Both tables also
join the tenant-owned-table declaration this same document's erasure
mechanism sweeps (data-export-and-erasure.md section 4).

## 3. Configuration and domain routing

- A tenant admin manages the SSO configuration, its domain claims, and the
  SCIM token through the tenant-admin control-plane surface
  (multi-tenancy.md section 16), gated by the SAME `settings:manage`
  permission atom role-templates-and-policy-defaults.md section 6 already
  introduces for tightening a tenant's session policy: setting up enterprise
  SSO is an ordinary administrative act on the tenant's own settings, not an
  owner-reserved act that touches the tenant's existence, so no new
  permission atom is needed. An admin can set the issuer, client id, and
  secret, add or remove domain claims, enable or disable SSO, and rotate the
  SCIM token. The client secret is write-only: set on save, never readable
  back, encrypted at rest the moment it is written.
- **Minting or rotating the SCIM token is refused outright under an
  impersonation or support session.** A support session impersonating a
  tenant is meant to end when the impersonation does; minting a new,
  standing, tenant-scoped bearer credential while inside one would let that
  access outlive the impersonation itself, which is exactly the shape of a
  persistence vector a fail-closed design refuses to create. Whatever
  surface starts a support-impersonation session in the first place must be
  checked and refused here, the same discipline any other long-lived
  credential mint should apply once a product has an impersonation feature
  at all.
- **The `issuer` MUST be HTTPS, rejected outright at config-save time.** A
  loopback or plain-http issuer is sometimes allowed for a local integration
  test's fake identity provider; a free-text, admin-supplied, per-tenant
  issuer must never inherit that escape hatch, because a plain-http issuer
  weakens the discovery-document and JWKS fetch to straightforward network
  tampering (an attacker on the path swaps the keys the flow will trust).
  Reject any issuer that is not `https://` at the `settings:manage` save
  endpoint; keep the local-dev loopback exception, if your test suite needs
  one, confined to the test host's own configuration and never reachable
  through the tenant-facing save path.
- **Domain routing is SP-initiated: a login begins with an email address.**
  Its domain is matched against `sso_domain_claims` to find the tenant whose
  identity provider owns it, and the caller is redirected there. The match
  MUST be EXACT, case-insensitive equality on the whole domain string, never
  a suffix or substring test - `notcontoso.com` matching an approved
  `contoso.com` claim is exactly the kind of bug a naive "ends with" check
  introduces. A domain claim is a real takeover vector on its own (a tenant
  claiming `gmail.com` outright would capture every Google account holder
  who ever tries to sign in through this path), so it is defended by TWO
  independent controls, both load-bearing: the GLOBAL unique index from
  section 2 makes a domain claimable by at most ONE tenant ever, and a claim
  only ROUTES once `verified_at` is set, by an operator's manual approval or
  a documented DNS-TXT verification flow (section 8). An unverified or
  unclaimed domain routes nowhere. Either control alone is not enough:
  uniqueness without verification lets any tenant claim any domain first-come;
  verification without uniqueness lets a second tenant claim an
  already-verified domain and race the router.

## 4. The OIDC sign-in flow: the security-critical part

Authorization-code flow, run per tenant, over that tenant's own configured
identity provider:

1. **Initiate** (for example `GET /auth/sso/start?email=...` or
   `?tenantId=...`): resolve the tenant's enabled SSO configuration; build the
   identity provider's authorize URL carrying `client_id`, `redirect_uri`,
   `scope=openid email profile`, a random `state` value (the CSRF defense), a
   random `nonce` value (the replay defense), and an S256 PKCE
   `code_challenge` (defense-in-depth against code interception, the current
   OAuth 2.1 recommendation for every client type, not only public/native
   ones). Store a SINGLE-USE, server-side record keyed by `state`, holding:
   the RESOLVED tenant id, the `nonce`, the PKCE `code_verifier`, a short
   time-to-live, and, when `/start` was called from an already-authenticated
   in-app session (the "link SSO into my existing account" entry point, as
   opposed to the unauthenticated, email-driven routing entry point), the
   caller's own user id. Whatever cookie or client-side handle carries the
   `state` value back to the caller must be marked HttpOnly, Secure, and
   SameSite=Lax (not Strict: Lax is what survives the top-level GET redirect
   the identity provider sends back after login; Strict would silently drop
   the cookie on that redirect and break every single sign-in). Redirect to
   the identity provider.
2. **Callback** (for example `GET /auth/sso/callback?code=...&state=...`):
   look up the server-side `state` record; reject a missing, expired, or
   mismatched one outright, and consume it (single-use, so a replayed
   callback with the same `state` fails on its second use).
   **The tenant id used for every remaining step of this callback comes ONLY
   from that stored `state` record, and is NEVER re-derived from the
   callback request's own parameters or from any claim inside the token
   itself.** An attacker who tampers with a callback query parameter, or who
   controls what claims their own identity provider asserts, must not be able
   to steer which tenant's configuration the callback resolves against; the
   `state` record is the single source of truth for that decision, full
   stop, because it was written by the server itself at `/start` time, before
   any attacker-controlled input entered the flow.
   Re-resolve the tenant's SSO configuration from that tenant id and
   RE-CHECK `enabled == true` at THIS point in time, not only at `/start`
   time - this makes disabling SSO mid-incident an actual kill switch: an
   admin who disables SSO while a malicious code exchange is already
   in flight stops it here, rather than the disable only taking effect on
   the next `/start` call.
   Exchange the authorization `code` at the identity provider's token
   endpoint using `client_id`, the DECRYPTED `client_secret`, and the PKCE
   `code_verifier`, over HTTPS, and then VALIDATE the returned `id_token` on
   every one of these dimensions, none of them optional and none of them
   skippable on any code path:
   - **signature**, verified against the identity provider's own published
     keys (JWKS), fetched from the CONFIGURED issuer's own discovery document
     and cached (never a hardcoded or client-supplied key set), with the
     signing algorithm PINNED to the identity provider's expected asymmetric
     algorithm (for example RS256), never accepted from whatever the token's
     own header happens to claim. "Verified against the JWKS" alone is not
     the whole story: an attacker who controls the `alg` header can assert
     `alg=none` and skip signature verification outright, or, against a
     validator naive enough to reuse a public signing key as if it were a
     shared HMAC secret, forge a symmetric signature that same JWKS lookup
     would wrongly accept. Pinning the expected algorithm up front and
     rejecting any token whose header claims a different one closes both;
   - **`iss`** exactly equal to the tenant's configured `issuer` - this is
     what PINS the token to THIS tenant's identity provider and is a direct
     continuation of the section-2 fix: without this exact-match check, an
     otherwise well-formed token from the WRONG tenant's identity provider
     could still pass every other check;
   - **`aud`** exactly equal to the tenant's configured `client_id`;
   - **`exp` and `nbf`** current (the token is neither expired nor not yet
     valid) and **`nonce`** equal to the one stored in the `state` record
     (the replay defense actually being checked, not merely generated);
   - **`email_verified`** must be `true` - an identity provider that has not
     itself verified the email address must never be allowed to link or
     create an account off that email, the same fail-closed reading any
     first-party social login flow already applies.
   Any single failure among these collapses to one generic SSO error
   response; none of them is an optional hardening pass layered on top of a
   "working" flow. All of them together are what makes the flow correct at
   all.
3. **Just-in-time provision or link, into the SSO tenant, and only that
   tenant.** First, attempt to match a RETURNING user by
   `(kind=sso, issuer, subject)` - and the issuer here is exactly the one
   that just finished validating in step 2, never read from anywhere else,
   which is the section-2 fix doing its actual job at the point that
   matters: one tenant's identity provider can never assert another
   tenant's subject and match a real user by doing so. If there is no
   returning match, resolve by the token's verified email through an
   account-linking decision: if `/start` was called from an authenticated
   in-app session (step 1's link-into-my-account entry point), the SSO method
   links straight onto that caller's own user id, since the caller already
   proved who they are by holding a live session. If `/start` was the
   unauthenticated, email-routing entry point and the email matches a
   DIFFERENT existing user, the flow fails CLOSED to "confirmation required"
   rather than auto-linking - a redirect flow that arrives with no session at
   all carries no proof that the person completing it is the owner of that
   existing account, so silently attaching a new login method to somebody
   else's account on the strength of an email match alone is exactly the kind
   of account-takeover-by-mistake a fail-closed design avoids. A brand-new
   email, with no existing user at all, creates one. Once the user is
   resolved (existing or new), ensure a MEMBERSHIP in the SSO tenant, created
   just-in-time if it does not already exist, with the tenant's default
   member role. The user is provisioned ONLY into the tenant whose identity
   provider just authenticated them: linking an SSO method to an existing
   global user grants that user access to THIS tenant alone, since a
   membership is always per-tenant and no other tenant's access is touched by
   any of this.
4. **Mint the session for that tenant.** Unlike a first-party login, which is
   tenant-less until the caller separately selects a tenant afterward
   (multi-tenancy.md section 5), the SSO caller is already IN the tenant the
   moment the callback resolves, so the session minted here is tenant-bound
   directly. **This mint MUST apply the tenant's own session-lifetime
   tightening, and skipping this is a real regression, not a cosmetic gap.**
   Reuse the exact `resolve_session_override(tenant_id)` cross-module port
   role-templates-and-policy-defaults.md section 6 already builds for the
   ordinary tenant-select mint path, and thread it through here identically;
   a session-minting path that instead passes "no override" unconditionally
   would silently hand every SSO login the platform DEFAULT lifetime even
   when the tenant has tightened it - a regression aimed precisely at the
   enterprise customer who is paying for SSO in the first place, and
   arguably the customer segment MOST likely to have tightened that setting.
   SSO bypasses the product's own second factor only if the identity provider
   itself asserted an equivalent (an `amr` claim check, section 8, a
   documented grow-into); by default, a user who separately enrolled MFA
   still hits the MFA challenge on next login, unchanged.
- A new `sso` authentication-method kind stores the `issuer` column (section
  2) plus `provider_subject` (the identity provider's own stable `sub`
  value), matched on `(kind, issuer, subject)` and never on email alone
  (an email address can change at the identity provider, and matching on
  email would reopen a version of the same cross-tenant ambiguity issuer-less
  matching creates).

## 5. SCIM 2.0 provisioning: the skeleton

- A dedicated `/scim/v2/Users` surface, authenticated by its own scheme: an
  `Authorization: Bearer scim_...`-shaped credential resolves, by
  `token_hash`, to its owning tenant, using the identical tenant-less
  hash-lookup pattern service-accounts.md section 3 already establishes for
  an API key. Concretely, this is the SAME request-inspecting selector
  pattern that document introduces (a selector that looks at the shape of
  the incoming credential and routes to the matching authentication path),
  gaining one more branch: a `scim_`-prefixed bearer routes to the SCIM
  handler instead of the ordinary session/token path or the API-key path,
  and every SCIM operation then runs scoped to the resolved tenant, under the
  tenant isolation boundary, for the rest of the request.
- **A SCIM bearer authenticates ONLY the SCIM surface, never anything else,
  and this is a hard boundary, not a convention.** It authenticates the
  `/scim/v2` routes alone and can NEVER act as a general tenant-admin
  credential. It is also, deliberately, NOT an RBAC principal: possession of
  the tenant-scoped bearer is the SOLE authority for the SCIM surface, so the
  SCIM routes themselves carry no permission or role check to bypass. Three
  independent, stack-agnostic defenses hold that boundary together: (a) a
  request reaches the SCIM authenticator only when it BOTH carries the
  SCIM-token shape AND targets a SCIM path - a `scim_` bearer presented on
  any other route is simply not authenticated there and gets a 401, never a
  fallthrough to some other scheme; (b) the SCIM route group is itself
  pinned to accept ONLY the SCIM authentication scheme, so even a routing
  mistake that somehow forwarded another credential type at it still cannot
  get in; (c) the SCIM principal is NON-RESOLVING - it carries the resolved
  tenant and nothing else, no user identity that any permission or role
  lookup would ever resolve, so an accidental authorization check added to a
  SCIM route later fails CLOSED instead of silently passing. A faithful
  implementation proves all three with a regression test that asserts a
  valid SCIM token is refused (401 or 403) on a non-SCIM tenant route.
- Core operations map a SCIM User resource onto a tenant membership:
  - `POST /Users` (provision): create-or-invite a member of the resolved
    tenant from the SCIM user payload (`userName` as the email, `active` as
    the initial state). **The global user this creates is born UNVERIFIED
    and passwordless** - a directory shell with no proven email address and
    no credential of its own yet, deliberately, not an oversight: the
    member's first real SSO login then CLAIMS that shell through the exact
    same account-linking path already described in section 4 (the
    unverified-account branch), with no new code path needed. A shell born
    VERIFIED instead would hit that same member's first login against the
    "email already belongs to a verified account, confirmation required"
    branch and lock them out of the very account SCIM just created for them.
    Idempotent on the external id or the email, so a directory's periodic
    reconciliation sweep can safely re-submit the same user without creating
    a duplicate - a repeat provision returns the same user, never a second
    one.
  - `GET /Users/{id}` and `GET /Users?filter=userName eq "..."` (the ONE
    filter expression a real SCIM client needs for reconciliation; broader
    filtering is grow-into, section 8): return the standard SCIM User
    resource shape for the matching member, including the identity
    provider's own per-member external identifier (`externalId`), stored
    against the membership at provisioning time and preserved unchanged
    across every subsequent `GET` and `PUT` so the directory's own
    reconciliation sweep can line its record up against ours.
  - `PUT /Users/{id}` (replace) and the `active` flag on it:
    **`active=false` DEACTIVATES the member, driving the exact same
    member-deactivation path an admin's own manual removal already drives**
    (multi-tenancy.md section 17). This is the entire point of adopting
    SCIM in the first place: a directory-side offboard (an employee leaves
    the customer's company, gets removed from their corporate directory)
    cuts that person's access to every connected application, including
    this one, immediately, with no admin anywhere having to remember to also
    remove them by hand. `active=true` reactivates a previously deactivated
    member.
  - `DELETE /Users/{id}`: deactivates (soft), never a hard delete - the
    audit trail for who was a member, and when, is worth keeping even after
    a directory-driven removal.
  - **Two guards sit under all three of the operations above.** The
    tenant's LAST OWNER can never be deactivated through this path: the
    status flip checks for that before it runs, and an attempt that would
    leave a tenant ownerless returns a SCIM error instead, never a silent
    lockout and never a server error. Deactivating an already-deactivated
    member, or reactivating an already-active one, and a repeated `DELETE`
    against an already-deactivated member, are each an idempotent no-op that
    returns success without a second state change - a directory sync retries
    relentlessly, and it must never see a state-transition error just for
    asking twice.
- The inbound SCIM request binds ONLY a safe, fixed attribute set -
  `userName`, `externalId`, `active` - so nothing else the payload carries
  has anywhere to land. This matters concretely because a real identity
  provider (Okta, by default) sends `roles`, `groups`, and other
  entitlement-shaped attributes on that same payload unasked: since the
  binding step never deserializes them, they are IGNORED BY CONSTRUCTION,
  not merely unused afterward, which closes a privilege-escalation path that
  would otherwise smuggle a role or entitlement grant in through a feature
  this skeleton has not built yet (`/Groups`, section 8).
- Response bodies follow the standard SCIM 2.0
  `urn:ietf:params:scim:schemas:core:2.0:User` resource shape (`id`,
  `userName`, `active`, `emails`, `externalId`, `meta`), so that a real
  identity-provider SCIM client (Okta, Microsoft Entra ID, or any RFC
  7643/7644-compliant directory) interoperates without a custom integration
  on the customer's side. A SCIM list response
  (`GET /Users?filter=...`) uses the standard SCIM
  `urn:ietf:params:scim:api:messages:2.0:ListResponse` shape, and a SCIM
  error response uses the standard SCIM
  `urn:ietf:params:scim:api:messages:2.0:Error` shape, instead of the
  product's own general-purpose success and error envelope. That is a
  DELIBERATE deviation, scoped ONLY to the `/scim/v2` surface, because a real
  SCIM client validates responses against those exact shapes and has no idea
  what to do with anything else. `PATCH` (partial operations), `/Groups`
  (mapping to teams, the section-18 grow-into bullet's other committed
  half), bulk operations, and full filtering are documented grow-into
  (section 8): the skeleton built here is the resource shape, the core CRUD,
  and the deactivate-drives-offboarding link, which together are the
  behavior that actually matters to a customer adopting SCIM.
- SCIM provisioning is a control-plane write on the resolved tenant. It runs
  on the ordinary request path, scoped by the SCIM token's resolved tenant
  under the tenant isolation boundary, reusing the same invitation and
  membership machinery a human admin's own member-management actions already
  use, and it emits the SAME membership events those actions already emit -
  so a directory-driven change is audited and webhook-deliverable with no new
  event type needed anywhere.

## 6. Events and audit

- SSO configuration changes and SCIM-token rotation are ordinary tenant-admin
  actions on the tenant's existing audited settings surface: fold them into
  whatever general tenant-settings-updated event your product already emits,
  or add dedicated tenant-scoped events (an `sso configured` /
  `scim token rotated` shape) to the deliverable catalogue if your product
  wants a more specific event type - either way, audited and
  webhook-deliverable like any other tenant-admin action.
- An SSO SIGN-IN reuses the product's existing session and login events
  unchanged; a just-in-time provision additionally emits the same
  membership-created event an invitation acceptance already emits
  (multi-tenancy.md section 12).
- SCIM provision and deprovision emit the SAME membership-created and
  member-deactivated events an admin's own add or remove action already
  emits, so the tenant audit log and any registered webhooks cover the
  directory-driven changes with no new plumbing anywhere in the event
  catalogue.

## 7. Placement and deletability

- The SSO configuration and its sign-in flow live in the identity module (it
  already owns authentication), reading the per-tenant configuration through
  a cross-module port the tenancy module implements, mirroring the exact
  seam role-templates-and-policy-defaults.md section 6 already establishes
  for the session-override read:

  ```
  resolve_tenant_sso_config(tenant_id) -> { issuer, client_id, client_secret, enabled } | null
  ```

  The identity module must never reach into a tenancy-owned table directly -
  the same module-boundary discipline that keeps any two modules in this
  template from silently coupling to each other's schemas - so this port,
  like `resolve_session_override`, is declared where the platform/shared
  layer already declares this class of cross-module contract, and
  implemented by the tenancy module, which owns the `sso_configs` table the
  port reads.
- The SCIM endpoints live in the API layer, over the tenancy module's
  existing membership surface, reusing its invitation and member-management
  operations rather than duplicating them behind a second code path.
- **Deletable.** Drop `sso_configs`, `sso_domain_claims`, and `scim_tokens`
  plus their migration; drop the SSO `/start` and `/callback` endpoints and
  the `sso` authentication-method kind (and its `issuer` column, if no other
  kind is using it); drop the SCIM endpoints and their bearer-authentication
  branch; drop the two sensitive-field markers this feature adds. First-party
  login (password, or the product's own social sign-in) is entirely
  untouched by any of this coming out, since the SSO flow was added
  alongside it, never woven into it.

## 8. Deferred (documented grow-into, not built)

- **SAML 2.0** as a second SSO protocol, for the enterprise laggard identity
  providers that still expect it, with its own signature-validation care
  (XML canonicalization and signature-wrapping defenses are a materially
  larger surface than validating a signed JSON token) - this is the exact
  reason OIDC is the protocol built first, not SAML.
- **OIDC identity-provider metadata auto-discovery**
  (`.well-known/openid-configuration`), so an admin supplies only the issuer
  and the rest of the configuration (authorize endpoint, token endpoint,
  JWKS location) is fetched automatically, and **DNS-TXT domain
  verification**, so a tenant can prove ownership of a routing domain itself
  instead of waiting on operator approval (section 3's current gate).
- **Identity-provider-initiated SSO** (a sign-in that starts from the
  identity provider's own app launcher tile rather than this product's own
  login page), and **`amr`/`acr`-based step-up** (trusting an identity
  provider's own asserted multi-factor claim to skip the product's own
  second factor, rather than always re-challenging it).
- **Full SCIM**: `/Groups` mapped onto teams and roles (the other half of
  the committed section-18 bullet; the skeleton here ships Users only,
  Groups is the direct next layer), `PATCH` partial operations, complex
  filtering beyond the one expression built here, `/ServiceProviderConfig`
  plus `/Schemas` plus `/ResourceTypes` discovery endpoints, and bulk
  operations.
- **SCIM-triggered role or team assignment driven from directory group
  membership** (the committed "maps directory groups to teams and roles"
  half of the section-18 bullet): once `/Groups` exists, a group's members
  can drive team membership and role grants the same way `active=false`
  already drives deactivation today.

## 9. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(audit-log.md section 10; data-export-and-erasure.md section 13):

- **OIDC validation matrix (the security-critical core).** A callback
  carrying a bad, missing, expired, or already-consumed `state` is rejected.
  An `id_token` with the wrong `iss`, the wrong `aud`, a bad signature, an
  expired `exp`, a not-yet-valid `nbf`, a mismatched `nonce`, or
  `email_verified=false` is each independently rejected - one test per
  dimension, not one test that only ever exercises the happy path plus a
  single generic failure case. Only a token that passes every dimension at
  once provisions a user and mints a session.
- **Cross-tenant identity-provider takeover is blocked (the section-2
  fix, proven, not just argued in prose).** Two tenants each configure their
  own identity provider. Tenant B's identity provider asserts a `sub` value
  equal to a real user's subject at tenant A's identity provider. Signing in
  through tenant B's flow must NOT resolve to tenant A's user: the
  `(kind, issuer, subject)` match, keyed on the issuer that actually
  validated THIS token, is what a regression test pins down directly, by
  constructing exactly this cross-issuer collision and asserting it fails to
  match.
- **Just-in-time provisioning scoping.** A first SSO sign-in creates the user
  plus a membership in the SSO tenant, and no other tenant. A returning SSO
  user is matched by `(issuer, subject)`, not by email. An authenticated
  in-app "link SSO" call links onto the caller's own account. An
  unauthenticated redirect whose email matches a DIFFERENT existing user
  fails closed to "confirmation required" rather than auto-linking.
- **Domain routing.** An email in a tenant's approved, VERIFIED domain routes
  to that tenant's identity provider. An unapproved, unclaimed, or
  not-yet-verified domain routes nowhere. A near-miss domain (a superstring
  or substring of an approved one) does not match.
- **SSO session tightening.** A tenant that has tightened its session
  lifetime (role-templates-and-policy-defaults.md section 6) gets that
  tightened lifetime on an SSO-minted session too, not the platform default -
  proven by minting through the SSO callback specifically, not only through
  the first-party tenant-select path the port was originally built for.
- **SCIM provisioning and isolation.** A valid SCIM token provisions a member
  (`POST /Users`). `active=false` deactivates the member and their access is
  actually cut (a subsequent request from that member is refused, not merely
  a flag flipped with no enforcement behind it). `GET ?filter=userName eq`
  finds the right member. A wrong or revoked token is rejected. Tenant A's
  SCIM token can never read or write tenant B's members, under the tenant
  isolation boundary, even when the request is otherwise well-formed.
- **Secret handling.** The `client_secret_encrypted` value and the SCIM
  `token_hash` never appear in the tenant's self-serve data export or an
  operator's pre-erasure snapshot - the same completeness check
  data-export-and-erasure.md section 8 already runs against every field
  marked sensitive, exercised here against these two new fields
  specifically.
