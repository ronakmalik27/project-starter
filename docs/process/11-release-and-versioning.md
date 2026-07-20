# 11 - Release and versioning

## Versioning

Use Semantic Versioning (MAJOR.MINOR.PATCH): MAJOR for breaking changes, MINOR
for backward-compatible features, PATCH for backward-compatible fixes. While
pre-1.0 (0.y.z) the public surface may still move - say so in the README so
consumers know the contract is not yet frozen.

## Changelog

Keep a human-readable [../../CHANGELOG.md](../../CHANGELOG.md) in the
"Keep a Changelog" format: an `[Unreleased]` section at the top that every
user-facing change adds a line to (under Added / Changed / Fixed / Removed /
Security), plus a dated section per release. The changelog is written for the
people who use the software; the git log is not a substitute for it.

## Cutting a release

1. Move the `[Unreleased]` entries into a new dated version section in
   [../../CHANGELOG.md](../../CHANGELOG.md) and bump the version number.
2. Tag the release commit (e.g. `v1.4.0`) once it is on the default branch.
3. Publish release notes from that changelog section.
4. Deploy the tagged build (see [10-production-readiness.md](10-production-readiness.md)
   and the CD workflow in `.github/workflows/`).

Automate steps 1-3 when the cadence justifies the effort; do them by hand until
then (cheapest-sufficient, see [00-principles.md](00-principles.md)).
