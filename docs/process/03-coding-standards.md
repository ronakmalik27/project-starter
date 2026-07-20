# Coding standards

These standards are language-agnostic. They describe the shape good code
takes in any stack. A project adopting this template should add a
language-specific section (formatting tool, linter config, idiom guide) that
applies these standards to its actual language and framework.

## Naming and readability

Names describe what a thing is or does, not how it is implemented. A
variable, function, or type name should let a reader guess its purpose
without opening its definition. Prefer a slightly longer, clear name over a
short, ambiguous one. Consistency beats personal preference: follow the
naming convention already used in the surrounding code.

## Small, focused functions

A function does one thing. If describing what a function does requires the
word "and" more than once, it is probably two functions. Small functions are
easier to test, easier to name well, and easier to review in isolation.

## Explicit error handling

Errors are handled deliberately, never swallowed. Concretely:

- Use whatever the language's idiomatic mechanism is for signaling failure
  (a typed error or `Result`-like return value, or a deliberately thrown
  exception), and pick one convention per codebase rather than mixing them
  without reason.
- A caught error is either handled (retried, translated, recovered from) or
  re-raised with enough context to diagnose it later. A bare catch-and-log,
  or a catch that discards the error, is a defect, not a safety net.
- Failure paths get the same review scrutiny as success paths.

## Secrets

No secret (API key, token, password, credentialed connection string,
private key) is ever written into code, configuration files, commit
history, pull request bodies, comments, or logs. Secrets live in a local
secret store during development and a managed vault or secret manager in
production. If a secret ever ends up in a place it should not be (including
pasted into a chat or a code review comment), treat it as compromised and
rotate it. A secret-scanning check in CI is the backstop, not the primary
control.

## Dependency hygiene

- Pin dependency versions so a build is reproducible.
- Review a new dependency before adding it: what it does, how actively it
  is maintained, and what it pulls in transitively.
- Prefer the smaller dependency footprint when two options solve the
  problem equally well. Every dependency is something the project now has
  to trust and keep patched.

## Formatting and linting

Formatting and linting are enforced by tooling, applied automatically, not
argued about by hand in review. Configure a formatter and linter for the
project's language, run them in a pre-commit or pre-push hook and in CI, and
treat a formatting diff in a pull request as something the tool should have
already fixed, not something a reviewer should flag by hand.

## Match the surrounding code

New code matches the comment density, naming idiom, and structure of the
code around it. A pull request that introduces a completely different style
into an existing module makes the module harder to read as a whole, even if
the new style is arguably better in isolation. Raise a style change as its
own proposal, not as a side effect of an unrelated change.

## Document public contracts

Anything another module, another team, or an external consumer depends on
(a public function signature, an API endpoint, a configuration option) is
documented at the point of definition: what it does, its inputs and
outputs, and any invariant it upholds or assumes. Undocumented internals are
fine; undocumented contracts are not.
