# Testing strategy

Tests exist to make change safe. This doc sets the layer map, the rules for
when tests are written, and what "passing" is allowed to mean.

## The layer map

- **Unit tests** cover logic in isolation: a function or a small unit of
  behavior, with dependencies faked or stubbed out. These are the fastest
  and most numerous tests, and they should catch most logic bugs before
  anything else runs.
- **Property or invariant tests** cover critical paths: anything that moves
  value, or that must not corrupt data (see 04-architecture-principles.md).
  Instead of asserting one example, these assert that an invariant holds
  across a range of generated inputs, for example "the sum of all ledger
  entries never changes across a transfer."
- **Integration tests** cover the seams between modules, and between a
  module and a real datastore or external dependency (using a real or
  faithfully emulated instance, not a stub). These catch problems that
  unit tests, which fake the seam, cannot see.
- **End-to-end or golden tests** cover user-visible flows: a full path
  through the system as a user or client would experience it, checked
  against a known-good result. These are the fewest and slowest tests, and
  they exist to catch the failures that only show up when everything is
  wired together.

Each layer catches a different class of bug. Skipping a layer because a
lower layer is thorough does not work: unit tests cannot see integration
failures, and integration tests cannot see logic bugs efficiently.

## Tests ride in the same pull request as the code

A pull request that adds or changes behavior includes the tests that cover
that behavior. Tests are not a follow-up. A reviewer should be able to see
the behavior and its test coverage in one diff.

## Coverage floors

Each project sets its own coverage floor (a percentage, or a stricter
per-module target for critical paths) and enforces it in CI. The floor is a
minimum, not a target to write toward: writing a test to satisfy a coverage
number without asserting anything meaningful defeats the purpose.

## A suite that cannot run is a failure, not a silent pass

If a test suite fails to run at all (a broken test harness, a missing
dependency, a timeout), that is a bug and gets bug-priority attention, the
same as a failing test. It is never treated as an acceptable skip or a
green check by default. Silence about a broken suite is worse than a
visible failure, because it hides the fact that nothing was actually
verified.

## Determinism

Tests do not depend on wall-clock time or network access unless that
dependency is deliberately isolated (a fake clock, a recorded network
fixture, a test-only sandbox environment). A test that is flaky because it
races the clock or a live network call is not trustworthy, and an
untrustworthy test is worse than no test: it teaches people to ignore
failures.

## Test data

Test data is synthetic. No real personal data, real customer data, or real
production data of any kind is used as a test fixture, even scrubbed or
partial. Generate representative fake data instead.
