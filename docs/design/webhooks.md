# Outbound webhooks: a worked example

Status: WORKED EXAMPLE and reference blueprint, not a requirement. It shows
how a tenant-registered outbound webhook grows out of the multi-tenancy
control plane in [docs/design/multi-tenancy.md](multi-tenancy.md) (the
grow-into bullet in that doc's section 18, "Outbound webhooks"): adapt the
specifics to your stack, or skip it if your product has no third-party
integration surface. Docs-first applies here too (see
[docs/adr/0001-docs-first-development.md](../adr/0001-docs-first-development.md)):
refine this against your product before building any of it. It is the third
worked example grown out of that surface, after
[audit-log.md](audit-log.md) and [service-accounts.md](service-accounts.md),
and builds directly on both: multi-tenancy.md's event/outbox spine and the
bypass path (sections 2 and 4), audit-log.md's "projection off the event
stream, not a new write path" placement (section 1) and its
catalogue-completeness discipline (section 10), and service-accounts.md's
shown-once-secret and display-prefix idioms (sections 2 and 7) - though a
webhook secret has to be recoverable rather than hashed, which changes its
storage story entirely (section 5 explains why). Read those first. Being a
generic reference, it carries no build-sequence section (a concrete
product's own design doc would): treat every part as a menu, adopt the
pieces your product needs.

## 1. The decision, up front

- **Delivery is two stages: a fan-out consumer writes one delivery row per
  subscribed endpoint, and a separate worker sends each row.** The fan-out
  consumer is an ordinary domain-event consumer (multi-tenancy.md section
  4): for every domain event, it inserts one delivery row per tenant
  endpoint subscribed to that event type, transactionally and idempotently
  (section 3). The worker is a separate, leader-elected process (section 4)
  that claims pending rows and makes the HTTP call, with its own per-row
  retry and dead-letter. This is the industry-standard shape: Stripe,
  GitHub, and Svix (a webhooks-as-a-service platform built on exactly this
  split) all separate "decide who gets this event" from "send it and handle
  the response" into two stages.
- **Why two stages, and not "send to every endpoint inside the consumer
  that reacts to the event."** If a single consumer call posted to every
  subscribed endpoint directly, one endpoint being slow or down would fail
  the whole consumer call, which means the source event gets redelivered
  and every endpoint that already succeeded gets posted to again - a
  healthy receiver punished for a sibling's outage. Splitting the work so
  each (event, endpoint) pair is its own row with its own attempt count and
  next-attempt time means each endpoint retries and dead-letters
  independently: a failing endpoint's retries never touch a healthy
  endpoint's already-successful delivery.
- **Webhooks live next to the event-stream and outbox mechanism they
  project from** (section 11), the same placement audit-log.md section 9
  argues for itself: a cross-cutting consumer that reads every module's
  events through one generic envelope, plus a worker that needs the same
  cross-tenant privilege the platform/shared layer already owns for a
  small, named set of consumers (multi-tenancy.md sections 2, 4, and 16).
- **The signing secret is recoverable, encrypted at rest, and shown once -
  not hashed like an API key.** A webhook secret has to sign every future
  delivery, so the server needs the plaintext back, which a one-way hash
  can never give it. It is stored as ciphertext under a server-managed
  encryption key (a key ring or a KMS, section 5), decrypted only at
  signing time, and returned in full exactly once, at register and at
  rotate (mirroring service-accounts.md's own shown-once discipline for a
  very differently stored credential).
- **Signing follows the Stripe scheme**: an HMAC over the timestamp and
  body, a `t=...,v1=...` style header, a constant-time comparison on the
  receiving end, and a rejected stale timestamp as the replay defense
  (section 5). A stable delivery-id envelope lets a receiver dedupe, since
  delivery is at-least-once end to end.
- **SSRF is a first-class threat, not an afterthought**, because the
  delivery URL is exactly what a tenant registers and exactly what the
  server then connects to on that tenant's behalf. The guard has to be
  authoritative at connect time, not just at registration, to survive DNS
  rebinding (section 6) - this is net-new work on every stack; no
  mainstream HTTP client validates any of this for you by default.

## 2. Data model

Two tables, both tenant-owned and under the same authoritative boundary as
every other tenant table (multi-tenancy.md section 2).

`webhook_endpoints` (one row per tenant-registered receiver):

- **id**: primary key.
- **tenant id**: not null, the isolation discriminator.
- **url**: the receiver URL. HTTPS only, validated at register and at every
  update (section 6).
- **description**: an admin-facing label.
- **event types**: the subscribed event-type list; empty means "every
  deliverable event type."
- **signing secret, encrypted**: ciphertext produced by the key ring
  (section 5), never the raw secret.
- **secret display prefix**: the first few characters of the raw secret, in
  clear, for display only - the same idiom service-accounts.md section 2
  uses for its own key prefix.
- **disabled at**: nullable; a disabled endpoint receives no new
  deliveries.
- **created by**, **created at** / **updated at**: as usual.

`webhook_deliveries` (one row per (event, endpoint) delivery attempt):

- **id**: primary key.
- **tenant id**: not null, the isolation discriminator.
- **endpoint id**: the target endpoint.
- **event id**: the source domain event's own id.
- **event type**: denormalized, for display and filtering.
- **payload**: the webhook body (the envelope, section 5), stored so a
  replay needs no event re-read.
- **status**: `pending` / `delivered` / `dead`.
- **attempts**: delivery attempts so far.
- **next attempt at**: when the worker may next claim this row.
- **delivered at**: nullable, set on a 2xx response.
- **dead lettered at**: nullable, set once attempts exhaust the retry
  budget.
- **last response status** / **last error**: the most recent outcome,
  bounded and non-PII.
- **created at**.

A unique constraint on (endpoint id, event id) is the fan-out idempotency
key (section 3). An index on (next attempt at), restricted to pending rows,
serves the worker's claim query (section 4).

## 3. The fan-out consumer

One consumer, subscribed to the deliverable event catalogue - the
tenant-scoped events your product decides are worth forwarding externally,
the same kind of catalogue the audit projection subscribes to
(audit-log.md section 2). It only writes rows; the HTTP call happens in the
separate worker (section 4), so it stays cheap to run inline with every
other consumer subscribed to the same event.

Per delivery, the dispatcher has already bound the consumer to the event's
own tenant (multi-tenancy.md section 4), so the consumer runs under that
tenant's context automatically:

1. Read that tenant's endpoints that are not disabled and whose subscribed
   event types are empty (meaning all) or include this event's type.
2. For each matching endpoint, insert a delivery row (status pending,
   attempts zero, next-attempt-at now, payload built from the event
   envelope). The insert is idempotent: the unique (endpoint id, event id)
   constraint turns a redelivered event into a no-op insert rather than a
   duplicate row - the same unique-violation-is-success pattern the audit
   projection uses for its own primary key (audit-log.md section 5).
   At-least-once redelivery of the source event therefore never
   double-enqueues a delivery.

The consumer reads the event payload as untyped structured data rather
than a typed deserialization, exactly as the audit projection does when it
cannot depend on every module's own payload types (audit-log.md section
5): a cross-cutting consumer that lives outside every business module has
no business-module types to deserialize into.

**Coupling with any other consumer of the same event.** Most outbox or
dispatcher implementations invoke every consumer registered for a given
event under one shared delivery attempt, so a retry of that delivery
re-invokes every subscribed consumer, not just the one that failed. That is
only safe because each consumer's own write is independently idempotent:
this consumer's unique (endpoint id, event id) constraint and the audit
projection's event-id-as-primary-key (audit-log.md section 5) each make
their own re-invocation a no-op rather than a duplicate. If either consumer
were not independently idempotent, sharing a delivery attempt with a
sibling would silently double that consumer's side effects on every retry
caused by the sibling's own failure - a coupling that stays invisible until
some other consumer on the same event starts failing, so both consumers
have to be checked for it, not just whichever one is being changed.

**The event catalogue's "ids and scalars, never PII or secrets" rule
becomes an external boundary here.** The audit log inherits that rule
internally (audit-log.md section 3): its projected `data` field is the
event payload verbatim, kept inside the product's own trust boundary. A
webhook delivery carries that same verbatim payload past the trust boundary
entirely, to a URL a tenant chose. Whatever discipline keeps PII and
secrets off the event stream today (verified at design time: no event
payload carries a raw key, token, or personal field beyond ids and scalars)
stops being merely internal hygiene the moment this feature ships: a leak
into an event payload now leaks externally, to every endpoint subscribed to
that event type, the instant it is emitted. A content-level guard that
asserts the rule for every future event type (a schema check, a lint rule,
or a reflection test over the payload shape) is a documented hardening
worth tracking with the same discipline audit-log.md section 10 applies to
catalogue completeness.

## 4. The delivery worker

A separate, long-running process (a background service, a dedicated worker
process, or a scheduled job on a short interval - whatever your stack's
long-running-task primitive is) that claims pending delivery rows and makes
the HTTP call. This repo does not otherwise document an outbox dispatcher's
own delivery-worker mechanics, so this section specifies them from first
principles, using the same building blocks most production queue and
outbox workers already reach for:

- **Leader election.** A distributed lock (a database advisory lock, a
  lease row in a coordination table, or a coordination service such as
  etcd, ZooKeeper, or Consul) with its own lock key, distinct from any other
  worker's, so exactly one instance is delivering at a time; every other
  instance idles and retries the lock periodically. Without this, two
  instances racing the same pending rows is the ordinary double-processing
  hazard any multi-instance worker has to solve, whatever the mechanism
  underneath.
- **Claim, with a lease.** The claim query runs on the bypass path
  (multi-tenancy.md section 2): the deliveries table is tenant-isolated, so
  a request-scoped connection with no tenant set would see nothing, and the
  worker must legitimately cross every tenant to drain the queue - exactly
  the small, named set of platform consumers multi-tenancy.md section 4
  marks as the exception. It selects pending rows whose next-attempt-at has
  passed, locks them so a concurrently running claim cannot take the same
  row twice (`SELECT ... FOR UPDATE SKIP LOCKED` is the reference case on
  Postgres and MySQL; a conditional claim update, a visibility-timeout
  queue receive, or a partition claim are the equivalent move on other
  stores), and in the same operation arms a lease: bump attempts and push
  next-attempt-at forward by a lease window. A crashed leader's in-flight
  rows become reclaimable only once that lease expires, never mid-flight.
- **Re-arm per row, immediately before sending - the real double-send
  anchor.** A lease taken at claim time is not, by itself, enough: a batch
  of slow-but-still-alive sends can outlive a single per-tick liveness
  check, so a failed-over leader could in principle have already reclaimed
  a row the original leader is still about to send to. Immediately before
  each row's send, the worker re-arms that row's lease again, and it must
  do so in a way that proves the SAME lock is still held right now, not
  merely that a lock existed at claim time. This is the fencing-token idea
  distributed-systems practice already prescribes for exactly this failure
  mode (Kleppmann's argument against trusting a lease without a fencing
  check applies here verbatim): if the re-arm cannot prove the lock is
  still held, the send does not happen. On a database advisory lock this is
  naturally a re-arm statement run on the very session that holds the lock;
  other lock mechanisms have their own equivalent (a fencing token compared
  before every write, a lease epoch checked at send time). Whatever the
  mechanism, this step is mandatory, not an optimization to skip under
  load.
- **Deliver, with a send-time re-check.** Load the endpoint (bypass path,
  as above); if it was deleted or disabled since fan-out time, drop the
  delivery (mark it dead with a reason, do not send) rather than trusting
  the filter the fan-out consumer already applied at enqueue time, which
  can be stale by the time the worker reaches the row. Otherwise decrypt
  the signing secret (section 5), build the signature, and send the stored
  payload through the SSRF-guarded client (section 6) under a send timeout.
- **Outcome.** A 2xx response marks the row delivered. Any other status, a
  transport failure, or a timeout leaves the row pending with
  next-attempt-at pushed out by exponential backoff plus jitter
  (`min(base^attempts, cap) + jitter` is the standard shape), and records
  the response status and a bounded, non-PII error note. Once attempts
  reach the configured maximum, the row is dead-lettered and parked for
  replay (section 7) - the exact analogue of a poisoned event on the outbox
  itself.
- **A decrypt failure is handled distinctly, never retried like an
  ordinary send failure.** If the signing secret cannot be decrypted (a
  lost or rotated-away key ring, section 5), that is not a transient
  delivery problem the endpoint might recover from - retrying it burns the
  whole retry budget on something that can never succeed and buries a real
  operational failure inside ordinary-looking backoff. The worker catches
  this case specifically and dead-letters the row immediately with a clear
  reason, so an operator sees a key-ring failure as what it is, not as a
  string of failed sends against an apparently-healthy endpoint.

All the tunables here (lock key, batch size, maximum attempts, backoff cap,
jitter, send timeout) belong in one validated options block, checked at
startup, not scattered as inline constants.

## 5. Signing and the payload envelope

- **The body is a stable envelope**, not the raw event: `{ id (the
  delivery's own id), type (the event type), occurredAt, data (the event
  payload) }`. `id` is what lets a receiver dedupe, since delivery is
  at-least-once end to end (retries, and a redelivered source event, can
  both produce a repeat send of logically the same delivery).
- **The signature is an HMAC-SHA256 over `"{timestamp}.{body}"`**, sent as
  a header carrying both parts, for example `X-Webhook-Signature:
  t=<unix timestamp>,v1=<hex digest>` (the scheme Stripe popularized and
  several webhook platforms since have converged on). The receiver
  recomputes the same HMAC over the timestamp and the raw body, compares it
  to the received digest using a constant-time comparison (an ordinary
  equality check on a MAC leaks timing information a constant-time compare
  does not), and rejects a request whose timestamp is too old - the replay
  defense. Because the timestamp is part of what gets signed, not just sent
  alongside the signature, an attacker who captures a valid request cannot
  change the timestamp to make a stale, captured request look fresh:
  changing it invalidates the signature.
- **The secret is minted like any other high-entropy bearer secret** (the
  same idiom service-accounts.md section 2 uses for its API key: a large
  random value, base64url-encoded, with a recognizable prefix such as
  `whsec_` so secret-scanning tools catch a leak), and returned in full
  exactly once, at register and at rotate, mirroring service-accounts.md
  section 7's "shown once" lifecycle discipline. After that moment, only
  its ciphertext and a display prefix persist. Rotate replaces the
  ciphertext and returns a new raw secret; the old secret stops signing
  immediately, and a grace window where two secrets verify at once is a
  documented extension, not a day-one requirement.
- **Unlike an API key, this secret cannot be stored as a one-way hash.**
  Service-accounts.md's key is only ever compared (section 2: hash the
  incoming key, look up the hash), so a one-way hash is not just
  sufficient but the more secure choice, since the server never needs the
  raw value back. A webhook secret is the opposite: the server has to
  actively compute a fresh HMAC with it on every single delivery, forever,
  so it must get the plaintext back, not merely confirm a match against
  it. That requirement is what forces encryption instead of hashing: the
  secret is stored as ciphertext produced by a server-managed encryption
  key (envelope encryption through a cloud KMS - AWS KMS, GCP Cloud KMS,
  Azure Key Vault - or a framework-native key ring such as ASP.NET Data
  Protection or a Rails encrypted-attribute key), decrypted only at the
  moment of signing, never held decrypted anywhere else.
- **The key ring is a single point of failure, and that is an operational
  obligation, not an oversight.** Whatever holds the encryption keys (a
  dedicated keys table, or the KMS's own managed store) must be persisted
  centrally, so every replica and every restart decrypts with the same
  keys, and it must be backed up with the same rigor as the database
  itself, never left on ephemeral or instance-local storage. Because every
  secret is shown once and stored only as ciphertext, losing or corrupting
  that key material makes EVERY tenant's secret unrecoverable at once, not
  just one - a disaster-recovery requirement worth naming explicitly rather
  than discovering it during an actual loss. The worker's distinct handling
  of a decrypt failure (section 4) is the other half of this: an operator
  needs a clear signal that the key ring itself has a problem, not a wall
  of ordinary-looking failed deliveries.
- **Keep the destination URL out of your tracing and logging pipeline.**
  Default HTTP-client instrumentation commonly records the request URL,
  and a tenant's receiver URL can itself embed a secret (a Slack, Discord,
  or Teams incoming-webhook URL carries its own token in the path) -
  something this feature cannot prevent at registration, since the URL is
  exactly what the tenant is registering. Redact or suppress the
  destination URL on this client's own spans and log lines specifically,
  so a receiver-owned secret is never shipped to your observability
  backend. The signing secret and the signature header are already safe as
  long as your instrumentation does not capture headers or bodies by
  default, which is the common default.

## 6. The SSRF guard

The delivery URL is tenant-controlled, and the server makes an outbound
request to it on the tenant's behalf: that is the textbook server-side
request forgery shape, so the guard is load-bearing, not cosmetic. This is
net-new on every stack: nothing about ordinary outbound HTTP handles it for
you. Three layers:

- **At register and update time.** The URL must be absolute and `https`; a
  plaintext `http` URL, a non-absolute value, or any other scheme is
  rejected outright. As a fast-fail nicety, resolve the host and
  range-check it here too, so an obviously internal literal target is
  caught immediately - but this check alone is not sufficient.
  Registration-time validation is a snapshot: a hostname can resolve to a
  public address today and a private one at delivery time (DNS rebinding),
  so connect-time is the authoritative check, not this one.
- **At connect time, the authoritative check.** Intercept the connection
  before the TCP handshake, using whatever low-level connect hook your HTTP
  client exposes for this (a custom `Dialer` in Go's `net/http` transport, a
  lookup override on Node's `http`/`https` agent, a custom socket factory in
  Java, a connect hook on Ruby's `Net::HTTP` or Faraday,
  `SocketsHttpHandler.ConnectCallback` in .NET). Whatever it is called, that
  hook is handed an unresolved host and port, and it must: **resolve DNS
  exactly once, validate every returned address against the blocklist
  below, then open the socket directly to the validated address - never
  hand the hostname back to a second resolver for the actual connect.** Two
  separate resolutions (one to validate, a second to connect) is precisely
  the TOCTOU window DNS rebinding exploits; resolving once and connecting to
  the address you already vetted closes it. Redirects are not followed - a
  3xx response is treated as a failed delivery attempt - so a redirect
  cannot bounce the request to a blocked host after the check has already
  passed.
- **The address classifier**, checked against the full IANA IPv4 and IPv6
  special-purpose address registries, not an ad hoc subset. Before
  range-checking, unwrap the addresses that hide a blocked address behind
  another family or encoding: an IPv4-mapped IPv6 address (`::ffff:0:0/96`)
  is unwrapped to its embedded IPv4 address, and NAT64 (`64:ff9b::/96`),
  6to4 (`2002::/16`), and Teredo (`2001::/32`) each have their own embedded
  IPv4 address extracted and checked the same way - otherwise an AAAA
  answer sails straight past a check that only looks at IPv4 ranges.
  Blocked IPv4 ranges: `0.0.0.0/8`, `10.0.0.0/8`, `100.64.0.0/10`
  (carrier-grade NAT), `127.0.0.0/8`, `169.254.0.0/16` (link-local,
  including the `169.254.169.254` cloud metadata endpoint), `172.16.0.0/12`,
  `192.0.0.0/24`, `192.0.2.0/24`, `192.168.0.0/16`, `198.18.0.0/15`,
  `198.51.100.0/24`, `203.0.113.0/24`, `224.0.0.0/4` (multicast),
  `240.0.0.0/4` (reserved, including the broadcast address
  `255.255.255.255`). Blocked IPv6 ranges: `::/128` (unspecified),
  `::1/128` (loopback), `fc00::/7` (unique-local), `fe80::/10`
  (link-local), `ff00::/8` (multicast). A bare "is this loopback" check is
  not enough on its own (it typically misses `0.0.0.0`, which a client
  connect can land on despite not looking like loopback), so the classifier
  checks explicit ranges rather than relying on a single built-in
  predicate.
- This is genuinely new code on every stack (an ordinary HTTP client
  validates none of this by default): the classifier and the connect hook
  deserve their own unit tests, one per blocked range, the address-unwrap
  cases, and a public address passing cleanly. A configurable allowlist of
  additional blocked or explicitly-permitted ranges (to allow one trusted
  internal host in a specific deployment, say) is a documented extension,
  not a day-one requirement.

## 7. Admin API

Exposed alongside the rest of the tenant-admin control-plane API
(multi-tenancy.md section 16), gated by one new permission atom,
`webhooks:manage`, added to the closed permission catalogue and the
default admin role's permission set (multi-tenancy.md section 8). The
actions mirror service-accounts.md section 7's lifecycle shape:

- **Register**: accepts a URL, a description, and the subscribed event
  types; returns the signing secret in full, exactly once.
- **List**: returns every endpoint's id, description, URL, subscribed
  types, and disabled state. Never the secret, and never its ciphertext -
  only the display prefix (section 2), the same discipline
  service-accounts.md section 7 applies to its own key list.
- **Update**: URL, description, subscribed event types, and disabled
  state. A URL change re-runs the full SSRF check (section 6): a validated
  URL is not validated forever.
- **Rotate secret**: mints a new secret, replaces the stored ciphertext and
  display prefix, and returns the new raw secret once. The old secret stops
  signing immediately.
- **Delete**: removes the endpoint and its pending deliveries together, in
  one transaction - whether that is expressed as a database cascade or an
  explicit application-level statement covering both tables is a stack
  choice, but it must be atomic, not a delete-then-clean-up-later that can
  leave orphaned pending rows if the second step never runs. The worker's
  own send-time re-check (section 4) is what covers the narrower case of a
  delivery already claimed by the worker in the instant before the delete
  lands.
- **List deliveries**: the delivery log for one endpoint - status,
  attempts, last response, timestamps - keyset-paginated like every other
  list read in the product.
- **Replay**: resets a delivered, failed, or dead delivery back to pending
  with attempts reset to zero, so the worker picks it up and sends it
  again.

**`webhooks:manage` is deliberately not a self-escalation primitive**,
unlike the two permissions service-accounts.md section 4 refuses to a
service account (`roles:manage`, which lets a principal author and assign
itself a broader role, and `api-keys:manage`, which lets a principal mint
itself further keys). Holding `webhooks:manage` lets a principal register
an external endpoint and see events flow to it - real operational power,
but not a path to broader permissions or new credentials for itself. That
means, unlike those two, it is safe to grant to a service account: a
service account that forwards a tenant's own events to an external system
(a data pipeline, a sync job) is an ordinary, supportable use case, not a
privilege-escalation hole. The genuine risk it carries - a webhook is a
sanctioned, tenant-configured way to send a tenant's own event data to an
external URL - is the same trust already placed in any admin-level
permission, bounded by the SSRF guard (no internal destinations) and by the
fact that every endpoint change is itself an audited action (section 9).

## 8. Bounds and fairness

The delivery worker is, in its simplest form, a single leader-elected
instance draining one global queue ordered by next-attempt-at. A few
bounds keep one tenant from crowding out the rest:

- **A cap on endpoints per tenant**, configurable, rejected at register
  with a clear validation error once hit. This bounds how many delivery
  rows a single event from one tenant can fan out into.
- **Global, serial delivery is the documented MVP limit, not the end
  state.** Sending strictly one row at a time behind a single lock means a
  merely-slow endpoint delays every row behind it in the queue, including
  other tenants' deliveries. The documented scale-up is a bounded degree of
  parallel sends plus a per-tenant round-robin claim (claim a few rows from
  each tenant with pending work in turn, rather than draining one tenant's
  backlog before touching the next), layered onto the same claim-and-lease
  model in section 4 without a schema change. A per-endpoint send-rate cap
  - so a burst of one tenant's own events cannot hammer an external target
  faster than it can handle - rides the same options block and is the next
  bound worth adding once volume justifies it.
- **A send timeout** bounds how long one endpoint can occupy the worker: a
  stuck connection fails the attempt and backs off rather than holding the
  worker open, so a genuinely down endpoint degrades to its own backoff
  schedule instead of stalling everyone else's deliveries.

## 9. Events and audit

Endpoint lifecycle emits its own tenant-scoped domain events (register,
update, delete, rotate-secret), and every one of them must be picked up by
the audit projection (audit-log.md section 2's tenant-scoped catalogue) or
explicitly named as a deliberate exception, exactly the discipline
service-accounts.md section 7 holds its own lifecycle events to, enforced
by audit-log.md section 10's catalogue-completeness check. These are
exactly the "who did what, to what, and when" actions a tenant audit log
exists for, so the expectation is that all four are audited, not exempted.

**Deliveries themselves are not domain events.** A delivery is the
projection of an event that already happened, not a new fact about the
system - recording every delivery attempt as its own domain event would
duplicate the source event under a new name for no benefit. Its record is
the delivery row itself (section 2), queryable through the admin API's
delivery list and replay actions (section 7).

## 10. Retention

Delivered rows are purged after a retention window by an operator-run
maintenance pass on the bypass path, mirroring how audit-log.md section 8
treats its own retention as an operator job rather than an
application-level mutation. Dead-lettered rows are kept past that window,
for inspection and replay, the same way a poisoned event stays parked
rather than being cleaned up automatically. Endpoints themselves persist
until explicitly deleted; there is no separate endpoint-retention policy.

## 11. Placement and deletability

Webhooks live next to the event-stream and outbox mechanism they project
from, in the platform/shared layer, not inside a business module - the
identical placement argument audit-log.md section 9 makes for itself, for
the identical two reasons. First, the fan-out consumer consumes every
module's events through the same generic envelope the audit projection
reads, so it depends on no specific module and gains nothing by living
inside one. Second, the delivery worker's claim query needs to cross every
tenant to drain the whole queue, which means it needs the same cross-tenant
bypass privilege the platform/shared layer already owns and exposes to a
small, named set of platform consumers (multi-tenancy.md sections 2, 4, and
16). Placing this feature inside a business module instead would force
that module to invent its own version of a privilege that already exists
in exactly one place for exactly this reason - the same duplication
audit-log.md section 9 warns against.

The cost of this placement is the same one audit-log.md section 9 names
for itself: the two webhook tables are very likely among the only
tenant-owned, isolation-bound tables living inside an otherwise
tenant-agnostic platform/shared layer, alongside the audit log and the
service-account table if your product built those first. That is a
deliberate, repeated exception, not drift - each of the three worked
examples in this repo needs the same authoritative tenant boundary as
every other tenant table, full stop, and a platform-layer design note
claiming "nothing here is tenant-owned" needs updating to name all three,
not just the first one that showed up.

**Deletability**: drop the two tables, the fan-out consumer and worker
registrations, the SSRF-guarded HTTP client, the admin endpoints, and the
`webhooks:manage` permission atom, and the event stream underneath is
completely untouched - nothing about what modules emit, or how they emit
it, changes when this feature is removed.

## 12. Tests: what the suite must prove

Behaviors worth proving, whatever your stack's testing story looks like,
blocking rather than nice-to-have, mirroring audit-log.md section 10's own
framing:

- **Fan-out is real and idempotent.** An event with two subscribed
  endpoints produces exactly two delivery rows; forcing a redelivery of
  that same event produces no additional rows (the unique (endpoint id,
  event id) constraint). An endpoint not subscribed to the event type gets
  no row; a disabled endpoint gets no row.
- **Tenant isolation.** A tenant sees only its own endpoints and
  deliveries; fanning out an event for tenant A never creates a row
  against tenant B's endpoint, the same assertion every other tenant table
  already carries (multi-tenancy.md section 15).
- **Delivery succeeds and is signed.** A stub receiver gets a request whose
  signature header verifies against the (rotated-in) secret and whose
  timestamp is fresh; the delivery row moves to delivered.
- **Retry and dead-letter, without punishing a healthy sibling.** A
  receiver returning an error status causes attempts to climb with backoff
  and the row to dead-letter once the maximum is reached; a healthy
  sibling endpoint subscribed to the same event still delivers exactly
  once - one endpoint's failure never re-sends to an endpoint that already
  succeeded.
- **Replay.** Replaying a dead delivery re-sends it, and it can then
  succeed.
- **The secret is shown once and stored encrypted, not hashed.** Register
  and rotate return the raw secret; list never does; the stored value is
  ciphertext, not the raw secret, and it decrypts back to the same value
  that was originally returned.
- **The SSRF guard, including rebinding.** Registering an `http://` or a
  non-absolute URL is rejected. A delivery to a URL that resolves to a
  loopback, private, link-local, or metadata address never connects. A URL
  that resolves to a public address at registration and a private one at
  delivery (the rebinding case) is still blocked at connect time, proving
  the guard is authoritative at connect time and not just a
  registration-time check.
- **Audited.** Register, update, delete, and rotate-secret each land an
  audit row, and the catalogue-completeness check (audit-log.md section
  10) stays green with the new event types accounted for.
