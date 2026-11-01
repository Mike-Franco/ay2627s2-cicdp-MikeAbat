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
- One shared product catalogue per business with separate inventory records; inventory-specific selling prices and assigned-inventory access.
- Hosted staging demonstration and automated CI; automated CD is optional.

### 2.2 Exclusions

- Product catalog CSV import.
- Advanced MVP reorder settings such as minimum order quantity and supplier pack size (BR-014).
- A new frontend framework, hosting provider, architecture, deployment provider or detailed pipeline choice in this SRS.
- Microservices, barcode scanning, multi-warehouse management, purchasing automation, mobile application, notifications, unapproved integrations or expanded analytics.
- Forecasting methods beyond the approved seven-day moving average unless changed by formal change control.
- Production operation or production-readiness claims. The PoC is isolated feasibility material, not application code.

## 3. Stakeholders and owner-defined scenarios

No stakeholder interviews are claimed. These scenarios express owner-defined roles and goals. BR-021–BR-025 approve the stated Manager/Staff actions and assigned-inventory boundary; BR-026–BR-028 add Staff deactivation, constrained assignment and Manager product reactivation. Remaining mechanics and unlisted actions are **TBD** in [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md).

### Manager scenario — owner-defined role, proposed workflow

As a Tory Manager, I review assigned inventories and transaction history, record ordinary stock movements and physical-count adjustments, maintain products and the two approved reorder settings, import transaction CSV, manage Staff accounts as approved and inspect forecasts/reorder explanations. These actions are subject to the approved business and inventory scope; workflow details remain TBD.

### Staff scenario — owner-defined role, proposed workflow

As a Tory Staff user, I view assigned inventory and its transaction history, record ordinary stock-in/out, view supplier lead time and safety stock, and inspect forecasts/reorder suggestions. I cannot perform Manager-only actions. Invitation and authentication mechanics remain TBD.

### Project owner / solo developer

The same person owns the project and performs development, review, testing and demonstration. Codex is a guided coding aid; generated changes are independently reviewed and tested. This is a delivery constraint, not a product user role.

## 4. Requirement status and priority conventions

- **Confirmed baseline / owner rule:** Charter/P1 capabilities and [BR-001–BR-033](OWNER_REQUIREMENTS_DECISIONS.md) are approved individually. BR-012–BR-025 were supplied as supplementary owner evidence and documented on 1 November 2026; their original approval timestamp is not known. Other detailed criteria remain draft until SRS approval.
- **PROPOSED detail:** a specific interpretation added to make the baseline testable; it is not an approved business rule until accepted by the owner.
- **TBD:** information is absent and must be resolved or explicitly deferred with an owner and due stage.
- Priority: **Must** = needed to satisfy the fixed baseline; **Should** = proposed quality/detail that materially supports baseline completion; **TBD** = owner decides whether it is required.

## 5. Functional requirements

Each acceptance criterion is a proposed verification condition for the SRS. Where a detail is not approved, it becomes binding only after owner approval.

### FR-001 — Identify and select a product

- **Priority/status:** SKU and business uniqueness **APPROVED BR-001/BR-017**; shared business catalogue, inventory-specific price and soft deactivation **APPROVED BR-016/BR-018/BR-019**; Manager product actions **APPROVED BR-021/BR-028**. Other lifecycle details TBD.
- **Actor:** Manager or Staff, subject to approved permissions.
- **Preconditions:** User is authenticated and authorized; product exists and its lifecycle state permits the requested action under BR-028.
- **Main flow:** User selects a product using its approved identifier; Tory presents the product identity and current recorded stock.
- **Errors:** Unknown or unauthorized selection is rejected without mutation. Inactive products remain available to authorized lifecycle/history views; ordinary transactions against them are rejected (BR-019/BR-028).
- **Acceptance criteria:** Reject missing/blank-after-trim SKU and case collisions within a business; BR-001's active-product qualifier and BR-017's business-wide uniqueness leave inactive-SKU reuse unresolved. One business shares a product catalogue while inventory records and selling prices remain inventory-specific. Managers can create/edit/deactivate products (BR-021) and reactivate them (BR-028). Soft deactivation retains transaction history, requires prior resolution of remaining stock and blocks ordinary transactions. Exact resolution, price formatting and SKU rename/reuse remain TBD.

### FR-002 — View current inventory

- **Priority/status:** Assigned-inventory view and history **APPROVED BR-021/BR-022/BR-024**; list/search/filter detail **PROPOSED**.
- **Actor:** Manager and Staff, limited to assigned inventories within their own business (BR-022). BR-027 further constrains Manager assignment of Staff; it does not expand viewing scope.
- **Preconditions:** User is authenticated; products exist.
- **Main flow:** User requests an assigned inventory; Tory displays its product identity, recorded quantities and inventory-specific selling prices where included in the view. Both roles may view its transaction history.
- **Errors:** Unauthorized request is denied; unavailable database data is reported without presenting an unverified quantity as current.
- **Acceptance criteria:** Both roles can view assigned inventories and their transaction history; requests for unassigned or other-business inventories are denied (BR-021/BR-022/BR-024). Separate inventories may have different prices for the same catalogue product (BR-016/BR-018). Displayed quantity matches committed PostgreSQL state. History fields, price format and search/filter details remain TBD.

### FR-003 — Record stock-in

- **Priority/status:** Ordinary stock-in for both roles **APPROVED BR-021**; whole-number base units **APPROVED BR-020**; expiry per receiving batch **APPROVED BR-032**; other input fields TBD.
- **Actor:** Manager or Staff for an assigned inventory in their own business (BR-021/BR-022).
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits a stock-in quantity; Tory validates it, records the receiving batch's expiry when applicable, and updates stock atomically. Expiry is optional for products not tracked for expiry.
- **Errors:** Invalid/nonpositive quantity, unknown product or database failure is rejected without partial state. Manual duplicate-request handling remains TBD.
- **Acceptance criteria:** For valid positive whole-number base-unit quantity `q`, committed on-hand becomes prior quantity + `q`; fractional units are rejected (BR-020). Expiry is recorded per receiving batch for an expiry-tracked product and is optional for a non-expiry-tracked product (BR-032). An unassigned inventory or deactivated product rejects ordinary stock-in (BR-022/BR-028). Invalid input leaves quantity unchanged. Packaging conversion, exact batch fields and history retention remain TBD.

### FR-004 — Record stock-out

- **Priority/status:** Ordinary stock-out for both roles **APPROVED BR-021/BR-022**; whole-number base units and no-negative rule **APPROVED BR-020/BR-002**; demand proxy with quarantine/disposal exclusion **APPROVED BR-006/BR-031**; expired-batch quarantine and FEFO **APPROVED BR-029/BR-033**.
- **Actor:** Manager or Staff for an assigned inventory in their own business.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits an ordinary issue quantity and, if approved, a reason/type; Tory allocates eligible batches automatically in earliest-expiry order (FEFO), validates and commits the movement and quantity change atomically. Expired batches are quarantined and unavailable for ordinary issue.
- **Errors:** Reject a stock-out that would make on-hand negative without partial mutation. Other validation and manual duplicate handling remain TBD.
- **Acceptance criteria:** Reject fractional base-unit quantity and access to an unassigned inventory. An ordinary issue cannot use a quarantined expired batch or a deactivated product. Eligible batches are consumed by earliest expiry; insufficient eligible stock is rejected atomically even if quarantined stock remains. Committed ordinary stock-outs count as demand; quarantine and disposal do not (BR-031). Expiry boundary, no-expiry ordering and concurrency remain TBD.

### FR-005 — Record stock adjustment

- **Priority/status:** Manager-only, absolute whole-base-unit physical count, required reason and recorded difference **APPROVED BR-003/BR-020/BR-021**; reason format/retention TBD.
- **Actor:** Manager only; Staff cannot perform adjustment.
- **Preconditions:** User has adjustment permission; product exists; adjustment input is valid.
- **Main flow:** Manager enters physical count and reason; Tory sets on-hand to that count and records `new count − prior on-hand` atomically.
- **Errors:** Unauthorized, invalid or conflicting adjustment is rejected without partial update. Whether a particular adjustment is an ordinary transaction against a deactivated product requires classification under BR-028.
- **Acceptance criteria:** Prior `p`, whole-number base-unit physical count `c` yields on-hand `c` and recorded difference `c − p` with reason. Reject Staff, unassigned inventory, missing reason, fractional count and negative resulting count without partial mutation. Packaging conversion and retention TBD.

### FR-006 — Import stock transactions atomically from CSV

- **Priority/status:** Manager import permission **APPROVED BR-021**; `sku,change`, atomicity, empty/header-only rejection **APPROVED BR-004**; successful identical-file re-upload rejection **APPROVED BR-005**; whole-number base units **APPROVED BR-020**; batch/expiry compatibility with BR-028/BR-029/BR-032/BR-033 unresolved.
- **Actor:** Manager for an assigned inventory in the same business; Staff denied (BR-021/BR-022).
- **Preconditions:** Manager authorized for the assigned inventory; upload satisfies size/encoding constraints once decided; referenced products exist.
- **Main flow:** Tory parses and validates the entire stock-transaction batch, checks all rows against applicable inventory rules, and commits all rows as one logical batch.
- **Errors:** Invalid rows, malformed/empty/header-only uploads, insufficient stock, or identical re-upload after a successful import reject the whole batch without mutation.
- **Acceptance criteria:** Only a Manager may import for an assigned inventory in the same business; Staff and out-of-scope imports are denied. A valid new `sku,change` batch with whole-number base-unit changes commits all rows; any invalid row commits none. Empty/header-only files fail. A previously successful identical file cannot apply twice; a failed upload is not a successful prior import. Ordinary negative issues count as demand; quarantine and disposal do not. Ordinary transactions on deactivated products and issues using quarantined stock are disallowed. With separate inventories, how the upload selects its target inventory is TBD. How a two-column CSV identifies receiving batches/expiry, distinguishes disposal, and allocates negative changes by FEFO is also TBD; no CSV format change is approved. Duplicate identity, encoding, whitespace, row order/limits, concurrency and error format are also TBD.

### FR-007 — Authenticate users and distinguish Manager/Staff access

- **Priority/status:** Distinct roles and listed actions **APPROVED BR-021–BR-025**; Manager-only adjustment **APPROVED BR-003**; Manager Staff deactivation and constrained assignment **APPROVED BR-026/BR-027**; invitation/authentication mechanics TBD.
- **Actor:** Manager, Staff, and any proposed account administrator.
- **Preconditions:** Initial Manager provisioned during setup or Staff invited/created by a Manager (BR-023); exact mechanics TBD.
- **Main flow:** User authenticates; each protected operation is authorized using the approved role/action matrix and assigned-inventory/business boundary (BR-021/BR-022). Managers invite/create Staff (BR-023), may deactivate Staff while preserving attributable history (BR-026), and may assign Staff only to inventories they are authorized to manage in the same business (BR-027).
- **Errors:** Invalid credentials, inactive account or missing permission is denied; no protected data change occurs.
- **Acceptance criteria:** Both roles are limited to assigned inventories in their own business and may view authorised transaction history (BR-022/BR-024). The initial Manager is provisioned during setup; Managers can invite/create Staff (BR-023). A deactivated Staff account loses access without losing attribution for prior actions (BR-026). A Manager cannot assign Staff across a business boundary or outside that Manager's authorized inventories (BR-027). Invitation, authentication, password reset, reactivation, session revocation timing and unlisted administration remain TBD.

### FR-008 — Maintain per-product supplier and reorder settings

- **Priority/status:** Supplier lead time and safety stock only **APPROVED BR-010/BR-014**; nonnegative whole-number safety stock including zero **APPROVED BR-015**; Manager edit/Staff view-only **APPROVED BR-025**.
- **Actor:** Manager edits; Staff views settings for authorized inventories. Other settings are outside MVP (BR-014/BR-025).
- **Preconditions:** Product exists; user has approved configuration permission.
- **Main flow:** An authorized user views a product's supplier lead time and safety stock; an authorized Manager may update them. Tory validates and persists approved changes.
- **Errors:** Invalid values, missing product or unauthorized edit is rejected with no partial configuration update.
- **Acceptance criteria:** Each product's lead time is a positive whole number of calendar days; reject zero, negative or fractional days. Safety stock is a nonnegative whole number, including zero; reject negative or fractional values. Managers may edit; Staff may view but not edit; both remain within assigned inventories. Minimum order quantities, pack sizes and other advanced reorder settings are outside MVP. Values for one product do not alter another. Editing workflow and maximum values TBD.

### FR-009 — Supply eligible demand observations for forecasting

- **Priority/status:** Stock-out proxy, Singapore calendar window and reliable seven-day coverage **APPROVED BR-006–BR-008**; quarantine/disposal exclusion **APPROVED BR-031**; observation mechanism TBD.
- **Actor:** System processing stock movement data; user role sees result under FR-010.
- **Preconditions:** Dated committed movements and trustworthy observation coverage are available for each of the prior seven Asia/Singapore calendar days; how coverage is established remains TBD.
- **Main flow:** Count committed ordinary manual and negative-CSV stock-outs as demand; exclude stock-in, adjustments, quarantine, disposal and rejected-batch rows. Group by the previous seven complete Singapore calendar days, excluding current day. BR-031 qualifies BR-006 so quarantine/disposal are not mistaken for ordinary demand.
- **Errors:** Any unobserved/incomplete day makes the forecast unavailable. Absence of movement records alone does not establish a verified zero day.
- **Acceptance criteria:** A verified zero-demand day contributes zero; an unobserved day makes the seven-day input series unavailable. Boundary events are assigned by Asia/Singapore local calendar date. The proxy is not validated customer sales. Source record/coverage design and retention remain TBD.

### FR-010 — Calculate and display an explainable seven-day moving average

- **Priority/status:** Seven-day average confirmed; window, coverage and precision **APPROVED BR-007–BR-009**; both roles may view for assigned inventories **APPROVED BR-021/BR-022**; quarantine/disposal exclusion **APPROVED BR-031**.
- **Actor:** Manager and Staff for assigned inventories within their own business.
- **Preconditions:** Seven previous complete, reliably observed Asia/Singapore days exist for the product.
- **Main flow:** Tory calculates the moving-average value from the approved seven-day window and displays the result with the dates and daily inputs/assumptions needed to explain it.
- **Errors:** Missing or incomplete coverage on any day makes forecast unavailable; do not infer zero from no records.
- **Acceptance criteria:** Display previous seven dates and daily stock-out proxy inputs. Average is total / 7, displayed to two decimal places; retain full precision for downstream calculations. For verified `[1,0,1,0,1,0,0]`, display `0.43`; if any day lacks coverage, show unavailable. See [worked examples](BUSINESS_RULES_AND_EDGE_CASES.md#edge-case-acceptance-examples-to-approve).

### FR-011 — Produce an explainable reorder recommendation

- **Priority/status:** Formula and informational nature **APPROVED BR-011**; threshold alert, pending-delivery exclusion, settings scope and safety-stock validation **APPROVED BR-012–BR-015**; both roles may view for assigned inventories **APPROVED BR-021/BR-022**; available-to-issue quantity excluding quarantine **APPROVED BR-030**.
- **Actor:** Manager and Staff for assigned inventories within their own business.
- **Preconditions:** FR-010 result and approved product supplier/reorder settings are available.
- **Main flow:** Compute reorder point = full-precision average daily demand × positive whole calendar-day lead time + nonnegative whole-number safety stock. Use available-to-issue quantity, excluding quarantined stock and ignoring incoming/pending supplier deliveries, for `max(0, ceil(reorder point − available-to-issue quantity))` (BR-011/BR-013/BR-030). Trigger a reorder alert when available-to-issue quantity is at or below the reorder point (BR-012). Display the alert and suggested quantity separately; create no purchase order.
- **Errors:** Missing forecast/settings or invalid values yield an unavailable recommendation with a reason; no purchase order is created.
- **Acceptance criteria:** For verified demand total `3` over seven days, lead time `7`, valid safety stock `0`, available-to-issue quantity `0`: full-precision average `3/7`, reorder point `3`, suggested quantity `3`; displayed `0.43` must not be multiplied back. At available-to-issue quantity equal to reorder point, show the alert even when suggested quantity is `0` (BR-012). Pending deliveries and quarantined stock do not increase the stock input (BR-013/BR-030). Missing coverage yields no numeric recommendation. Advanced settings and automatic purchasing remain outside MVP; exact alert presentation when inputs are unavailable remains TBD.

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

**NFR-001 — Authorization:** Every protected operation shall enforce BR-021–BR-025 role permissions and assigned-inventory/same-business access at the server side; denial shall occur before any protected mutation. BR-026 revokes deactivated Staff access while preserving attribution; BR-027 constrains Manager Staff assignment to currently authorized inventories in the same business. **Proposed verification:** positive and negative automated tests for each approved matrix cell, including cross-business and out-of-scope requests and assignments.

**NFR-002 — Credential and secret handling:** Credentials, session secrets and database passwords shall not be committed to source or returned in application errors; staging shall use transport encryption where the selected provider supports it. Authentication/session details and security review criteria are **TBD** pending approval.

### Correctness and data integrity

**NFR-003 — Transaction integrity:** Stock quantities are whole-number base units (BR-020); no accepted stock-out makes on-hand negative. Manager adjustment sets physical count and records difference/reason atomically. Soft product deactivation preserves history (BR-019), and no ordinary transaction applies to a deactivated product (BR-028); expired batches are quarantined and unavailable for ordinary issue (BR-029); receiving-batch expiry follows BR-032; eligible issue allocation follows FEFO (BR-033). A rejected CSV batch, including empty/header-only or previously successful identical upload, commits zero changes; a successful file is not applied twice. Exact identity, batch/CSV compatibility, expiry boundary and concurrent-update safeguards TBD. **Proposed verification:** PostgreSQL integration/concurrency tests.

**NFR-004 — Forecast reproducibility:** For fixed dated ordinary stock-out inputs, verified daily coverage, available-to-issue quantity and approved settings, use BR-007–BR-015 and BR-030–BR-031 deterministically. Quarantine/disposal are excluded from demand; quarantined stock and pending deliveries are excluded from the reorder stock input. Show the Singapore seven-day window, two-decimal display, full-precision inputs and alert separately from suggested quantity; unobserved days yield unavailable rather than an imputed zero. Formula version, movement classification and record-retention details TBD.

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

The individually approved BR-001–BR-033 are in [OWNER_REQUIREMENTS_DECISIONS.md](OWNER_REQUIREMENTS_DECISIONS.md), including the supplementary owner-provided BR-012–BR-025 record; proposed alternatives and edge cases are in [BUSINESS_RULES_AND_EDGE_CASES.md](BUSINESS_RULES_AND_EDGE_CASES.md). The SRS as a whole remains unapproved.

### Logical data concepts (proposed; not a schema design)

- **Business/catalogue product:** one shared product catalogue per business, with case-insensitive business-scoped SKU, stable identifier, display name and soft lifecycle state (BR-016–BR-019). BR-001's active-only uniqueness and BR-017's business-wide wording need a SKU reuse decision. Managers create/edit/deactivate (BR-021) and reactivate (BR-028); remaining-stock resolution workflow TBD.
- **Inventory:** separate inventory records and inventory-specific selling prices (BR-016/BR-018), with access limited to assignments in the same business (BR-022). Price format, assignment lifecycle and inventory identity TBD.
- **Receiving batch:** per-batch expiry when tracked, optional expiry for non-expiry-tracked products; eligibility, quarantine and FEFO order follow BR-029/BR-032/BR-033. Expiration boundary, no-expiry ordering and physical representation remain TBD.
- **Stock movement/history:** trustworthy dated records of ordinary stock-outs, quarantine and disposal are needed to distinguish demand from excluded activity. Both roles may view history for authorized inventories (BR-024); product deactivation retains it (BR-019). Product, inventory, batch, type, whole-base-unit quantity, time and adjustment reason/difference are logical needs; schema, view fields, retention and correction method TBD.
- **Import batch:** sufficient successful-import identity/history is needed to reject an identical re-upload. Hashing, retention, concurrency safeguard and row-level validation records TBD.
- **Supplier/reorder settings:** per-product positive whole-calendar-day lead time and nonnegative whole-number safety stock, including zero; these are the only MVP reorder settings (BR-010/BR-014/BR-015). Managers edit and Staff view within their authorized scope (BR-025).
- **Demand observation/forecast:** trustworthy per-product daily coverage evidence, including verified zero-demand days, is needed in addition to dated movements. Absence of records alone does not prove coverage. Coverage method, schema and retention TBD.
- **User/role and inventory assignment:** initial Manager provisioned during setup; Managers invite/create Staff (BR-023). Account identity, active status, attributable history, Manager/Staff role, business boundary and assignments support BR-021–BR-027. Invitation/authentication mechanics, reactivation, session timing and assignment lifecycle remain TBD.

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

See [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) for remaining decisions. Blocking issues include the BR-001/BR-017 inactive-SKU reuse interpretation, price format, invitation/authentication mechanics, account reactivation, remaining-stock resolution before product deactivation, expiration boundaries, no-expiry batch ordering, CSV-versus-batch conflicts, quarantine implementation, concurrency, CSV encoding/limits and duplicate identity, trustworthy observation coverage and dated history, alert presentation when inputs are unavailable, packaging conversion, manual duplicate handling and numeric NFR targets. BR-012–BR-015 and BR-021–BR-025 resolve the former trigger, pending-delivery, safety-stock, advanced-settings and role-permission TBDs as stated.

### Explicit boundaries

- Product CSV import is excluded.
- Reorder recommendations do not place orders.
- No frontend framework, hosting provider, architecture, CI vendor or CD solution is selected here.
- BR-003 requires recording the adjustment difference/reason; BR-005 requires enough successful-import history to reject an identical re-upload; BR-006–BR-008 and BR-031 require trustworthy dated movements, classification and observation coverage. BR-023 approves initial Manager setup and Manager Staff invitation/creation; BR-026–BR-027 approve Manager Staff deactivation and constrained assignment. Other account administration remains TBD. Schema, retention, audit interface and recovery policy remain TBD. Export and backup are not approved features.
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
