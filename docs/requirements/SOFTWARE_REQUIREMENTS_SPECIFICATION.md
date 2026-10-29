# Tory Software Requirements Specification

**Course:** Singapore Polytechnic ST0529 CA1  
**Product:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*  
**Lifecycle:** Waterfall: Planning, Requirements, Design, Implementation, Testing, Deployment  
**Requirements window:** 31 October–5 November 2026 (target; schedule risk tracked)  
**Status:** Draft for owner review — **not approved; Requirements exit pending**  
**Backend constraint:** Django 5.2 LTS + PostgreSQL approved in [ADR-001](../decisions/ADR-001-backend-and-database.md).

## 1. Purpose

This SRS translates the approved high-level Tory baseline into testable requirements for owner review. It is a Requirements-stage draft, not a Design, architecture, implementation or testing record. Each detailed behavior is marked either as directly based on the **confirmed Planning baseline** or as a **proposed detail** requiring owner approval. No requirement in this draft claims implementation or test completion.

## 2. Problem context and product scope

Tory is intended to help users record inventory movements and use recent demand to support replenishment decisions. This is a project framing based on the approved Charter; customer interviews, validated market research, operating metrics and measured business losses have not been supplied.

### 2.1 Confirmed high-level scope

- Manual stock-in, stock-out and stock adjustment transactions.
- Atomic CSV import of **stock transactions only**; reject the whole batch if any row is invalid. Product catalog import is excluded.
- PostgreSQL persistence.
- Manager and Staff access with distinct permissions.
- Per-product supplier lead time, safety stock and reorder settings.
- Explainable seven-day moving-average demand forecasting.
- Explainable reorder recommendations.
- Hosted staging demonstration and automated CI; automated CD is optional.

### 2.2 Exclusions

- Product catalog CSV import.
- A new frontend framework, hosting provider, architecture, deployment provider or detailed pipeline choice in this SRS.
- Microservices, barcode scanning, multi-warehouse management, purchasing automation, mobile application, notifications, unapproved integrations or expanded analytics.
- Forecasting methods beyond the approved seven-day moving average unless changed by formal change control.
- Production operation or production-readiness claims. The PoC is isolated feasibility material, not application code.

## 3. Stakeholders and owner-defined scenarios

No stakeholder interviews are claimed. These scenarios express the owner-defined role labels and approved high-level goals. Exact permissions remain **PROPOSED** in [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md) pending owner approval.

### Manager scenario — owner-defined role, proposed workflow

As a Tory Manager, I need to review inventory, oversee stock movements, configure each product's supplier/reorder settings and inspect forecast/reorder explanations so I can manage inventory and replenishment. The distinction between Manager and Staff is confirmed; the individual actions and permissions in this scenario are proposed for approval.

### Staff scenario — owner-defined role, proposed workflow

As a Tory Staff user, I need to review permitted inventory information and perform approved day-to-day stock transactions so I can keep stock records current. The Staff role is confirmed; permitted transactions and visibility are proposed for approval.

### Project owner / solo developer

The same person owns the project and performs development, review, testing and demonstration. Codex is a guided coding aid; generated changes are independently reviewed and tested. This is a delivery constraint, not a product user role.

## 4. Requirement status and priority conventions

- **Confirmed baseline:** the high-level capability is owner-approved in the Charter/P1. Detailed acceptance criteria below remain draft until SRS approval.
- **PROPOSED detail:** a specific interpretation added to make the baseline testable; it is not an approved business rule until accepted by the owner.
- **TBD:** information is absent and must be resolved or explicitly deferred with an owner and due stage.
- Priority: **Must** = needed to satisfy the fixed baseline; **Should** = proposed quality/detail that materially supports baseline completion; **TBD** = owner decides whether it is required.

## 5. Functional requirements

Each acceptance criterion is a proposed verification condition for the SRS. Where a detail is not approved, it becomes binding only after owner approval.

### FR-001 — Identify and select a product

- **Priority/status:** Must-supports baseline; product fields and maintenance workflow **PROPOSED**.
- **Actor:** Manager or Staff, subject to approved permissions.
- **Preconditions:** User is authenticated and authorized; product exists and is active under the proposed lifecycle rule.
- **Main flow:** User selects a product using its approved identifier; Tory presents the product identity and current recorded stock.
- **Errors:** Unknown, inactive or unauthorized product selection is rejected with a clear message and no data mutation.
- **Acceptance criteria (proposed):** Given an authorized user and an existing product, selecting it returns its approved identifying fields and current quantity. An unknown or unauthorized identifier returns a controlled error. Exact fields and product creation/editing rights require approval.

### FR-002 — View current inventory

- **Priority/status:** Must-supports manual movement and replenishment baseline; list/search/filter details **PROPOSED**.
- **Actor:** Manager and Staff, with visibility controlled by the approved matrix.
- **Preconditions:** User is authenticated; products exist.
- **Main flow:** User requests inventory information; Tory displays approved product identifiers and recorded quantities.
- **Errors:** Unauthorized request is denied; unavailable database data is reported without presenting an unverified quantity as current.
- **Acceptance criteria (proposed):** For an authorized product, the displayed quantity equals the committed PostgreSQL quantity after the latest successful transaction. A denied user cannot retrieve the protected inventory view. Search/filter features are not required unless approved.

### FR-003 — Record stock-in

- **Priority/status:** **Confirmed baseline capability**; input fields and role allocation **PROPOSED detail**.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits a stock-in quantity; Tory validates it, records the movement and updates the product's on-hand quantity atomically.
- **Errors:** Invalid/nonpositive quantity, unknown product, duplicate request or database failure is rejected or safely deduplicated under the approved rule; no partial state is allowed.
- **Acceptance criteria (proposed):** For a valid quantity `q`, committed on-hand quantity becomes prior quantity + `q`. Invalid input leaves quantity unchanged. A durable movement record is proposed and requires an explicit history/retention decision; FR-012 concerns validation feedback, not history.

### FR-004 — Record stock-out

- **Priority/status:** **Confirmed baseline capability**; demand classification and negative-stock policy **PROPOSED detail**.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits a stock-out quantity and, if approved, a reason/type; Tory validates and commits the movement and quantity change atomically.
- **Errors:** Invalid input, insufficient stock under the proposed no-negative rule, unknown product, duplicate request or database failure causes no partial quantity change.
- **Acceptance criteria (proposed):** A valid stock-out changes quantity by the approved amount. Under the proposed rule, quantity cannot become negative and a rejected stock-out changes no committed data. Whether stock-out counts as demand for forecasting must be explicitly approved.

### FR-005 — Record stock adjustment

- **Priority/status:** **Confirmed baseline capability**; permissions, reason and adjustment semantics **PROPOSED detail**.
- **Actor:** Proposed Manager-only; Staff policy requires approval.
- **Preconditions:** User has adjustment permission; product exists; adjustment input is valid.
- **Main flow:** User submits an adjustment with the approved quantity/reason representation; Tory records and applies it atomically.
- **Errors:** Unauthorized, invalid or conflicting adjustment is rejected without partial update.
- **Acceptance criteria (proposed):** An authorized valid adjustment produces the exact approved resulting quantity or signed delta, and a rejected adjustment leaves quantity unchanged. Owner must choose absolute-count versus signed-delta semantics and reason requirements.

### FR-006 — Import stock transactions atomically from CSV

- **Priority/status:** **Confirmed baseline capability**, transaction rows only; exact file contract is **PROPOSED detail**.
- **Actor:** Proposed Manager-only; Staff import permission requires approval.
- **Preconditions:** User authorized; upload accepted by the approved size/encoding constraints; referenced products exist.
- **Main flow:** Tory parses and validates the entire stock-transaction batch, checks all rows against applicable inventory rules, and commits all rows as one logical batch.
- **Errors:** Any invalid row, malformed file, unknown product, insufficient stock, duplicate request or database failure rejects the entire batch; no row from that batch is committed.
- **Acceptance criteria:** (1) A fully valid batch applies all rows according to the approved ordering/duplicate-SKU rule. (2) Inserting one invalid row at any position causes zero batch changes. (3) Invalid product-catalog rows are not processed as catalog imports. (4) PostgreSQL state before and after a rejected batch is identical for the batch's effects. Header, encoding, row limits, duplicate file handling and error report format remain proposed/TBD.

### FR-007 — Authenticate users and distinguish Manager/Staff access

- **Priority/status:** Distinct Manager and Staff permissions are **Confirmed baseline**; authentication mechanism and exact permission mapping are **PROPOSED/TBD**.
- **Actor:** Manager, Staff, and any proposed account administrator.
- **Preconditions:** User account provisioned through an owner-approved process.
- **Main flow:** User authenticates; each protected operation is authorized using the approved role/action matrix.
- **Errors:** Invalid credentials, inactive account or missing permission is denied; no protected data change occurs.
- **Acceptance criteria (proposed):** For every permission-matrix row, an automated test verifies both allowed and denied behavior for Manager and Staff. Unauthenticated access to protected operations is denied. Account creation, password reset, session behavior and administrative actor require approval.

### FR-008 — Maintain per-product supplier and reorder settings

- **Priority/status:** **Confirmed baseline capability**; fields, units, edit permissions and validation **PROPOSED detail**.
- **Actor:** Proposed Manager can maintain; Staff read-only or no access is proposed.
- **Preconditions:** Product exists; user has approved configuration permission.
- **Main flow:** User views or updates the approved lead-time, safety-stock and reorder settings for one product; Tory validates and persists the changes.
- **Errors:** Invalid values, missing product or unauthorized edit is rejected with no partial configuration update.
- **Acceptance criteria (proposed):** Each product's approved settings persist and are used by its recommendation; values for one product do not alter another product. Meaning of “reorder settings” beyond lead time and safety stock is TBD.

### FR-009 — Supply eligible demand observations for forecasting

- **Priority/status:** Supporting requirement **PROPOSED/TBD**; the baseline confirms forecasting but does not define its source data.
- **Actor:** System processing stock movement data; user role sees result under FR-010.
- **Preconditions:** Approved source and classification rule identify demand observations and coverage for the seven-day window.
- **Main flow:** Tory selects only owner-approved demand data, grouped by the approved calendar interval and product.
- **Errors:** Incomplete, unavailable or unclassified observations are reported as insufficient/unknown rather than silently treated as zero, subject to owner approval.
- **Acceptance criteria (proposed):** A reference dataset with known eligible demand events produces a documented seven-day input series; adjustments and replenishments are excluded unless explicitly approved as demand. Data source, stock-out proxy, timezone and completeness semantics block approval.

### FR-010 — Calculate and display an explainable seven-day moving average

- **Priority/status:** **Confirmed baseline capability**; day boundaries, missing-day and rounding semantics **PROPOSED detail**.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** Approved demand source and sufficient/completeness rules are satisfied for the product.
- **Main flow:** Tory calculates the moving-average value from the approved seven-day window and displays the result with the dates and daily inputs/assumptions needed to explain it.
- **Errors:** Insufficient or incomplete demand history produces the approved unavailable/partial status, not a fabricated numeric forecast.
- **Acceptance criteria (proposed):** For a fully specified seven-day reference series, displayed average equals the arithmetic mean of eligible demand over those seven approved days. Displayed explanation names the window and inputs. Missing days, true zero-demand days and rounding are tested separately after approval.

### FR-011 — Produce an explainable reorder recommendation

- **Priority/status:** **Confirmed baseline capability**; formula, rounding and treatment of stock on order **PROPOSED detail**.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** FR-010 result and approved product supplier/reorder settings are available.
- **Main flow:** Tory calculates a recommendation using approved inputs and displays the result and formula/input explanation.
- **Errors:** Missing forecast/settings or invalid values yield an unavailable recommendation with a reason; no purchase order is created.
- **Acceptance criteria (proposed):** Given approved inputs, the recommendation equals the owner-approved formula; changing one input changes only affected outputs. The recommendation is advice only. Automatic procurement is excluded. Treatment of inbound orders, minimum order quantity and target stock remain TBD.

### FR-012 — Provide controlled validation feedback

- **Priority/status:** **PROPOSED detail** supporting movement and CSV baseline.
- **Actor:** Authorized user.
- **Preconditions:** User submits a transaction or batch.
- **Main flow:** Tory reports success or identifies the relevant row/field and reason for rejection without exposing secrets or internal stack traces.
- **Errors:** Error-reporting failure must not weaken atomicity or authorization.
- **Acceptance criteria (proposed):** Invalid movement feedback identifies a correctable input; CSV feedback identifies rejected row(s) per approved policy; rejected batches leave data unchanged. Exact message format and whether all errors or first error are shown are owner decisions.

## 6. Nonfunctional requirements

All numeric targets below are **PROPOSED** for owner approval or marked **TBD**. None is a measured result. Formal verification plans belong in the Testing stage; this SRS defines the target only after approval.

### Security

**NFR-001 — Authorization:** Every protected operation shall enforce the approved Manager/Staff permission matrix at the server side; denial shall occur before any protected mutation. **Proposed verification:** positive and negative automated tests for every matrix cell.

**NFR-002 — Credential and secret handling:** Credentials, session secrets and database passwords shall not be committed to source or returned in application errors; staging shall use transport encryption where the selected provider supports it. Authentication/session details and security review criteria are **TBD** pending approval.

### Correctness and data integrity

**NFR-003 — Transaction integrity:** A committed movement shall atomically update quantity and its associated record if the owner approves movement history. A rejected CSV batch shall commit zero batch changes. Concurrent updates shall preserve the approved inventory invariants using PostgreSQL. **Proposed verification:** PostgreSQL integration/concurrency tests; no SQLite-only concurrency evidence.

**NFR-004 — Forecast reproducibility:** For fixed approved demand inputs and settings, forecast and recommendation outputs shall be deterministic and reproducible. Formula version, input window and rounding must be visible or recorded as approved.

### Usability

**NFR-005 — Understandable outcomes:** Users shall be able to distinguish stock-in, stock-out and adjustment outcomes and understand why a CSV batch or forecast is rejected/unavailable. Exact interface and usability testing method are **TBD**; no frontend is selected.

### Performance

**NFR-006 — Response time:** **PROPOSED:** warm staging requests for routine inventory reads and manual transactions complete within 2 seconds at the 95th percentile; forecast calculation within 3 seconds at the 95th percentile. Dataset size, concurrency, network conditions and cold-start exclusion must be approved before this target is testable. No current performance evidence exists.

### Maintainability

**NFR-007 — Change and schema management:** Database schema changes shall be versioned and reproducible from source-controlled migrations. Generated code must be independently reviewed by the solo developer. Review checklist and supported-version policy are **TBD** for Design.

### Reliability

**NFR-008 — Failure handling and recovery:** Failed transactions shall not leave partial stock changes. Backup frequency, recovery point/time objectives and data retention are **TBD**; zero-cost hosting candidates may not provide managed backups.

### Deployment

**NFR-009 — Staging and cost constraint:** Tory shall provide a hosted staging demonstration using PostgreSQL and remain within the confirmed SGD 0 cash ceiling. Provider, eligibility, quotas, payment-method rules and connectivity must be verified before Design exit. No provider is selected.

**NFR-010 — Automated CI:** Automated CI shall install approved dependencies, provision/connect to PostgreSQL, apply migrations and run approved checks on relevant changes. Provider, repository visibility, quota and exact gate set are **TBD**. CD is optional and not required by this SRS.

### Testability

**NFR-011 — Requirement verification:** Every approved Must requirement shall map to one or more proposed/approved acceptance tests in the traceability matrix; each formal result shall be recorded with source revision and environment. No test result is claimed here.

## 7. Business rules and data requirements

Detailed candidate rules and unresolved alternatives are maintained in [BUSINESS_RULES_AND_EDGE_CASES.md](BUSINESS_RULES_AND_EDGE_CASES.md). They are not approved until accepted by the owner.

### Logical data concepts (proposed; not a schema design)

- **Product:** stable identifier, SKU, display name, current on-hand quantity, lifecycle state; exact fields and product maintenance actions TBD.
- **Stock movement:** product, movement type, quantity/delta, timestamp, actor/request identity and any approved reason/reference. Ledger retention and correction method TBD.
- **Import batch:** batch identity, source metadata, status and row-level validation outcomes; retention and duplicate-file detection TBD.
- **Supplier/reorder settings:** product association, lead time, safety stock, and owner-approved additional reorder parameters.
- **Demand observation/forecast:** product, date/window, eligible demand input, moving-average result, explanation and recommendation calculation version/inputs. Data source and retention TBD.
- **User/role:** account identity, active status and Manager/Staff role under the approved identity lifecycle.

PostgreSQL is approved. The logical entities above do not prescribe tables, ORM relationships, application architecture or hosting topology.

## 8. Assumptions and dependencies

- The fixed baseline and exclusions in the approved Charter and P1 record remain unchanged unless formally changed.
- Django 5.2 LTS + PostgreSQL is the approved backend. Exact deployment patch versions and configuration are later decisions.
- The project has one solo developer, 10–15 hours/week, deadline 27 November 2026 and SGD 0 cash budget. Schedule risk is high and tracked in Planning.
- Codex may assist development; generated changes require independent review and verification.
- A demand dataset can be supplied or derived only after owner approval of its source and classification. Availability/quality are not established.
- A zero-cost PostgreSQL CI/staging solution may be available, but provider eligibility, quotas, connectivity and no-charge operation are unresolved.
- Existing PoC evidence is narrow and historical. Source PoC reports record 14/14 passed; PoC source reviewed there had 15 test methods; 16/16 is owner-reported without a matching artifact. No PoC result completes formal Testing.
- Jira and a separate `tory-inventory` GitHub repository are desired work-management changes, but neither is verified as configured. The current course repository remains the documented project repository until changed.

## 9. Open questions and requirement boundaries

See [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) for the complete decision list. Blocking issues include exact role permissions, product fields and lifecycle, stock-out/demand classification, CSV contract and limits, forecast data availability/completeness, reorder formula and settings, duplicate request behavior, numeric NFR targets, accessibility/browser expectations, and identity/account administration.

### Explicit boundaries

- Product CSV import is excluded.
- Reorder recommendations do not place orders.
- No frontend framework, hosting provider, architecture, CI vendor or CD solution is selected here.
- No audit/history, export, backup, user-management or data-retention capability is treated as approved unless the owner accepts the proposed requirement.
- Requirements approval does not authorize Design, Implementation or Testing entry; each Waterfall stage requires its own gate.

## 10. Requirements verification and change control

1. The owner reviews each FR/NFR status and approves, revises, defers or rejects it; proposed details do not become binding by appearing in this draft.
2. Approved requirements receive a baseline revision and traceability IDs. Ambiguous/TBD items must be resolved or explicitly deferred with an owner and target stage.
3. Proposed acceptance tests are reviewed for determinism, coverage and feasibility; they are not test execution evidence.
4. The traceability matrix links approved Charter objectives to requirements, proposed acceptance tests, and later Design/Build/Test evidence placeholders.
5. Changes after SRS approval require a documented change request describing scope, schedule, cost (must remain SGD 0 unless changed), security/data and verification impacts, with explicit owner approval.
6. Requirements exit is complete only when the owner approves the SRS and records the stage-gate decision. **Requirements exit is currently PENDING OWNER APPROVAL.**

## References

- [Approved Project Charter](../planning/PROJECT_CHARTER.md)
- [Planning Gate P1 — approved with conditions](../planning/PLANNING_GATE_P1.md)
- [Owner Decisions](../planning/OWNER_DECISIONS.md)
- [Planning Review](../planning/PLANNING_REVIEW.md)
- [ADR-001: Backend and Database](../decisions/ADR-001-backend-and-database.md)
- [Technology Evaluation](../TECHNOLOGY_EVALUATION.md)
- [PoC Results](../POC_RESULTS.md), [Technical Feasibility](../TECHNICAL_FEASIBILITY.md), [PoC Handover](../POC_HANDOVER.md)
