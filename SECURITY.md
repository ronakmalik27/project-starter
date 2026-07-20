# Security policy

## Reporting a vulnerability

Please report security issues privately - not in a public issue or pull request:

- Preferred: this repository's private vulnerability reporting (the Security tab
  -> "Report a vulnerability").
- Or email your security contact (replace this line with a real address before
  you rely on it).

Include what you found, how to reproduce it, and the impact you expect. Expect
an acknowledgement within a few business days and an agreed disclosure timeline;
please give a reasonable window to ship a fix before any public disclosure.

## Supported versions

State which versions receive security fixes (fill in as you cut releases):

| Version | Supported |
|---|---|
| latest | yes |
| older | best effort |

## Handling secrets

Never commit a secret (API key, token, password, credentialed connection
string, private key) anywhere in the repo. Secrets live in a local secret store
in development and a managed secret store in production. A secret that lands in
the repo, a PR, or a log is compromised: rotate it. The gitleaks scan is the
backstop, not the rule - see
[docs/process/03-coding-standards.md](docs/process/03-coding-standards.md).
