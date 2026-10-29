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

No stakeholder interviews are claimed. These scenarios express owner-defined roles and goals. Manager-only adjustment is approved (BR-003); other action permissions remain **PROPOSED/TBD** in [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md).

### Manager scenario — owner-defined role, proposed workflow

As a Tory Manager, I need to review inventory, oversee stock movements, configure each product's supplier/reorder settings and inspect forecast/reorder explanations so I can manage inventory and replenishment. The distinction between Manager and Staff is confirmed; the individual actions and permissions in this scenario are proposed for approval.

### Staff scenario — owner-defined role, proposed workflow

As a Tory Staff user, I need to review permitted inventory information and perform approved day-to-day stock transactions so I can keep stock records current. The Staff role is confirmed; permitted transactions and visibility are proposed for approval.

### Project owner / solo developer

The same person owns the project and performs development, review, testing and demonstration. Codex is a guided coding aid; generated changes are independently reviewed and tested. This is a delivery constraint, not a product user role.

## 4. Requirement status and priority conventions

- **Confirmed baseline / owner rule:** Charter/P1 capabilities and [BR-001–BR-011](OWNER_REQUIREMENTS_DECISIONS.md) are approved individually. Other detailed criteria remain draft until SRS approval.
- **PROPOSED detail:** a specific interpretation added to make the baseline testable; it is not an approved business rule until accepted by the owner.
- **TBD:** information is absent and must be resolved or explicitly deferred with an owner and due stage.
- Priority: **Must** = needed to satisfy the fixed baseline; **Should** = proposed quality/detail that materially supports baseline completion; **TBD** = owner decides whether it is required.

## 5. Functional requirements

Each acceptance criterion is a proposed verification condition for the SRS. Where a detail is not approved, it becomes binding only after owner approval.

### FR-001 — Identify and select a product

- **Priority/status:** Required, trimmed, case-insensitively unique active SKU **APPROVED BR-001**; other fields/lifecycle proposed or TBD.
- **Actor:** Manager or Staff, subject to approved permissions.
- **Preconditions:** User is authenticated and authorized; product exists and is active under the proposed lifecycle rule.
- **Main flow:** User selects a product using its approved identifier; Tory presents the product identity and current recorded stock.
- **Errors:** Unknown, inactive or unauthorized product selection is rejected with a clear message and no data mutation.
- **Acceptance criteria:** Reject missing/blank-after-trim SKU and trim/case collisions among active products. Authorized selection returns approved identity and current quantity; unknown/unauthorized selection is controlled. SKU renaming/reuse and product maintenance rights remain TBD.

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

- **Priority/status:** Stock-out capability confirmed; no-negative rule **APPROVED BR-002** and stock-out demand proxy **APPROVED BR-006**; actor/input details TBD.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits a stock-out quantity and, if approved, a reason/type; Tory validates and commits the movement and quantity change atomically.
- **Errors:** Reject a stock-out that would make on-hand negative without partial mutation. Other validation and manual duplicate handling remain TBD.
- **Acceptance criteria:** Stock-out equal to on-hand may reach zero; one exceeding on-hand is rejected atomically. Every committed stock-out counts as demand, as a proxy rather than validated sales.

### FR-005 — Record stock adjustment

- **Priority/status:** Manager-only, absolute physical count, required reason and recorded difference **APPROVED BR-003**; reason format/retention TBD.
- **Actor:** Manager only; Staff cannot perform adjustment.
- **Preconditions:** User has adjustment permission; product exists; adjustment input is valid.
- **Main flow:** Manager enters physical count and reason; Tory sets on-hand to that count and records `new count − prior on-hand` atomically.
- **Errors:** Unauthorized, invalid or conflicting adjustment is rejected without partial update.
- **Acceptance criteria:** Prior `p`, physical count `c` yields on-hand `c` and recorded difference `c − p` with reason. Reject Staff, missing reason and negative resulting count without partial mutation. Count precision and retention TBD.

### FR-006 — Import stock transactions atomically from CSV

- **Priority/status:** Transaction CSV capability confirmed; `sku,change`, atomicity, empty/header-only rejection **APPROVED BR-004**; successful identical-file re-upload rejection **APPROVED BR-005**; parsing details TBD.
- **Actor:** Proposed Manager-only; Staff import permission requires approval.
- **Preconditions:** User authorized; upload accepted by the approved size/encoding constraints; referenced products exist.
- **Main flow:** Tory parses and validates the entire stock-transaction batch, checks all rows against applicable inventory rules, and commits all rows as one logical batch.
- **Errors:** Invalid rows, malformed/empty/header-only uploads, insufficient stock, or identical re-upload after a successful import reject the whole batch without mutation.
- **Acceptance criteria:** A valid new `sku,change` batch commits all rows; any invalid row commits none. Empty/header-only files fail. A previously successful identical file cannot apply twice; a failed upload is not a successful prior import. Committed negative changes count as demand; rejected rows do not. Duplicate identity, encoding, whitespace, row order/limits and error format TBD.

### FR-007 — Authenticate users and distinguish Manager/Staff access

- **Priority/status:** Distinct roles confirmed; Manager-only adjustment **APPROVED BR-003**; other permission cells and account provisioning TBD.
- **Actor:** Manager, Staff, and any proposed account administrator.
- **Preconditions:** User account provisioned through an owner-approved process.
- **Main flow:** User authenticates; each protected operation is authorized using the approved role/action matrix.
- **Errors:** Invalid credentials, inactive account or missing permission is denied; no protected data change occurs.
- **Acceptance criteria (proposed):** For every permission-matrix row, an automated test verifies both allowed and denied behavior for Manager and Staff. Unauthenticated access to protected operations is denied. Account creation, password reset, session behavior and administrative actor require approval.

### FR-008 — Maintain per-product supplier and reorder settings

- **Priority/status:** Supplier/reorder settings confirmed; positive whole calendar-day lead time per product **APPROVED BR-010**; other settings and edit permission TBD.
- **Actor:** Proposed Manager can maintain; Staff read-only or no access is proposed.
- **Preconditions:** Product exists; user has approved configuration permission.
- **Main flow:** User views or updates the approved lead-time, safety-stock and reorder settings for one product; Tory validates and persists the changes.
- **Errors:** Invalid values, missing product or unauthorized edit is rejected with no partial configuration update.
- **Acceptance criteria:** Each product's lead time is a positive whole number of calendar days; reject zero, negative or fractional days. Values for one product do not alter another. Safety-stock constraints and other settings TBD.

### FR-009 — Supply eligible demand observations for forecasting

- **Priority/status:** Stock-out proxy, Singapore calendar window and reliable seven-day coverage **APPROVED BR-006–BR-008**; observation mechanism TBD.
- **Actor:** System processing stock movement data; user role sees result under FR-010.
- **Preconditions:** Dated committed movements and trustworthy observation coverage are available for each of the prior seven Asia/Singapore calendar days; how coverage is established remains TBD.
- **Main flow:** Count all committed manual and negative-CSV stock-outs; exclude stock-in, adjustments and rejected-batch rows. Group by the previous seven complete Singapore calendar days, excluding current day.
- **Errors:** Any unobserved/incomplete day makes the forecast unavailable. Absence of movement records alone does not establish a verified zero day.
- **Acceptance criteria:** A verified zero-demand day contributes zero; an unobserved day makes the seven-day input series unavailable. Boundary events are assigned by Asia/Singapore local calendar date. The proxy is not validated customer sales. Source record/coverage design and retention remain TBD.

### FR-010 — Calculate and display an explainable seven-day moving average

- **Priority/status:** Seven-day average confirmed; window, coverage and precision **APPROVED BR-007–BR-009**.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** Seven previous complete, reliably observed Asia/Singapore days exist for the product.
- **Main flow:** Tory calculates the moving-average value from the approved seven-day window and displays the result with the dates and daily inputs/assumptions needed to explain it.
- **Errors:** Missing or incomplete coverage on any day makes forecast unavailable; do not infer zero from no records.
- **Acceptance criteria:** Display previous seven dates and daily stock-out proxy inputs. Average is total / 7, displayed to two decimal places; retain full precision for downstream calculations. For verified `[1,0,1,0,1,0,0]`, display `0.43`; if any day lacks coverage, show unavailable. See [worked examples](BUSINESS_RULES_AND_EDGE_CASES.md#edge-case-acceptance-examples-to-approve).

### FR-011 — Produce an explainable reorder recommendation

- **Priority/status:** Formula and informational nature **APPROVED BR-011**; stock on order, trigger and safety-stock constraints TBD.
- **Actor:** Manager and/or Staff according to approved permissions.
- **Preconditions:** FR-010 result and approved product supplier/reorder settings are available.
- **Main flow:** Compute reorder point = full-precision average daily demand × positive whole calendar-day lead time + safety stock; suggest `max(0, ceil(reorder point − current on-hand))`. Display inputs and calculation; create no purchase order.
- **Errors:** Missing forecast/settings or invalid values yield an unavailable recommendation with a reason; no purchase order is created.
- **Acceptance criteria:** For verified demand total `3` over seven days, lead time `7`, safety stock input `0`, on-hand `0`: full-precision average `3/7`, reorder point `3`, suggested quantity `3`; displayed `0.43` must not be multiplied back (it would incorrectly suggest `4`). Zero safety stock here is a test input, not approval of its allowed range. Missing coverage yields no numeric recommendation. Inventory on order, trigger semantics, safety-stock constraints and pack/minimum rules TBD.

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

**NFR-003 — Transaction integrity:** No accepted stock-out makes on-hand negative. Manager adjustment sets physical count and records difference/reason atomically. A rejected CSV batch, including empty/header-only or previously successful identical upload, commits zero changes; a successful file is not applied twice. Exact identity and concurrent-upload safeguards TBD. **Proposed verification:** PostgreSQL integration/concurrency tests.

**NFR-004 — Forecast reproducibility:** For fixed dated stock-out inputs, verified daily coverage, on-hand and settings, use BR-007–BR-011 deterministically. Show the Singapore seven-day window, two-decimal display and full-precision calculation inputs; unobserved days yield unavailable rather than an imputed zero. Formula version/record-retention details TBD.

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

The eleven approved rules are in [OWNER_REQUIREMENTS_DECISIONS.md](OWNER_REQUIREMENTS_DECISIONS.md); proposed alternatives and edge cases are in [BUSINESS_RULES_AND_EDGE_CASES.md](BUSINESS_RULES_AND_EDGE_CASES.md). The SRS as a whole remains unapproved.

### Logical data concepts (proposed; not a schema design)

- **Product:** stable identifier, SKU, display name, current on-hand quantity, lifecycle state; exact fields and product maintenance actions TBD.
- **Stock movement:** trustworthy dated records of stock-outs are needed for the Singapore calendar window and demand proxy. Product, type, quantity, time and adjustment reason/difference are logical needs; schema, retention and correction method TBD.
- **Import batch:** sufficient successful-import identity/history is needed to reject an identical re-upload. Hashing, retention, concurrency safeguard and row-level validation records TBD.
- **Supplier/reorder settings:** product association, lead time, safety stock, and owner-approved additional reorder parameters.
- **Demand observation/forecast:** trustworthy per-product daily coverage evidence, including verified zero-demand days, is needed in addition to dated movements. Absence of records alone does not prove coverage. Coverage method, schema and retention TBD.
- **User/role:** account identity, active status and Manager/Staff role under the approved identity lifecycle.

PostgreSQL is approved. The logical entities above do not prescribe tables, ORM relationships, application architecture or hosting topology.

## 8. Assumptions and dependencies

- The fixed baseline and exclusions in the approved Charter and P1 record remain unchanged unless formally changed.
- Django 5.2 LTS + PostgreSQL is the approved backend. Exact deployment patch versions and configuration are later decisions.
- The project has one solo developer, 10–15 hours/week, deadline 27 November 2026 and SGD 0 cash budget. Schedule risk is high and tracked in Planning.
- Codex may assist development; generated changes require independent review and verification.
- BR-006 approves stock-outs as a demand proxy; availability, reliability and coverage of dated history are not established.
- A zero-cost PostgreSQL CI/staging solution may be available, but provider eligibility, quotas, connectivity and no-charge operation are unresolved.
- Existing PoC evidence is narrow and historical. Source PoC reports record 14/14 passed; PoC source reviewed there had 15 test methods; 16/16 is owner-reported without a matching artifact. No PoC result completes formal Testing.
- Jira and a separate `tory-inventory` GitHub repository are desired work-management changes, but neither is verified as configured. The current course repository remains the documented project repository until changed.

## 9. Open questions and requirement boundaries

See [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) for remaining decisions. Blocking issues include other role permissions, product lifecycle, CSV encoding/limits and duplicate identity, trustworthy observation coverage and dated history, inventory-on-order treatment, reorder-trigger semantics, safety-stock constraints, manual duplicate handling, numeric NFR targets and account provisioning.

### Explicit boundaries

- Product CSV import is excluded.
- Reorder recommendations do not place orders.
- No frontend framework, hosting provider, architecture, CI vendor or CD solution is selected here.
- BR-003 requires recording the adjustment difference/reason; BR-005 requires enough successful-import history to reject an identical re-upload; BR-006–BR-008 require trustworthy dated stock-outs and observation coverage. Their schema, retention, audit interface and recovery policy remain TBD. Export, backup and in-app user management are not approved features.
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
- [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md)
