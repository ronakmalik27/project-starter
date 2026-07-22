# 10 - Security

<!-- Starter skeleton. If your project already has this document, refine it
     against these sections and current industry standards; otherwise create it
     from here. Delete sections that do not apply and add your own. -->

## 1. Overview
<!-- The security posture and scope of this document. -->

## 2. Threat model
<!-- The main threats considered and the assumed attacker capabilities. -->
<!-- Multi-tenant SaaS: cross-tenant data leakage is the top risk, treat it
     accordingly. Isolation tests (no code path, including background jobs,
     can return another tenant's rows) are mandatory, not optional. Any
     support impersonation of a tenant user must be audited, time-boxed, and
     revocable. See docs/adr/0002-multi-tenancy-and-tenant-isolation.md. -->

## 3. Authentication
<!-- How users and services prove identity. -->

## 4. Authorization
<!-- How access is granted and checked per resource and action. -->

## 5. Secrets management
<!-- Where secrets live and how they are rotated. -->

## 6. Data classification and handling
<!-- Sensitivity tiers and the handling rules for each. -->

## 7. Logging and audit
<!-- What gets logged, for how long, and who can read it. -->

## 8. Dependency and supply-chain hygiene
<!-- How dependencies are vetted, scanned, and kept current. -->
