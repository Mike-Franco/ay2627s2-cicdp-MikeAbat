# ADR-003: Django Templates and Bootstrap Frontend

**Decision date:** 3 November 2026
**Status:** Accepted by project owner
**Issue:** TORY-9
**Scope:** Frontend approach for Tory

## Decision and rationale

Use **Django Templates + Bootstrap**, with small amounts of JavaScript where useful, for Tory's frontend. This is the project owner's 3 November 2026 decision. [ADR-001](ADR-001-backend-and-database.md) retains Django 5.2 LTS and PostgreSQL; [ADR-002](ADR-002-agile-kanban-delivery.md) retains Agile Kanban for remaining delivery. The approved business rules, roles, FR/NFR identifiers and acceptance outcomes remain unchanged.

Compared with **React + a Django API**, server-rendered Django pages avoid a second application build, API contract, client-side authentication state and separate frontend deployment path within a solo-developer, SGD 0 project ending **27 November 2026 at 17:00 Asia/Singapore**. Django's forms, templates, session authentication and CSRF protection fit the approved Manager/Staff workflows and reduce integration work. Bootstrap supplies a consistent responsive layout without selecting a paid design service. This is a schedule and integration judgment, **not** a measured performance or security result. React would offer richer client interaction and independent UI evolution, but those benefits do not outweigh the added build, testing and deployment work for the approved MVP.

## Proposed MVT structure for the first increment

The following is a **design proposal, not an implemented module/schema plan or a separate owner approval of product behavior**:

| Layer | Proposed responsibility and requirement boundary |
|---|---|
| Views, forms, templates and Bootstrap | Server-render pages and validate submitted values; use small JavaScript for optional interaction. Present stock, history and forecast outcomes from approved FR-001–FR-012. Templates do not decide permissions or stock quantities. |
| Authentication and authorization | Django email/password and server-managed sessions under BR-042–BR-045/G-07. Enforce role, current same-business inventory assignment and CSRF on protected views and mutations (BR-021–BR-027, NFR-001/NFR-002); hiding a button is insufficient. G-13 account/catalogue authority remains open. |
| Domain services | Centralize stock-in/out, adjustments, CSV, expiry, disposal and deactivation rules. Make accepted inventory mutations and their attributable movement/audit evidence atomic in PostgreSQL; prevent negative/double-allocated stock under concurrency (NFR-003, G-01–G-05/G-09/G-11). Exact service and locking boundaries remain to be designed and tested. |
| ORM models and migrations | Persist the approved logical concepts with versioned Django migrations (NFR-007): a shared business-level product catalogue, separate inventories with inventory-specific selling prices, per-product reorder settings, receiving batches, stock movements and audit attribution. Model names, relationships, constraints and module splits remain proposed. |

The shared catalogue and inventory-specific records follow BR-016–BR-019; receiving order, expiry/quarantine and movement evidence follow the recorded batch and audit decisions. No table layout, price-edit permission, movement category or returned/damaged-stock resolution is invented here. The first implementation increment should prove a narrow, authorised stock mutation with PostgreSQL rollback and audit evidence before expanding workflows. Trace each increment to the [SRS](../requirements/SOFTWARE_REQUIREMENTS_SPECIFICATION.md), [business rules](../requirements/BUSINESS_RULES_AND_EDGE_CASES.md), [role matrix](../requirements/ROLE_PERMISSION_MATRIX.md), [gap analysis](../requirements/REQUIREMENTS_GAP_ANALYSIS.md) and [traceability matrix](../requirements/REQUIREMENTS_TRACEABILITY_MATRIX.md).

## CA1 framework evidence to capture

Demonstrate at least three Django capabilities with source revision and test/report evidence, **not as already completed results**:

1. **Forms and CSRF middleware:** validated inputs and rejected invalid-CSRF stock mutation without database change.
2. **Authentication, sessions and authorization checks:** Manager/Staff allowed and denied requests, including an out-of-scope inventory and deactivated session.
3. **ORM migrations and PostgreSQL transactions:** clean migration, atomic stock/audit commit or rollback and a competing stock-out test.
4. **Templates and template inheritance:** a shared Bootstrap layout with role-appropriate rendered pages, while server-side checks remain authoritative.

## Trade-offs and open boundaries

Server rendering may need extra requests or carefully limited JavaScript for dynamic interactions. Bootstrap does not ensure accessibility or usable feedback by itself; review those outcomes against the eventual interface criteria. Django and PostgreSQL still require explicit transaction, security and performance design. No API-first or SPA interface is promised; an API later would require its own decision and tests. The current decision does not select a hosting provider, prove zero-cost HTTPS/email/backup feasibility (**G-10 remains blocking**), close other gaps, or approve the complete SRS or historical stage reviews. The earlier Charter, ADR-001/ADR-002, PoC reports and owner decisions retain their dated evidence and authority.
