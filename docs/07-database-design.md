# 07 - Database Design

<!-- Starter skeleton. If your project already has this document, refine it
     against these sections and current industry standards; otherwise create it
     from here. Delete sections that do not apply and add your own. -->

## 1. Overview
<!-- The storage engine choice and the scope of this schema. -->

## 2. Entity model
<!-- The core entities and how they relate to each other. -->

## 3. Tables
<!-- Table definitions: columns, types, and constraints. -->
<!-- Multi-tenant SaaS: give every tenant-owned table a tenant-id
     discriminator and enforce it at one choke point (row-level security if
     the database supports it, otherwise a single query layer, never inline
     per handler). Note the silo (schema or database per tenant) escape
     hatch for tenants, or a single workspace, that need stronger isolation.
     If customers subdivide
     their account, add a nullable workspace-id column (an authorization
     scope, not a second isolation tier) and tables for scoped RBAC:
     roles, role_permissions, role_assignments (principal x scope), teams,
     team_members. See docs/adr/0002-multi-tenancy-and-tenant-isolation.md
     and the worked example in docs/design/multi-tenancy.md. -->

## 4. Indexes
<!-- Indexes and the queries each one supports. -->

## 5. Migration policy
<!-- How schema changes are made, versioned, and rolled back. -->

## 6. Data lifecycle and retention
<!-- How records age, archive, and get deleted over time. -->
