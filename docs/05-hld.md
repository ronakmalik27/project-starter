# 05 - High-Level Design

<!-- Starter skeleton. If your project already has this document, refine it
     against these sections and current industry standards; otherwise create it
     from here. Delete sections that do not apply and add your own. -->

## 1. Overview
<!-- The system at a glance and its main design goals. -->

## 2. Context diagram
<!-- The system's boundary and its external actors and dependencies. -->

## 3. Components and responsibilities
<!-- The major components and what each one owns. -->

## 4. Data flow
<!-- How data moves through the components end to end. -->

## 5. Technology choices
<!-- Key technology decisions; link the relevant ADRs in docs/adr/. -->

## 6. Cross-cutting concerns
<!-- Concerns that span components: logging, auth, config, and similar. -->
<!-- Multi-tenant SaaS: name the choke point every tenant-owned query goes
     through (the one place the tenant boundary is enforced), and how the
     platform super-admin plane stays a separate code path from
     tenant-scoped request handling, not a tenant role. If customers
     subdivide their account, note that a workspace is an authorization
     scope, not a second isolation tier: the tenant boundary stays the only
     hard one, workspace access is resolved per request. See
     docs/adr/0002-multi-tenancy-and-tenant-isolation.md and the worked
     example in docs/design/multi-tenancy.md. -->

## 7. Deployment topology
<!-- Where components run and how they are connected in each environment. -->
