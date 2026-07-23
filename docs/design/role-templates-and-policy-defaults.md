# Global role templates and platform policy defaults: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how two operator-plane features grow out of the multi-tenancy control plane
in [docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into bullet in
that doc's section 18, "Global role templates and platform policy
defaults"): adapt the specifics to your stack, or skip either half if your
product does not need it. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the ninth
worked example grown out of that surface, after [audit-log.md](audit-log.md),
[service-accounts.md](service-accounts.md), [webhooks.md](webhooks.md),
[billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), [quotas.md](quotas.md),
[data-export-and-erasure.md](data-export-and-erasure.md), and
[in-app-notifications.md](in-app-notifications.md).

Two independent operator-plane features share one document because the
section-18 bullet groups them, not because they are mechanically related:
(A) GLOBAL ROLE TEMPLATES the platform operator seeds into every tenant, and
(B) platform POLICY DEFAULTS (password, session, lockout) the whole install
inherits. It builds on multi-tenancy.md's permission catalogue and
custom-role guardrails (section 10, which already reserves both of this
document's seams: a note that the super-admin plane may publish role
templates seeded into every tenant, and the plan-gated permission check
itself), its platform super-admin plane (section 13), its provisioning
atomicity (section 12), and its thin per-tenant token (section 5); read those
first. It also reuses billing-and-entitlements.md's plan-gated permission
check (section 5) and its super-admin catalogue-CRUD posture (section 8),
and audit-log.md's synchronous platform-audit write (sections 2 and 4) and
catalogue-completeness discipline (section 10). Being a generic reference,
it carries no build-sequence section (a concrete product's own design doc
would): treat every part as a menu, adopt the pieces your product needs.

## 1. The decision, up front

- **Both are operator-owned platform catalogues; tenants consume, they do
  not author.** Role templates and policy defaults carry no tenant
  discriminator, the same shape as the plans and feature-flag catalogues
  (billing-and-entitlements.md section 2; feature-flags.md section 2): a
  global vocabulary table, writable only through the platform-admin check on
  the privileged control-plane role, read by every tenant. A tenant never
  edits a template or a platform default directly; it receives a COPY (a
  role template becomes one of the tenant's own custom roles) or INHERITS a
  floor (a policy default the tenant may tighten but never loosen).
- **A role template is a SEED, not a live link.** Seeding a template into a
  tenant creates an ordinary tenant-owned custom role (multi-tenancy.md
  section 10), owned by that tenant from the moment it is created. After
  seeding, the copy is the tenant's: it may rename, re-permission, or delete
  it, and editing the template afterward does not retroactively change
  already-seeded copies. This is the standard "scaffold a sensible starting
  role" behavior (GitHub's default organization roles, Auth0's role
  templates), not a permanent binding.
- **The global-user model bounds where "a tenant may tighten" is even
  coherent, and the design says so honestly.** The section-18 bullet
  promises a tenant "inherits and may tighten" password, session, and
  lockout policy. That phrasing assumes tenant-scoped credentials. In this
  template, a user is GLOBAL (multi-tenancy.md section 1): registration and
  login happen with no tenant context, before any tenant is selected.
  Section 4 works through why this means password and lockout policy are
  install-wide by construction, while session policy is the one dimension a
  tenant can coherently tighten.
- **Tighten means tighten, enforced, never loosen.** Wherever a tenant
  override exists at all, it must validate to no LOOSER than the platform
  default (for the session lifetime this document builds, shorter is
  tighter); an attempt to set a looser value than the platform floor is
  rejected. The effective value is always `min(platform default, tenant
  override)`.

## 2. Role templates

A global `role_templates` catalogue, carrying no tenant discriminator
(operator vocabulary, the same shape as the plans and feature-flag
catalogues):

| column | type | notes |
|---|---|---|
| `key` | text | primary key; the stable template identifier |
| `name` | text, not null | the role name seeded into the tenant |
| `description` | text, not null | |
| `permissions` | array of text, not null | permission atoms from the closed catalogue (multi-tenancy.md section 8), validated against it on write |
| `assignable_scopes` | array of text, not null | `tenant` and/or `workspace` (the custom-role scope vocabulary, multi-tenancy.md section 10) |
| `created_at` / `updated_at` | timestamptz, not null | |

- **Authoring and validation.** The platform-admin check gates create,
  update, and delete on this catalogue - an endpoint filter (or your
  framework's equivalent middleware) admitting only the privileged
  control-plane role - audited synchronously on the platform audit log
  (`platform.role_template.created` / `.updated` / `.deleted`, the same
  synchronous-write pattern billing-and-entitlements.md section 7 and
  feature-flags.md section 6 use for their own catalogue edits). Write-time
  validation rejects any permission that is not a real catalogue atom, and
  rejects any owner-reserved permission outright: owner-reserved permissions
  (managing or deleting the tenant, ownership transfer, multi-tenancy.md
  section 8) can never appear in a custom role, so a template can never
  carry one either.
- **Seeding at provisioning.** Tenant provisioning (multi-tenancy.md section
  12), on the privileged path, after it creates the owner membership and
  INSIDE the same provisioning transaction, seeds one custom role per active
  template plus its permission rows, for the new tenant. Seeding is a cheap
  local write with no external I/O, so it belongs in the same commit as the
  rest of provisioning, not in a best-effort post-commit path. A seeded role
  carries a nullable `template_key` column pointing back at the catalogue: a
  re-seed is idempotent (skip a template already seeded for the tenant), and
  "which roles came from a template" stays answerable after the fact. A
  tenant-authored custom role has `template_key` null.
- **The seeding call must not open its own transaction - a load-bearing
  implementation note.** The ordinary, tenant-facing custom-role create path
  runs under the request-scoped, tenant-bound context, and whatever service
  method backs it almost certainly opens its OWN transaction unconditionally,
  because every other caller of it is a standalone request. Calling that
  method from inside the provisioning transaction, which is already open,
  either fails outright (many transaction APIs refuse a second, nested
  transaction on a connection that already has one) or silently produces two
  independent units of work where the design assumed one. The fix is to
  factor the shared work - filtering permissions against the plan, then
  inserting the role and its permission rows - into an internal,
  TRANSACTION-AGNOSTIC helper: a function that writes on whatever transaction
  is already open, with no opinion of its own about who started it. The
  tenant-facing, endpoint-driven create path wraps that helper in its own
  transaction; the provisioner calls the helper directly inside the
  transaction it already holds. (An alternative is a join-or-begin guard on
  the shared method itself - open a new transaction only if none is active -
  but a shared, transaction-agnostic helper is the cleaner seam, since it
  never has to ask "am I already inside one.")
- **A partial unique index is the race backstop for idempotency.** An index
  unique on `(tenant_id, template_key)` where `template_key is not null`
  means a concurrent bulk-seed and a concurrent new-tenant provision cannot
  double-seed the same template into the same tenant, mirroring the
  app-check-plus-database-constraint pattern a custom role's own key already
  uses. The application-level "skip if already seeded" check is the
  friendly, fast path; the index is what makes it safe under a race, not
  merely usually-safe.
- **Plan permissions are respected, never bypassed.** A template permission
  the tenant's plan does not grant (billing-and-entitlements.md section 5)
  is SKIPPED at seeding time - the seeded role gets the plan-allowed subset -
  never seeded in violation of the plan. A template is a convenience, not a
  permission-escalation path. On the default, unrestricted plan
  (billing-and-entitlements.md section 1), the fail-open default applies and
  the full template seeds unchanged. If filtering leaves a role with no
  permissions at all, the role is still created empty: an empty custom role
  is a valid, if useless, role, and the operator can widen the plan later
  without anything else to fix up.
- **Applying a template to tenants that already exist.** A platform-admin
  action seeds one template into every existing tenant, or a single named
  tenant, on demand - idempotently, guarded by the same `template_key`
  check. This is how a template defined after a tenant was already
  provisioned reaches that tenant: seeding is not only a provisioning-time
  event.
- **The tenant owns the copy.** A seeded role is visible through the
  existing tenant-facing custom-role surface (list, edit, delete, assign)
  with no new tenant-facing endpoint: it is an ordinary custom role that
  happens to carry a `template_key`. Deleting a seeded role is allowed, the
  same as deleting any other custom role the tenant authored itself.

## 3. Platform policy defaults

A single-row `policy_defaults` catalogue: a boolean `singleton` column,
primary key, fixed to `true`, with a check constraint so exactly one row can
ever exist.

```sql
create table policy_defaults (
    singleton                     boolean primary key default true,
    password_min_length           integer not null,
    access_token_lifetime_seconds integer not null,
    refresh_lifetime_seconds      integer not null,
    lockout_max_attempts          integer not null,
    lockout_duration_seconds      integer not null,
    updated_at                    timestamptz not null,
    constraint policy_defaults_singleton check (singleton)
);
```

| field | default | enforced at |
|---|---|---|
| `password_min_length` | 10 | register / set / change password |
| `access_token_lifetime_seconds` | 900 (15 minutes) | access-token issue |
| `refresh_lifetime_seconds` | 2,592,000 (30 days) | refresh-family issue |
| `lockout_max_attempts` | 10 | login |
| `lockout_duration_seconds` | 900 (15 minutes) | login |

- **Why a singleton, when every other operator catalogue here is
  multi-row.** The plans and feature-flag catalogues
  (billing-and-entitlements.md section 2; feature-flags.md section 2) are
  multi-row, with an `is_default`-style partial index picking out the active
  one. Policy defaults have no "which one is active" question at all - there
  is exactly one install, so there is exactly one row - and the singleton
  shape is simpler for that case: no demote-race, no default-flag to
  maintain. Call this out where you document it, so the next reader is not
  surprised this catalogue diverges from the plans/flags shape for a real
  reason, not an oversight.
- **Seeded once, by the same migration that creates the table, with today's
  constants as the row's values.** This is the reproducibility discipline
  the whole seed step exists to protect: the defaults ARE the current
  hardcoded values, so shipping this feature changes nothing about existing
  behavior until an operator deliberately edits the row.
- **A request-scoped policy-defaults reader** exposes the current values,
  read through the ordinary request path with no tenant boundary needed (a
  global catalogue, like the plans catalogue). A short, in-process,
  time-bound cache is worth adding, because the lockout fields sit on the
  login hot path - the one path already flagged as brute-force-exposed
  (section 5) - and per-request caching alone does nothing to reduce load
  under concurrent attack traffic hitting that path at once.
- **If the singleton row is ever absent** - a database that has not yet run
  the seed - the reader FAILS CLOSED to the built-in constant defaults, the
  same explicit-fallback discipline a default-plan lookup already uses when
  no default plan exists yet (billing-and-entitlements.md section 2). It
  never throws on the login or registration path; an operational gap in
  seeding must not turn into an outage in authentication.
- **The existing password-strength check's floor becomes config-driven; its
  CPU guard does not.** Wherever password validation reads a minimum-length
  constant today, that one check switches to read `password_min_length` from
  the reader. A maximum-length guard that exists purely to bound the cost of
  the password-hashing function (Argon2 or whichever your stack uses) is
  untouched: it is a resource-exhaustion guard, not a policy choice, and
  nothing about this feature should make it configurable.
- **A token-lifetime audit note: switch the MINT, not every reader, and keep
  one hard cap on the constant.** A hardcoded access-token or refresh-token
  lifetime is typically read from more than one place: the code that
  actually mints the token, and several call sites that report `expires_in`
  back to a client. Find every one of those readers before touching any of
  them. Only the mint itself should read the policy-defaults value and
  RETURN the resolved lifetime it used; every `expires_in`-reporting call
  site should report that returned value, not re-read the constant
  independently - a reported expiry that disagrees with the token's own
  claim is the exact bug this ordering avoids. One reader is the deliberate
  exception and must keep reading the literal constant: an impersonation
  grant's token-lifetime cap (multi-tenancy.md section 13) is a hard
  security ceiling on how long an impersonation session can run, and policy
  must never be able to widen it. Call this exception out explicitly in the
  code, not just in this document, so a future refactor does not "helpfully"
  make it config-driven too.
- **Options-validation bounds each field on write**: positive values only,
  and a sane maximum for each (nobody should be able to configure a
  zero-second lockout duration or a year-long access token through this
  surface).

## 4. The load-bearing subtlety: what "inherits and may tighten" requires

"A tenant inherits a platform default and may tighten it" sounds like one
uniform rule that should apply the same way to password, session, and
lockout policy. It is not, and treating it as one rule would ship a knob
that silently does nothing.

**The rule is only coherent where the enforcement point HAS a tenant
context to tighten within.** In a GLOBAL-user model (multi-tenancy.md
section 1: one account, many tenants, no tenant selected until after
sign-in), look at where each policy is actually enforced:

- **Password** is enforced at global register / set / change password. That
  path runs before any tenant is chosen, and a user with memberships in
  three tenants has exactly one password, full stop. There is no per-tenant
  password to tighten, because there is no per-tenant password at all.
- **Lockout** is enforced at global login, keyed on the credential. The same
  user has one login, shared across every tenant they belong to. A locked
  credential is locked everywhere at once; there is no tenant-scoped lock to
  tighten either.
- **Session** is different in kind, not degree. The per-tenant access token
  is minted only after a tenant is selected (multi-tenancy.md section 5), so
  it is genuinely scoped to one tenant at a time. A tenant CAN tighten its
  own session lifetime, because the enforcement point - minting that one
  tenant's token - sits inside the tenant context to begin with.

So the honest design is: platform defaults are set by the operator and
enforced install-wide for all three. Tenant TIGHTENING is built only for
session (section 6), where it is coherent, and DOCUMENTED as a deferred
grow-into for password and lockout (section 8), where it is not - not
omitted by oversight, but ruled out on the record until the user model
itself becomes tenant-scoped.

**Why this matters enough to say twice.** If a tenant-facing "tighten your
password policy" setting shipped anyway, it would validate, save, and return
success - and then enforce nothing, because the global password-check path
has no tenant to read that setting from in the first place. A tenant admin
would reasonably believe their tenant is stricter than it is. A design that
fakes a knob it cannot back is worse than one that is honest about a gap: it
fails silently, at the exact moment a security-conscious customer goes
looking for reassurance. Teach this pattern generally: before building a
"tenant may override X" feature, first confirm X is even resolved inside a
tenant-bound enforcement point. If it is not, tightening it per tenant is
not a smaller version of the feature - it is a different feature (making X
tenant-scoped in the first place), and it should be named and scoped as
that, not backed into as a side effect of a policy-defaults ticket.

## 5. Password and lockout (install-wide)

- **Password.** The existing password-strength check reads
  `password_min_length` from the policy-defaults reader (section 3) instead
  of a hardcoded constant; everything else about it (a breach-list check,
  the hash-cost guard) is unchanged. Raising the platform minimum applies to
  the next register or change; it does not retroactively invalidate existing
  passwords or force a rotation, the documented NIST position on password
  aging.
- **Lockout (new): brute-force protection at login, keyed on the
  credential.** The identity module's password-credential record gains a
  `failed_attempts` integer (default 0) and a nullable `locked_until`
  timestamp.
  - **On a login attempt where `locked_until` is set and still in the
    future**: reject with the same generic invalid-credentials response used
    for any other failed login, never a distinct "this account is locked"
    message - a distinguishable response would confirm to an attacker that
    the account exists and is currently under a lockout. A distinct locked
    response for a first-party UI is a documented, deliberate option
    (section 8), not the default.
  - **Timing-safe subtlety, load-bearing: the locked branch must still pay
    the password-hash cost before it returns.** It is tempting to
    short-circuit a locked credential before ever touching the password
    hasher - that is, after all, the entire point of a lockout, saving CPU
    on attempts that are going nowhere. Do not take that shortcut. An
    unknown email and a known-but-wrong password both pay the full hashing
    cost before failing; if a locked account instead returns immediately, it
    is measurably FASTER than both of those cases, and that timing gap is a
    real oracle: an attacker can distinguish "this credential does not
    exist," "this credential exists and the password is wrong," and "this
    credential exists and is currently locked" purely by response time, with
    no error message needed at all. The fix is to run the hash verification
    against a dummy or placeholder hash (or verify-and-discard the real one)
    on the locked branch too, paying the same cost as every other branch
    before returning the same generic answer. The CPU saving a lockout is
    supposed to provide comes from rejecting attempts BEFORE they retry, not
    from skipping the hash on the one attempt that does land while locked.
  - **On a wrong password**: increment the failed-attempt counter and
    conditionally set the lock in ONE standalone, atomic statement, with no
    ambient transaction held open around it. Holding a transaction across
    the hashing step would pin a pooled connection for the duration of a
    deliberately expensive computation, which is exactly the wrong thing to
    do under brute-force load; a read-then-write instead of a single atomic
    statement would race two concurrent wrong attempts against each other
    and could undercount. Express the threshold in the statement itself, so
    the database serializes concurrent attempts on the row and no increment
    is ever lost:

    ```sql
    update password_credentials
    set failed_attempts = failed_attempts + 1,
        locked_until = case
            when failed_attempts + 1 >= @max_attempts
                then @now + @lockout_duration
            else locked_until
        end
    where credential_id = @credential_id;
    ```
  - **On a successful verify**: reset the counter and clear the lock in one
    equally simple statement (`failed_attempts = 0, locked_until = null`).
  - **Auto-unlock is implicit, not a job.** Once `locked_until` is in the
    past, the very next attempt is allowed again, and a wrong one restarts
    the count from the top. Nothing needs to run on a schedule to "unlock"
    anything.
  - A non-password sign-in method (an external identity provider, say)
    carries no password credential and is unaffected by any of this.
  - **The accepted tradeoff, named because the user model makes it bigger
    than usual.** Lockout is a standard, accepted denial-of-service tradeoff
    in any system: an attacker who knows a victim's identifier can lock them
    out by deliberately failing the password enough times. In a
    GLOBAL-user model, that tradeoff has a materially larger blast radius
    than in a per-tenant system: locking the credential locks the user out
    of EVERY tenant they belong to, at once, not just one. This is accepted
    and documented here, not treated as a defect to silently work around;
    mitigations that shrink the blast radius (a distinct locked-status
    response with a retry-after, IP-based or progressive lockout that does
    not lock the shared account on a distributed attempt) are named as
    deferred work (section 8), not built here.

## 6. Session tightening: the one coherent per-tenant override

- A tenant gains a nullable `session_max_seconds` field: its own override on
  the per-tenant access-token lifetime. A tenant admin sets it through the
  tenant-admin control-plane surface (multi-tenancy.md section 16), behind
  an endpoint filter (or your framework's equivalent middleware) that checks
  a permission atom added to the closed catalogue for exactly this purpose
  (`settings:manage`, in the default admin role set) - distinct from the
  owner-reserved capability that manages or deletes the tenant itself
  (multi-tenancy.md section 8): tightening a session policy is an ordinary
  administrative act, not an act that touches the tenant's existence.
- **Validation is tighter-only.** A submitted override must be `<=
  access_token_lifetime_seconds` from the platform defaults; a looser value
  is rejected outright with a clear error naming the platform ceiling. The
  effective per-tenant session lifetime is always `min(platform default,
  tenant override)`, computed at the point of use, never stored as a
  separately-cached number that could drift from either input.
- **The cross-module seam is where this gets architecturally interesting.**
  The code that actually mints the per-tenant access token lives in the
  identity module - the same module that owns global registration and login
  (section 4) - and a well-kept module boundary forbids the identity module
  from reaching into a tenancy-owned table directly, the same discipline
  that keeps any two modules in this template from silently coupling to
  each other's schemas. So the override is read through a cross-module
  port, declared where the platform/shared layer already declares this kind
  of cross-module contract and implemented by the tenancy module, which
  owns the `session_max_seconds` field:

  ```
  resolve_session_override(tenant_id) -> integer | null   // the tenant's own override, if any
  ```

  The identity module depends on this port through whatever
  dependency-injection or service-location mechanism your stack uses, never
  on the tenancy module directly. The token issuer resolves the effective
  lifetime as `min(platform default, port.resolve_session_override(tenant_id)
  or platform default)` - the same tighter-only rule from above, just
  evaluated where the mint actually happens.
- **Resolve on every mint path that can carry a tenant, not only the obvious
  one.** A tenant-select operation is naturally endpoint-mediated - only one
  composition-layer entry point calls it - so resolving the override there
  is straightforward. A token-refresh operation is easy to overlook, because
  it may otherwise have no reason to touch anything tenancy-related at all;
  but a refresh that carries a tenant claim must consult the same port too.
  Skipping it there means a tenant that tightens its session policy AFTER a
  token was already issued does not see the shorter lifetime take effect
  until that token's natural expiry, which could be the very platform
  default the tenant is trying to shrink. Resolving on refresh means the
  very next rotation honors the current override - re-resolved fresh each
  time, never a value captured once at tenant-select time and carried
  forward stale. This does add one port read to the refresh path whenever a
  tenant claim is present; that is the accepted cost of the override being
  genuinely live rather than fixed at first mint.
- Only the per-tenant access token is affected by any of this. The
  refresh-family lifetime and a token minted before any tenant is selected
  stay install-wide, because neither one is scoped to a single tenant to
  begin with.
- This is the worked example of "inherits and may tighten," built on the one
  dimension where the global-user model makes it coherent (section 4).
  Password and lockout tightening would follow the identical tighter-only
  shape the day the user model itself becomes tenant-scoped (section 8) -
  the mechanism here transfers unchanged, only the enforcement point moves.

## 7. Events and audit

- Role-template create/update/delete and policy-default updates are
  platform-operator actions, audited synchronously on the platform audit log
  through whatever narrow, platform-owned write interface your audit design
  uses (audit-log.md sections 2 and 4, the same posture already used for
  granting a platform admin or editing the plans catalogue). Both are added
  to the completeness check's explicit not-audited set where relevant
  (audit-log.md section 10), since they are audited synchronously rather
  than through the async projection consumer.
- Seeding a template into a tenant creates ordinary custom-role rows through
  the tenant's normal role-creation path; the existing role-created event
  already covers that side. No new tenant-scoped event is needed for seeding
  itself.
- A tenant setting its own session override rides a tenant-scoped
  settings-changed event: fold this field into whatever general
  tenant-settings-updated event your product already emits, or introduce one
  if it does not yet have any tenant-level settings worth an event of their
  own.

## 8. Deferred (documented grow-into, not built)

- **Tenant tightening of PASSWORD and LOCKOUT policy.** Coherent only once
  credentials are tenant-scoped, not global (section 4): the
  effective-is-tighter mechanism built for session (section 6) transfers
  unchanged the day the user model changes; until then, only session
  tightening is built, and this gap is a deliberate, documented one, not an
  oversight.
- **A distinct locked-status response** (instead of the enumeration-safe
  generic invalid-credentials answer) for a first-party client that wants to
  show "this account is locked, try again in N minutes" - at the cost of the
  enumeration protection section 5 chooses by default.
- **Live re-seeding and a drift report**: which tenants have diverged from a
  template since it was seeded, and a deliberate "re-apply this template's
  current definition everywhere" bulk action, beyond the idempotent,
  seed-once-per-template action this document builds.
- **Per-tenant password composition or rotation rules**, and IP-based or
  progressive (exponential-backoff) lockout, beyond the fixed
  count-and-duration lockout this document builds.

## 9. Placement and deletability

The role-templates catalogue, the policy-defaults catalogue and its reader,
and the session-override port all belong in the platform/shared layer, not
inside any business module - the identical placement argument audit-log.md
section 9, data-export-and-erasure.md section 12, and
in-app-notifications.md section 8 each make for their own cross-cutting
piece: both catalogues are read by every tenant and written only through the
platform-admin plane, and neither depends on any one module's data. The
tenancy module implements the session-override port (it owns the field the
port resolves), and the identity module consumes it, but the port's
declaration itself lives with the other cross-module contracts the
platform/shared layer already owns.

**Deletability**: drop the `role_templates` catalogue, its CRUD surface, the
provisioning-time seeding step, and the `template_key` column (the seeded
custom roles it leaves behind stay valid, ordinary tenant-owned roles -
deleting the marker only stops future re-seed detection from working, it
does not touch existing role or permission rows). Drop the `policy_defaults`
catalogue and its reader, reverting the password check and the token
issuers to their original constants - the exact values the seed step wrote
in the first place, so this is a clean revert, not a behavior change. Drop
the `failed_attempts` and `locked_until` columns and the login-time lockout
branch. Drop the tenant's `session_max_seconds` field, the settings surface's
validation of it, and the tighter-only resolution at the mint. The system
roles, the custom-role engine itself, and the base authentication flows are
all untouched by any of this coming out.

## 10. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(audit-log.md section 10; data-export-and-erasure.md section 13):

- **Role-template CRUD.** The platform-admin check admits create, update,
  and delete; a non-operator caller is refused. A write containing an
  unknown permission atom, or an owner-reserved one, is rejected.
- **Seeding, plan-filtered.** Provisioning a new tenant seeds every active
  template as a tenant-owned custom role; on a plan with a restricted
  grantable-permission set, the seeded role holds only the plan-allowed
  subset, never the full template; on the default, unrestricted plan, the
  full template seeds.
- **Idempotent re-seed.** Re-running seeding for a tenant that already has a
  given template does not create a second role for it; the partial unique
  index holds under a forced concurrent double-seed.
- **The tenant owns its copy.** A tenant can rename, re-permission, or
  delete a seeded role through the ordinary custom-role surface, exactly as
  it could for a role it authored itself; editing the template afterward
  does not change the already-seeded copy.
- **Policy-default enforcement.** Raising `password_min_length` causes a
  password that used to pass to be rejected on the next register or change;
  changing `access_token_lifetime_seconds` changes the lifetime of the next
  token issued, and the value reported to the caller matches the value the
  token actually carries.
- **Fail-closed fallback.** With the `policy_defaults` row absent, the
  reader returns the built-in constant defaults rather than throwing, and
  login and registration both keep working.
- **Lockout, including the timing-safe locked branch.** N wrong passwords
  lock the credential; a subsequent attempt with the CORRECT password still
  fails while locked, with the same generic response as any other failure;
  the locked branch's response time is not measurably faster than a
  non-locked wrong-password attempt (the branch pays the hash cost); a
  correct attempt after `locked_until` elapses (pin the clock) succeeds and
  resets the counter to zero; a non-password sign-in method is unaffected.
- **Session tighten-only validation.** A tenant override `<=` the platform
  default is accepted and the next mint reflects it; an override greater
  than the platform default is rejected; a tenant with no override inherits
  the platform default unchanged; a token refreshed after the tenant
  tightens its override reflects the new, shorter lifetime rather than the
  value in effect when the token was first minted.
