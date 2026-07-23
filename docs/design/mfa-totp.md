# MFA / TOTP (two-factor authentication): a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a per-user TOTP second factor grows out of the multi-tenancy control
plane in [docs/design/multi-tenancy.md](multi-tenancy.md) (the grow-into
bullet in that doc's section 18, "MFA/TOTP"): adapt the specifics to your
stack, or skip it if your product does not need a second factor. Docs-first
applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the tenth
worked example grown out of that surface, after
[audit-log.md](audit-log.md), [service-accounts.md](service-accounts.md),
[webhooks.md](webhooks.md), [billing-and-entitlements.md](billing-and-entitlements.md),
[feature-flags.md](feature-flags.md), [quotas.md](quotas.md),
[data-export-and-erasure.md](data-export-and-erasure.md),
[in-app-notifications.md](in-app-notifications.md), and
[role-templates-and-policy-defaults.md](role-templates-and-policy-defaults.md).

Unlike most of the surface this series has grown out of, MFA is not a
tenant-owned catalogue and does not live in the platform/shared layer: it is
a pure identity-module feature. MFA is a property of the GLOBAL user (the
same global-user model role-templates-and-policy-defaults.md section 4
works through for password and lockout policy: multi-tenancy.md section 1,
one account, many tenants, no tenant selected until after sign-in), enrolled
per user and enforced at global login, before any tenant is chosen. No
tenant is involved and no tenancy code changes (a tenant REQUIRING MFA of
its members is a documented grow-into, section 11, the same shape of gap
role-templates-and-policy-defaults.md section 4 names for tenant-tightening
password and lockout policy). It builds directly on
role-templates-and-policy-defaults.md section 5 (the password-credential
lockout mechanism this feature reuses for its own brute-force guard) and
section 4 (why an install-wide, global-user policy cannot fake a per-tenant
knob it cannot back); read those first. Being a generic reference, it
carries no build-sequence section (a concrete product's own design doc
would): treat every part as a menu, adopt the pieces your product needs.

## 1. The decision, up front

- **TOTP (RFC 6238) as the second factor, the industry-standard
  authenticator-app method** (Google Authenticator, 1Password, Authy): a
  shared secret plus a 30-second time step yields a 6-digit code. No SMS
  (SIM-swap-prone, a below-par choice), no proprietary push. WebAuthn /
  passkeys are the stronger modern option and a documented grow-into
  (section 11); TOTP is the universal baseline a starter should ship.
- **Two-step login.** Password stays the first factor. After the password
  verifies, if the user has CONFIRMED MFA, login does NOT issue a session;
  it returns an MFA challenge, and a second endpoint exchanges the challenge
  plus a valid TOTP (or recovery) code for the session. A user without
  confirmed MFA logs in exactly as today, in one step.
- **The secret is recoverable and encrypted at rest, not hashed.** Verifying
  a TOTP code needs the raw shared secret, so, unlike a password, it cannot
  be hashed. It is encrypted with a key-management / secret-encryption
  service (the same protect/unprotect pattern webhooks.md section 5 uses
  for a webhook signing secret, for the identical reason: the server has to
  get the plaintext back, not merely confirm a match against it), so it is
  never stored in clear and every replica decrypts with the same persisted
  keys.
- **Recovery codes are the lost-authenticator escape hatch, and they ARE
  hashed** (high-entropy random, one-time, the same SHA-256 discipline
  service-accounts.md uses for an API key).
- **The TOTP algorithm is pinned by the RFC's own official test vectors.**
  RFC 6238 is small and precisely specified; a hand-rolled implementation
  built on a standard HMAC-SHA1 primitive is verified against the RFC 6238
  Appendix B golden vectors, so no new crypto dependency is taken. (A
  vetted TOTP library is the alternative; the hand-rolled-plus-golden-vector
  path avoids a dependency and is correctness-verified on its own terms,
  section 3.)

## 2. Data model (identity module)

Unlike the tenant-owned platform catalogues this series otherwise builds
(the audit log, webhooks, notifications), these tables carry no
`tenant_id` and do not live in the platform/shared layer: they sit
alongside the identity module's other global-user credential tables (the
user record, the password credential), scoped by `user_id`, exactly like
the password credential itself. MFA is not a tenant-owned concept, so it is
not under row-level tenant isolation and needs none.

A per-user credential row, one per user (`mfa_credentials`):

| column | type | notes |
|---|---|---|
| `user_id` | uuid | PK (one MFA enrollment per user) |
| `secret_encrypted` | text, not null | the TOTP shared secret, encrypted at rest (never stored in clear) |
| `confirmed_at` | timestamptz, null | null = enrollment begun but not confirmed (MFA NOT enforced yet); set on the first valid confirm code |
| `last_step` | bigint, null | the last time-step a code was accepted for (the replay guard, section 3) |
| `failed_attempts` | integer, not null, default 0 | failed verify-endpoint attempts against this user's challenge (section 6) |
| `locked_until` | timestamptz, null | set once `failed_attempts` crosses the threshold; cleared on a successful verify |
| `created_at` | timestamptz, not null | |

A recovery-codes table, hashed one-time (`mfa_recovery_codes`):

| column | type | notes |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid, not null | |
| `code_hash` | text, not null | SHA-256 hex of the code; the code itself is shown once and never stored |
| `used_at` | timestamptz, null | one-time: set when consumed, a used code never works again |
| `created_at` | timestamptz, not null | |

- An `mfa_credentials` row with `confirmed_at = null` means enrollment is
  pending and MFA is NOT enforced at login; only `confirmed_at != null`
  gates login.
- Putting `failed_attempts` / `locked_until` on the credential row itself,
  rather than on the ephemeral challenge token, is what makes the
  brute-force guard (section 6) survive across challenges: the lock lives
  with the USER, not with any one login attempt.

## 3. The TOTP algorithm: two hand-rolled components, both pinned

This is a teaching point worth stating plainly: a hand-rolled crypto or
encoding routine is only as safe as its test suite, and here there are TWO
such routines, not one. Skipping the pin on either leaves a hole in the
safety net the other one closes.

- **The HOTP/TOTP core** (RFC 6238, built on RFC 4226's HOTP): HMAC-SHA1
  over an 8-byte, big-endian time-step counter (`floor(unixSeconds / 30)`),
  the standard dynamic-truncation to a 31-bit integer, then `mod 1,000,000`
  for 6 digits (zero-padded left to 6). The secret is 20 random bytes
  (160 bits, the RFC's recommended HMAC-SHA1 key size).
- **Golden-vector test against RFC 6238 Appendix B (the load-bearing
  correctness gate).** RFC 6238's own published vectors are 8-DIGIT codes;
  this feature uses 6 digits, and the correct 6-digit value is the LAST six
  of the 8-digit value (`fullCode mod 1,000,000`), NOT the first six - a
  real, silent interop trap: a byte-order or truncation bug that takes the
  first six digits instead can pass a shallow smoke test and still be
  wrong, because a wrong prefix and a wrong suffix are both syntactically
  valid 6-digit strings. State the derivation in the test itself and assert
  the adapted 6-digit expected values for the SHA-1 vectors directly (T=59
  -> `287082`, T=1111111109 -> `081804`, T=1111111111 -> `050471`, each
  derived as the low six digits of the RFC's own published `94287082` /
  `07081804` / `14050471`), so a byte-order or truncation bug fails the
  build, not a manual reading of the spec.
- **Base32 (RFC 4648) is a hand-rolled codec too, and it is PINNED on its
  own, separately from the HOTP core.** It is the single canonical string
  form of the secret: the `otpauth://` URI carries it, the key-management
  service's protect operation stores the base32 string (since that
  interface takes and returns strings, not raw bytes), and TOTP computation
  base32-DECODES it back to the 20 raw bytes for the HMAC. Pin the codec
  against RFC 4648 section 10's own test vectors (the published `""` / `"f"`
  / `"fo"` / `"foo"` / .. -> base32 pairs), with the same rigor as the HOTP
  pinning - a wrong bit-packing or padding edge case must fail the build,
  not hide behind the one 20-byte (a clean multiple of 5, the size base32
  packs evenly) secret length that would mask it. A secret length that is
  NOT a clean multiple of 5 bytes is exactly the case a padding bug shows
  up on, so the vector suite must cover odd-length inputs even though the
  feature itself only ever encodes 20-byte secrets.
- **Skew window +/-1 step**: accept the code for the current step and the
  two adjacent steps (covers a client clock up to ~30s off). Wider windows
  weaken the factor; +/-1 is the common default.
- **Constant-time comparison.** Compare the computed code to the submitted
  code with a fixed-time comparison primitive over the digit bytes, never a
  plain string or byte-array equality check, so a timing side-channel
  cannot leak digit-by-digit correctness.
- **Replay guard.** A TOTP code is valid for its whole ~30-90s window (the
  skew window above), so a code observed once could be replayed within it.
  On a successful verify, record the accepted time-step in `last_step` and
  REJECT any code whose step is `<= last_step`, so each code (and each
  step) is single-use even inside its own validity window. Traced against
  the skew window: accepted steps are monotonically non-decreasing across
  genuine logins, so this never wrongly rejects the next legitimate step,
  only a true replay.
- **A decrypt failure is handled, not fatal.** Verifying needs the raw
  secret, so a lost or rotated-away key ring makes a TOTP code
  unverifiable. Catch this case as a distinct, named error (the same
  distinct-decrypt-failure handling webhooks.md section 4 gives a signing
  secret that cannot be decrypted) and return a controlled error, never an
  unhandled exception. The recovery-code path (SHA-256 hashed, key-ring
  independent, section 7) is the documented fallback for a user whose TOTP
  secret cannot be decrypted; it is the reason recovery codes exist at all,
  not merely a convenience for a lost phone.

## 4. Enrollment, and the load-bearing subtlety: step-up re-authentication

**Enabling MFA is a step-up operation, security-equivalent to changing a
password.** Both enroll and confirm require a FRESH credential proof (the
current password), not just an authenticated session - the same bar
disable (section 8) already sets for turning MFA off.

**Teach the attack this closes, because it is not obvious on first
reading.** An attacker who briefly holds a session - a stolen short-lived
access token, an XSS payload elsewhere in the product - makes two API
calls: enroll an ATTACKER-controlled secret, then confirm it. Confirming
returns the recovery codes. The attacker now holds a working authenticator
AND the recovery codes for an account they do not own, and MFA is
permanently enabled with credentials only the attacker has. The legitimate
owner's next login now hits the MFA challenge holding neither the
authenticator app nor a recovery code: they are locked out of their own
account, and the takeover is durable, surviving the very session hijack
that caused it long after that stolen token expires. This is worse than
the attacker simply reading data during the hijack window, because it
converts a temporary compromise into a permanent one.

**Requiring the current password closes it**, because an attacker who
holds only a stolen session token does not also hold the password - the
whole point of the token being the lighter-weight, shorter-lived credential
it is. Re-entering the password proves the caller is the account owner
right now, not merely someone whose earlier request happened to carry a
valid session. (A passwordless or SSO-only account, which has no password
to re-enter, must set a password or re-prove through a fresh sign-in with
its identity provider before enrolling - a documented step-up path,
section 11.)

- **Enroll** (authenticated + current password): generate a 20-byte secret,
  store it ENCRYPTED with `confirmed_at = null` (replacing any prior
  unconfirmed row), and return the `otpauth://` URI
  (`otpauth://totp/{issuer}:{email}?secret={base32}&issuer={issuer}`,
  percent-encoding the issuer and email label segments so an email or
  issuer with reserved URI characters cannot produce a malformed URI) and
  the base32 secret for manual entry - shown ONCE, so the client can render
  a QR code. This does NOT yet enable MFA.
- **Confirm** (authenticated + current password, body: a code from the
  authenticator): verify the code against the pending secret; on success
  set `confirmed_at`, GENERATE the recovery codes (section 7, shown ONCE in
  the response, stored hashed), and MFA is now enforced at login. A wrong
  code returns a validation error and does not confirm. Confirming proves
  the user's authenticator actually works before they are locked into
  needing it.
- **Re-enroll** (enroll again while already confirmed) begins a fresh
  pending secret; MFA stays on the OLD secret until a new confirm succeeds,
  so a half-finished re-enroll never locks the user out.

## 5. Login step-up: the challenge token

- After the password verifies (through the lockout and timing-safe checks
  role-templates-and-policy-defaults.md section 5 already builds), the
  login path checks for a CONFIRMED `mfa_credentials` row. If none, it
  issues the session exactly as today. If present, it returns an MFA
  challenge instead of the session.
- **The login result needs a third outcome, not a nullable hack.** A
  result type that today only distinguishes success from failure cannot
  also carry "succeeded, but a challenge is needed instead of a session."
  Model it as a discriminated outcome - tokens issued, OR a challenge
  issued - rather than bolting a second, sometimes-null field onto the
  existing success shape; the endpoint maps the tokens outcome to the
  normal token response and the challenge outcome to
  `{ mfaRequired: true, challenge, expiresIn }`.
- **The challenge token has a DISTINCT audience from an access token.** It
  is a signed, short-lived token (subject = user id, a ~5-minute expiry, no
  session-id claim) minted with an audience value reserved for this purpose
  alone (e.g. `mfa-challenge`), never the ordinary access-token audience.
  Because the app's normal bearer-token authentication only accepts the
  access-token audience, a `mfa-challenge`-audience token is rejected
  outright by every ordinary authenticated endpoint - it can NEVER be used
  as an access token, verified by the real audience-validation check the
  framework already runs. The mint and the validation are two explicit,
  separate paths, not a variant of the normal token issuer: a small
  dedicated challenge issuer mints it, and the verify endpoint validates it
  (audience, expiry, signature) INSIDE its own handler, not through the
  framework's default bearer-authentication pipeline - that default
  pipeline would reject the audience mismatch and return an authentication
  error before the handler ever ran, which is the wrong failure mode for a
  token that is supposed to be usable here and nowhere else. The challenge
  proves "the first factor passed"; alone, it is useless without a second
  code.
- **Verify** (body: the challenge token plus a code): validate the
  challenge, then accept EITHER a TOTP code (section 3, with its replay
  guard) OR a recovery code (section 7). On success, issue the real
  session, tenant-less like a normal login - the caller selects a tenant
  next, unchanged (multi-tenancy.md section 5).

## 6. The other load-bearing subtlety: brute-force throttling the verify endpoint

**A 6-digit TOTP code is only 10^6 possibilities, and a recovery code space
is finite too.** A challenge-token holder must NOT get unlimited guesses
against either one. Without this control, MFA barely improves on a stolen
password: a stolen password alone already gets an attacker to the verify
endpoint, and an unthrottled endpoint hands them all the time in the world
to grind through a six-digit space. The entire value of adding a second
factor rests on bounding that space, so this is not an optional hardening
pass, it is the property that makes the feature do what it claims to do.

- **Cap failed verifies PER USER**, reusing the exact same lockout
  mechanism role-templates-and-policy-defaults.md section 5 already builds
  for the password path (an atomic, conditional counter-increment-plus-lock
  statement, never a read-then-write): after N failed codes against a
  user's `mfa_credentials` row, the MFA step locks for a configured
  duration, expressed against `failed_attempts` and `locked_until` on that
  row (section 2).
- **A fresh challenge must NOT reset the count.** Because the lock lives on
  the user's credential row, not on any one challenge token, requesting a
  new login (and so a new challenge) does not give an attacker a clean
  slate - the count they have already burned stays burned. A design that
  instead tracked failed attempts per-challenge would let an attacker
  reset their guess budget for free by simply logging in again with the
  password they already have, defeating the whole point of the cap.
- **Reset the count on a successful verify**, mirroring the password path's
  own reset on a successful login.
- **The generic-answer and timing discipline from the password path applies
  here too**: a locked verify attempt returns the same shape of error a
  wrong-code attempt would, and pays the same computational cost, for the
  identical enumeration-safety and timing-side-channel reasons
  role-templates-and-policy-defaults.md section 5 argues for the password
  path.

## 7. Recovery codes

- Generated at confirm (section 4), and regenerable via a dedicated,
  authenticated-plus-fresh-TOTP-code endpoint that REPLACES all prior
  codes: 10 codes, each at least 16 base32 characters (~80 bits), shown
  ONCE, stored as SHA-256 hex.
- **The ~80-bit floor is deliberate, not arbitrary.** Unlike the other
  SHA-256-hashed secrets a system like this one typically has (API keys,
  one-time tokens - all high-entropy, effectively 256-bit, "no stretching
  needed"), a recovery code is human-typed, so it cannot be 256 bits long
  in practice; but a ~50-bit code (10 base32 characters) is
  OFFLINE-brute-forceable across its whole space on commodity hardware if
  the recovery-codes table ever leaks, whereas ~80 bits keeps a
  leaked-table attack infeasible. Format the code in groups for legibility
  (e.g. `xxxx-xxxx-xxxx-xxxx`, stripping separators on submit).
- A recovery code is accepted at verify (section 5) in place of a TOTP
  code. Consume it with a SINGLE ATOMIC conditional update:

  ```sql
  update mfa_recovery_codes
  set used_at = @now
  where user_id = @user_id
    and code_hash = @hash
    and used_at is null;
  -- accept only when rows-affected == 1
  ```

  A read-then-write instead of this single statement would let two
  concurrent submissions of the same code both pass the check before
  either write lands, minting two sessions from one one-time code.
- **Constant-time comparison is not required here**, unlike the raw TOTP
  digit comparison in section 3: this is an equality lookup against a
  high-entropy hash used as a lookup key, not a comparison whose
  digit-by-digit timing could leak information about a short, guessable
  value.
- Regenerating invalidates all outstanding codes (delete plus reissue), so
  a user who suspects a leaked list can rotate.

## 8. Disable

- Disable (authenticated + a fresh TOTP or recovery code): re-verifying the
  second factor proves it is really the enrolled user, not a hijacked
  session, turning MFA off - the same step-up bar section 4 sets for
  turning it on. On success, delete the `mfa_credentials` row and all
  recovery codes. Login reverts to one step.
- If the stored secret cannot be decrypted (section 3's decrypt-failure
  case), disable still accepts a valid recovery code: the recovery path is
  key-ring-independent by construction, so it is the route out for a user
  whose TOTP secret has become unverifiable, not only for a lost
  authenticator.
- A super-admin "reset a locked-out user's MFA" is a documented grow-into
  (section 11) - an operator recovery path, deliberately not built into
  the self-serve surface.

## 9. Events and audit

- `identity.mfa.enabled` (on confirm) and `identity.mfa.disabled` (on
  disable) are GLOBAL identity events, the same class as an
  `identity.password.changed` event: they carry no tenant, so they are NOT
  on the tenant-scoped audit catalogue and NOT in any tenant audit log.
  They join the audit catalogue's explicit not-audited set
  (audit-log.md section 10) alongside the other identity/session events,
  the same catalogue-completeness discipline that document already argues
  for.
- The identity module's existing domain-event consumer that emails a user
  about identity events (a changed password, a sign-in from an
  unrecognized device - the EMAIL channel in-app-notifications.md section 1
  already names) must be EXPLICITLY extended with these two event types and
  real copy ("MFA was enabled / disabled on your account", the security-
  notice pattern that consumer already uses for other identity events): a
  fixed, enumerated list of event types and render cases does not pick up a
  new type implicitly just because it was added to the catalogue.
- Recovery-code use and verify failures are NOT domain events - they sit on
  the high-volume login path, the same reason a quota rejection is
  deliberately not a domain event (quotas.md section 8). The `last_step`,
  `used_at`, and lock-state columns are the durable record instead.

## 10. Placement and deletability

**Placement diverges from most of this series' features on purpose.** The
audit log, webhooks, notifications, feature flags, and the
role-templates-and-policy-defaults catalogues are all cross-tenant,
platform/shared-layer pieces (their own placement sections each make this
argument for their own piece). MFA is not: it is per-user identity data,
sitting exactly where the password credential already sits, inside the
identity module. Nothing here is tenant-owned, so nothing here needs the
platform/shared layer's cross-cutting home; a design note that lists
"everything tenant-agnostic in the platform layer" should NOT gain an entry
for this feature, because MFA was never a platform-layer concern to begin
with.

**Deletability**: additive and removable. Drop the `mfa_credentials` and
`mfa_recovery_codes` tables and their migration, the TOTP and base32
helpers, the enroll / confirm / verify / disable / recovery-code
endpoints, and the MFA-challenge branch in the login path (login reverts
to the single-step flow it has today). No other module references MFA:
the key-management service and the lockout mechanism it reuses are shared
infrastructure, used by other features too, and are untouched by removing
this one.

## 11. Deferred (documented grow-into, not built)

- **WebAuthn / passkeys** (phishing-resistant hardware or platform
  authenticators) as a stronger second, or first, factor.
- **A tenant POLICY requiring MFA of its members**, enforced at tenant
  selection or a per-request gate for that tenant - the first place MFA
  would touch tenancy, hence deferred (the committed scope here is "no
  tenancy change"). This is the identical shape of gap
  role-templates-and-policy-defaults.md section 4 names for tenant-tightening
  password and lockout policy: coherent only once the enforcement point has
  a tenant context to evaluate the policy within, which global-user MFA
  enforcement does not have today.
- **A super-admin MFA reset** for a user who has lost both their
  authenticator and every recovery code (an audited operator recovery
  path). Deferred deliberately, and the risk it would otherwise carry is
  bounded by two controls this feature DOES ship: the step-up on
  enroll/confirm (section 4) means an attacker with only a session cannot
  turn MFA on against a victim (no attacker-driven lockout), and the
  recovery codes (section 7, shown at confirm) are the user's own
  self-recovery path. So the remaining exposure is narrowly "a user who
  both enabled MFA and lost their authenticator AND every recovery code" -
  a support-ticket case, not a takeover vector; an operator reset (delete
  the user's `mfa_credentials` row and recovery codes, audited) is the
  clean grow-into for it.
- **"Remember this device"**: a trusted-device token that skips the second
  factor for a bounded window on a known device.
- **SMS or email OTP** as an additional, weaker method, behind the same
  challenge flow.

## 12. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring this series' own framing
(audit-log.md section 10; in-app-notifications.md section 9):

- **Golden-vector correctness.** The RFC 6238 Appendix B vectors pass,
  including the 6-digit adaptation (the low six digits of the published
  8-digit values, not the first six) - the load-bearing algorithm gate; the
  RFC 4648 base32 vectors pass, including an odd-length input the 20-byte
  secret length would otherwise never exercise.
- **TOTP window and replay.** A code from the current step verifies; a
  code from two steps away fails (outside the +/-1 window); the replay
  guard rejects a code whose step is `<= last_step`.
- **Enrollment and step-up.** Enroll returns an `otpauth://` URI plus
  secret and does NOT enforce MFA; confirm with a valid code enables MFA
  and returns 10 recovery codes; confirm with a wrong code does not enable
  it; a pending re-enroll does not disturb an already-confirmed secret;
  enroll or confirm attempted without a fresh, correct password re-check
  is rejected even with a valid session.
- **Login step-up.** A confirmed-MFA user's password login returns a
  challenge outcome with no session tokens; verify with a valid TOTP code
  issues the session; verify with a recovery code issues the session and
  burns the code (a reuse of the same code then fails); the challenge
  token is rejected by normal access-token authentication (wrong
  audience); a non-MFA user still logs in in one step, unchanged.
- **Brute-force lock.** N wrong codes against verify lock the MFA step for
  that user (a subsequent CORRECT code then fails while locked); requesting
  a fresh challenge does not reset the count; a successful verify resets
  it.
- **Recovery-code burn under concurrency.** Two concurrent submissions of
  the same recovery code cannot both succeed; exactly one issues a
  session, and the atomic conditional update is what prevents the other.
- **Disable.** Disable requires a fresh, valid code; after disable, login
  is one step again and the recovery codes are gone; a decrypt failure on
  the stored secret still allows disable via a recovery code.
