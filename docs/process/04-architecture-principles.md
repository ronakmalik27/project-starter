# Architecture principles

These principles apply at whatever granularity the project uses: services,
modules, packages, or layers within a single application. They are
deliberately stack-agnostic.

## Clear module boundaries, one dependency direction

Every module has a defined responsibility and a defined boundary. Dependencies
between modules flow in one direction: a lower-level module never reaches
back up into a module that depends on it. If two modules need to depend on
each other, that is a sign they should be one module, or that a third,
shared module should own the common piece.

## Explicit contracts between modules

Modules talk to each other through explicit interfaces: a function
signature, an API contract, a message schema. They do not communicate
through shared mutable state (a shared global, a shared database row
mutated by both sides without a defined protocol). An explicit contract can
be tested, versioned, and documented; shared mutable state cannot.

## Deferred features still get design hooks now

A feature that is out of scope for now but plausible later should not be
designed as if it will never exist. Concretely: capture the domain events
that a future feature would need, and leave the extension points (a plugin
interface, an event stream, a schema field reserved for future use) in place
from day one. The goal is that adding the deferred feature later is an
addition, not a rewrite. This costs little up front and is expensive to
retrofit.

## No premature abstraction

Do not build a generic, configurable abstraction for a case that has
appeared once. Prefer duplication until a pattern has shown up at least
three times (the rule of three), then extract the abstraction from the real
examples you have, not from a guess about what the abstraction should look
like. An abstraction built too early tends to fit the imagined cases and
fight the real ones.

## Observability from day one

A system reports on its own health from the first version that runs
anywhere other than a laptop:

- **Structured logs** (not free-text strings) so they can be queried and
  correlated.
- **Metrics** for the handful of numbers that tell you whether the system
  is healthy (request rate, error rate, latency, queue depth, whatever is
  relevant to the system).
- **Health checks** that a deployment platform or a human can poll to know
  whether the system is up and functioning, not just whether the process is
  running.

Retrofitting observability after an incident is much more expensive than
building it in from the start.

## Security considered at design time

Security is a design input, not a review-time patch. At design time, name
the trust boundaries (what data crosses from an untrusted source, who is
authenticated to do what), the sensitive data the system holds, and the
failure modes an attacker would try first. A design doc that has not
considered these is not finished.

## Data integrity invariants stated explicitly

Any path that moves value (money, credits, inventory, anything where being
wrong is costly) or that must not corrupt data states its invariants
explicitly in the design: what must always be true, and what mechanism
enforces it (append-only history instead of mutation, an idempotency key, a
reconciliation check, a typed unit instead of a raw floating-point number).
An invariant that exists only in a developer's head is not an invariant; it
is an assumption waiting to be violated.
