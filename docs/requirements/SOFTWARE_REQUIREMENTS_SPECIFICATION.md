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

No stakeholder interviews are claimed. These scenarios express owner-defined roles and goals. BR-021–BR-025 approve the stated Manager/Staff actions and assigned-inventory boundary; BR-026–BR-028 add Staff deactivation, constrained assignment and Manager product reactivation. BR-042–BR-045 approve email/password authentication, Staff email invitations, reset links and session/security controls. Remaining mechanics and unlisted actions are **TBD** in [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md).

### Manager scenario — owner-defined role, proposed workflow

As a Tory Manager, I review assigned inventories and transaction history, record ordinary stock movements and physical-count adjustments, maintain products and the two approved reorder settings, import transaction CSV, manage Staff accounts as approved and inspect forecasts/reorder explanations. These actions are subject to the approved business and inventory scope; workflow details remain TBD.

### Staff scenario — owner-defined role, proposed workflow

As a Tory Staff user, I set my own password after a Manager's email invitation, then use email/password sign-in to view assigned inventory and its transaction history, record ordinary stock-in/out, view supplier lead time and safety stock, and inspect forecasts/reorder suggestions. I cannot perform Manager-only actions. Email delivery and token/session timing remain TBD.

### Project owner / solo developer

The same person owns the project and performs development, review, testing and demonstration. Codex is a guided coding aid; generated changes are independently reviewed and tested. This is a delivery constraint, not a product user role.

## 4. Requirement status and priority conventions

- **Confirmed baseline / owner rule:** Charter/P1 capabilities and [BR-001–BR-045](OWNER_REQUIREMENTS_DECISIONS.md) are approved individually. BR-012–BR-025 were supplied as supplementary owner evidence and documented on 1 November 2026; their original approval timestamp is not known. Other detailed criteria remain draft until SRS approval.
- **PROPOSED detail:** a specific interpretation added to make the baseline testable; it is not an approved business rule until accepted by the owner.
- **TBD:** information is absent and must be resolved or explicitly deferred with an owner and due stage.
- Priority: **Must** = needed to satisfy the fixed baseline; **Should** = proposed quality/detail that materially supports baseline completion; **TBD** = owner decides whether it is required.

## 5. Functional requirements

Each acceptance criterion is a proposed verification condition for the SRS. Where a detail is not approved, it becomes binding only after owner approval.

### FR-001 — Identify and select a product

- **Priority/status:** SKU and business uniqueness plus permanent original-product reservation **APPROVED BR-001/BR-017/BR-038**; shared business catalogue, inventory-specific price and soft deactivation **APPROVED BR-016/BR-018/BR-019**; Manager product actions and all-inventory zero-stock deactivation guard **APPROVED BR-021/BR-028/BR-040**. Other lifecycle details TBD.
- **Actor:** Manager or Staff, subject to approved permissions.
- **Preconditions:** User is authenticated and authorized; product exists and its lifecycle state permits the requested action under BR-028.
- **Main flow:** User selects a product using its approved identifier; Tory presents the product identity and current recorded stock.
- **Errors:** Unknown or unauthorized selection is rejected without mutation. Inactive products remain available to authorized lifecycle/history views; ordinary transactions against them are rejected (BR-019/BR-028).
- **Acceptance criteria:** Reject missing/blank-after-trim SKU and case collisions within a business. A SKU remains reserved to its original product after deactivation; reject reuse for a different product even when the original is inactive (BR-038). One business shares a product catalogue while inventory records and selling prices remain inventory-specific. Managers can create/edit/deactivate products (BR-021) and reactivate them (BR-028). Before soft deactivation, physical stock must be zero in **every** inventory of the business, including quarantined units (BR-040); history remains attributable and ordinary transactions are blocked afterward. Exact stock-resolution workflow, SKU renaming/alias behavior and price formatting remain TBD.

### FR-002 — View current inventory

- **Priority/status:** Assigned-inventory view and history **APPROVED BR-021/BR-022/BR-024**; list/search/filter detail **PROPOSED**.
- **Actor:** Manager and Staff, limited to assigned inventories within their own business (BR-022). BR-027 further constrains Manager assignment of Staff; it does not expand viewing scope.
- **Preconditions:** User is authenticated; products exist.
- **Main flow:** User requests an assigned inventory; Tory displays its product identity, recorded quantities and inventory-specific selling prices where included in the view. Both roles may view its transaction history.
- **Errors:** Unauthorized request is denied; unavailable database data is reported without presenting an unverified quantity as current.
- **Acceptance criteria:** Both roles can view assigned inventories and their transaction history; requests for unassigned or other-business inventories are denied (BR-021/BR-022/BR-024). Separate inventories may have different prices for the same catalogue product (BR-016/BR-018). Displayed physical on-hand matches committed stock; available-to-issue and quarantine views apply approved G-02 expiry eligibility from Singapore midnight even before a stored transition. History view fields, price format and search/filter details remain TBD.

### FR-003 — Record stock-in

- **Priority/status:** Ordinary stock-in for both roles **APPROVED BR-021**; whole-number base units **APPROVED BR-020**; expiry per receiving batch **APPROVED BR-032**; manual receiving with batch/expiry details for expiry-tracked products **APPROVED BR-036**; other input fields TBD.
- **Actor:** Manager or Staff for an assigned inventory in their own business (BR-021/BR-022).
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User manually receives expiry-tracked stock with batch/expiry details; for a product not tracked for expiry, expiry is optional. Tory validates the whole-number stock-in and updates stock atomically.
- **Errors:** Invalid/nonpositive quantity, unknown product or database failure is rejected without partial state. Manual duplicate-request handling remains TBD.
- **Acceptance criteria:** For valid positive whole-number base-unit quantity `q`, committed on-hand becomes prior quantity + `q`; fractional units are rejected (BR-020). An expiry-tracked product is received manually with batch/expiry details (BR-032/BR-036); positive CSV rows for it are rejected under FR-006. Expiry is optional for a non-expiry-tracked product. Committed receipt order must be distinguishable by the approved G-01 receiving sequence, with stable batch ID as final tie-breaker. An unassigned inventory or deactivated product rejects ordinary stock-in (BR-022/BR-028). Invalid input leaves quantity unchanged. Packaging conversion, exact sequence/identifier representation and history retention remain TBD.

### FR-004 — Record stock-out

- **Priority/status:** Ordinary stock-out for both roles **APPROVED BR-021/BR-022**; whole-number base units and no-negative rule **APPROVED BR-020/BR-002**; demand proxy with quarantine/disposal exclusion **APPROVED BR-006/BR-031**; expiry eligibility, FEFO then undated FIFO **APPROVED BR-029/BR-033–BR-035**; Manager-only reasoned disposal **APPROVED BR-037**.
- **Actor:** Manager or Staff for an assigned inventory in their own business.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits an ordinary issue quantity; Tory allocates eligible dated batches by earliest expiry (FEFO), followed by eligible undated batches in receiving order (FIFO), and commits atomically. An expiry-dated batch is unavailable for ordinary issue from 00:00 on its expiry date in Asia/Singapore (BR-034/BR-035). Separately, only a Manager may dispose of quarantined units with a required reason and attributable history (BR-037).
- **Errors:** Reject a stock-out that would make on-hand negative without partial mutation. Other validation and manual duplicate handling remain TBD.
- **Acceptance criteria:** Reject fractional base-unit quantity and access to an unassigned inventory. An ordinary issue cannot use a deactivated product or a batch expired at Singapore local midnight on its expiry date, even if stored quarantine transition is delayed. Within a product/inventory, consume eligible dated batches by `(expiry date, committed receiving sequence, stable batch ID)`, then eligible undated batches by `(committed receiving sequence, stable batch ID)` (G-01 approved Option A; BR-033/BR-034 preserved). Insufficient eligible stock is rejected atomically even if quarantined physical stock remains. Display quarantine and exclude expired remaining units from available-to-issue immediately while physical on-hand is unchanged (G-02 approved Option A). Only Managers may dispose of quarantined units with reason and attributable, nondemand history (BR-037). **Acceptance examples:** equal-expiry B-20 sequence 41 precedes B-10 sequence 42; a dated batch precedes undated U-2 sequence 7 then U-1 sequence 8. At 8 November 2026 00:00 Asia/Singapore, a five-unit expiring batch has physical 5, available 0 and quarantine 5; a reasoned Manager disposal of 2 changes physical/quarantine to 3/3 without demand, while Staff or reasonless attempts fail. Exact batch-ID comparison convention, quarantine evidence-delay bound, reason format and G-11 concurrency mechanics remain TBD.

### FR-005 — Record stock adjustment

- **Priority/status:** Manager-only, absolute whole-base-unit physical count, required reason and recorded difference **APPROVED BR-003/BR-020/BR-021**; reason format/retention TBD.
- **Actor:** Manager only; Staff cannot perform adjustment.
- **Preconditions:** User has adjustment permission; product exists; adjustment input is valid.
- **Main flow:** Manager enters physical count and reason; Tory sets on-hand to that count and records `new count − prior on-hand` atomically.
- **Errors:** Unauthorized, invalid or conflicting adjustment is rejected without partial update. Whether a particular adjustment is an ordinary transaction against a deactivated product requires classification under BR-028.
- **Acceptance criteria:** Prior `p`, whole-number base-unit physical count `c` yields on-hand `c` and recorded difference `c − p` with reason. Reject Staff, unassigned inventory, missing reason, fractional count and negative resulting count without partial mutation. Packaging conversion and retention TBD.

### FR-006 — Import stock transactions atomically from CSV

- **Priority/status:** Manager import permission **APPROVED BR-021**; `sku,change`, atomicity, empty/header-only rejection **APPROVED BR-004**; successful same-inventory byte-identical re-upload rejection **APPROVED BR-005/BR-041**; whole-number base units **APPROVED BR-020**; before-upload inventory selection, all-row scope, expiry-tracked positive-row rejection and negative batch allocation **APPROVED BR-036/BR-039**.
- **Actor:** Manager for an assigned inventory in the same business; Staff denied (BR-021/BR-022).
- **Preconditions:** Before upload, Manager explicitly selects one inventory they are authorized to access (BR-039); upload satisfies size/encoding constraints once decided; referenced products exist.
- **Main flow:** Tory parses and validates the entire stock-transaction batch, checks all rows against applicable inventory rules, and commits all rows as one logical batch.
- **Errors:** Invalid rows, malformed/empty/header-only uploads, insufficient stock, or identical re-upload after a successful import reject the whole batch without mutation.
- **Acceptance criteria:** Before upload, a Manager selects one authorized inventory; every `sku,change` row applies to that inventory (BR-039). Staff and out-of-scope imports are denied. The header remains `sku,change`. Reject a positive row for an expiry-tracked product and roll back the entire CSV batch, including otherwise valid rows; receive that product manually with batch/expiry details (BR-036). Valid negative rows use approved G-01 ordering: eligible dated batches by expiry, committed receiving sequence and stable batch ID, then undated batches by sequence and stable ID; expired units cannot satisfy them even if transition evidence is late (G-02). Empty/header-only files fail; any invalid row commits none, including stock, allocation, demand and committed audit events from preceding valid rows (G-09). Successful row movements link to their import identity without double-counted demand. Reject exact file bytes previously imported successfully for the **same inventory**; a failed upload is not a successful prior import, and a semantically equivalent but byte-different file is not identical under BR-041. Import history in another inventory alone does not trigger this duplicate rule. Ordinary negative issues count as demand; quarantine and disposal do not. Ordinary transactions on deactivated products are disallowed. Non-expiry-tracked positive-row batch handling, byte-comparison/retention mechanism, encoding, whitespace, row order/limits, batch-ID comparison convention, concurrency and error format remain TBD.

### FR-007 — Authenticate users and distinguish Manager/Staff access

- **Priority/status:** Distinct roles and listed actions **APPROVED BR-021–BR-025**; Manager-only adjustment **APPROVED BR-003**; Manager Staff deactivation and constrained assignment **APPROVED BR-026/BR-027**; Manager-only quarantined-unit disposal **APPROVED BR-037**; Django email/password login, secure Staff email invitations, single-use time-limited reset links and session/security controls **APPROVED BR-042–BR-045**. Delivery and timing details TBD.
- **Actor:** Manager, Staff, and any proposed account administrator.
- **Preconditions:** Initial Manager provisioned during setup or Staff securely invited by a Manager through email (BR-023/BR-043); invitee sets their own password. Email delivery and initial Manager credential setup TBD.
- **Main flow:** Manager or Staff signs in with email and password through Django-based authentication (BR-042). Server-managed session access uses HttpOnly cookies, HTTPS and CSRF protection (BR-045). Protected operations enforce the approved role/action matrix and assigned-inventory/business boundary (BR-021/BR-022). Managers invite Staff by email without choosing their passwords (BR-043), may deactivate Staff while preserving attributable history (BR-026), and may assign Staff only to inventories they are authorized to manage in the same business (BR-027). Users may request a time-limited, single-use password reset link (BR-044). Before CSV upload, a Manager explicitly selects an authorized inventory (BR-039).
- **Errors:** Wrong password, inactive account, expired/reused reset link, invalid invitation, missing permission or failed CSRF validation does not grant protected access or mutate protected data. Exact error presentation remains TBD.
- **Acceptance criteria:** Correct email/password credentials establish a server-managed session for the appropriate active role; wrong passwords do not (BR-042/BR-045). A Manager can invite Staff by email, and the invitee sets their own password without the Manager knowing it; assignments remain within the Manager's authorized same-business inventories (BR-043/BR-027). **Proposed invitation verification:** expired or reused invitation tokens cannot create a second account or set a password again; token expiry duration and mechanics remain TBD. A reset link works once within its validity window and fails after expiry or reuse (BR-044); duration remains TBD. Logout invalidates the current server session for subsequent protected requests (**proposed verification**); deactivated accounts cannot access protected operations even with a previously issued session, while prior history remains attributable (BR-026). Protected requests without valid CSRF proof are denied; valid authenticated requests still require assigned-inventory authorization (BR-022/BR-045). Staff cannot record quarantined-unit disposal (BR-037). Email delivery, session timeout, rate limiting, account reactivation, cookie settings beyond HttpOnly and unlisted administration remain TBD.

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
- **Main flow:** Count committed ordinary manual and negative-CSV stock-outs as demand; exclude stock-in, adjustments, quarantine, Manager-recorded disposal and rejected-batch rows. Group by the previous seven complete Singapore calendar days, excluding current day. BR-031/BR-037 keep quarantine and disposal out of ordinary demand.
- **Errors:** Any unobserved/incomplete day makes the forecast unavailable. Absence of movement records alone does not establish a verified zero day.
- **Acceptance criteria:** A verified zero-demand day contributes zero; an unobserved day makes the seven-day input series unavailable. Boundary events are assigned by Asia/Singapore local calendar date. G-09 approved classification keeps receipt, adjustment, quarantine and disposal out of ordinary demand and avoids double counting linked CSV rows or multi-batch issues. The proxy is not validated customer sales. Source record/coverage design and retention remain TBD.

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
- **Acceptance criteria:** For verified demand total `3` over seven days, lead time `7`, valid safety stock `0`, available-to-issue quantity `0`: full-precision average `3/7`, reorder point `3`, suggested quantity `3`; displayed `0.43` must not be multiplied back. At available-to-issue quantity equal to reorder point, show the alert even when suggested quantity is `0` (BR-012). Pending deliveries and quarantined stock do not increase the stock input (BR-013/BR-030). At Singapore midnight on an expiry date, the stock input excludes expired remaining units even if transition evidence is delayed (G-02 approved Option A). Missing coverage yields no numeric recommendation. Advanced settings and automatic purchasing remain outside MVP; exact alert presentation when inputs are unavailable remains TBD.

### FR-012 — Provide controlled validation feedback

- **Priority/status:** **PROPOSED detail** supporting movement and CSV baseline.
- **Actor:** Authorized user.
- **Preconditions:** User submits a transaction or batch.
- **Main flow:** Tory reports success or identifies the relevant row/field and reason for rejection without exposing secrets or internal stack traces.
- **Errors:** Error-reporting failure must not weaken atomicity or authorization.
- **Acceptance criteria (proposed):** Invalid movement feedback identifies a correctable input; CSV feedback identifies rejected row(s) per approved policy; rejected batches leave data unchanged. Exact message format and whether all errors or first error are shown are owner decisions.

## 6. Nonfunctional requirements

The six owner-approved nonfunctional decisions dated 1 November 2026 map to NFR-003, NFR-006 and NFR-008–NFR-011 below and are recorded in [OWNER_REQUIREMENTS_DECISIONS.md](OWNER_REQUIREMENTS_DECISIONS.md#owner-approved-nonfunctional-decisions--1-november-2026). Measurement parameters and infrastructure details marked **TBD** are not approved. None is a measured result; formal execution evidence belongs in later Waterfall stages.

### Security

**NFR-001 — Authorization:** Every protected operation shall enforce BR-021–BR-025 role permissions and assigned-inventory/same-business access at the server side; denial shall occur before any protected mutation. BR-026 revokes deactivated Staff access while preserving attribution; BR-027 constrains Manager Staff assignment to currently authorized inventories in the same business. BR-037 limits quarantined-unit disposal to Managers. BR-039 requires an explicitly selected authorized inventory before CSV upload. BR-042/BR-045 require authenticated server-managed sessions and CSRF protection; an authenticated session never expands inventory scope. **Proposed verification:** positive and negative tests for role cells, deactivated sessions, invalid CSRF proof, cross-business/out-of-scope requests, assignments and CSV selections.

**NFR-002 — Credential and secret handling:** Django-based email/password authentication (BR-042), invitees choosing their own passwords after secure Manager email invitation (BR-043), time-limited single-use reset links (BR-044), and server-managed sessions with HttpOnly cookies, HTTPS and CSRF protection (BR-045) are approved. Credentials, session secrets and database passwords shall not be committed to source or returned in application errors. **Proposed verification:** wrong passwords, expired/reused invitation and reset links, logout, deactivated sessions, HttpOnly cookie attribute, HTTPS-only protected traffic and CSRF rejection/acceptance. Email delivery, token expiry duration, session timeout, authentication rate limiting, additional cookie attributes and exact security review criteria remain TBD.

### Correctness and data integrity

**NFR-003 — Transaction integrity and audit:** **Owner-approved 1 November 2026:** every inventory transaction is atomic; an accepted operation cannot leave a negative available-to-issue balance or allocate the same batch units twice under concurrency. An invalid CSV import commits no rows, and byte-identical previously successful imports for the same inventory are rejected per BR-041. The separate G-01/G-02/G-09 Option A approvals of 1 November fix deterministic batch ties, expiry-derived eligibility with system-attributed transition evidence, and one logical event per committed inventory mutation linked to batches and source operation/import. Each event identifies actor or system, business, inventory, product, action, timestamp, affected batches, relevant quantity before/after or change, classification and required reason; distinguish physical, available and quarantine quantities where relevant. Commit stock/state and evidence together; rejected operations have no committed inventory-mutation event. Link successful CSV row movements to import identity without double-counting demand; preserve actor/product attribution after deactivation. Existing BR-002–BR-005, BR-020, BR-028–BR-041 remain binding. **Proposed verification:** PostgreSQL integration/concurrency cases cover equal-expiry ordering, no double allocation, Singapore midnight expiry with delayed evidence, disposal, multi-batch event, invalid CSV full stock/audit rollback and retained attribution. **Open:** G-02 maximum evidence-recording delay; G-09 separate rejected-attempt logging; transaction/locking design, batch-ID comparison convention, audit schema/retention/correction, other holds and workload. No formal test is claimed.

**NFR-004 — Forecast reproducibility:** For fixed dated ordinary stock-out inputs, verified daily coverage, available-to-issue quantity and approved settings, use BR-007–BR-015 and BR-030–BR-031/BR-037 deterministically. G-09 approved classification counts each ordinary issue once even when it spans batches or CSV-linked rows; quarantine and attributable disposal are excluded from demand. G-02 excludes expired remaining units from reorder available-to-issue at Singapore midnight even if transition evidence is delayed; pending deliveries remain excluded. Show the Singapore seven-day window, two-decimal display, full-precision inputs and alert separately from suggested quantity; unobserved days yield unavailable rather than an imputed zero. Formula version, coverage method and record-retention details TBD.

### Usability

**NFR-005 — Understandable outcomes:** Users shall be able to distinguish stock-in, stock-out and adjustment outcomes and understand why a CSV batch or forecast is rejected/unavailable. Exact interface and usability testing method are **TBD**; no frontend is selected.

### Performance

**NFR-006 — Response time:** **Owner-approved 1 November 2026:** p95 response time ≤ 2 seconds for normal application requests and ≤ 3 seconds for forecast requests. **Proposed verification:** measure request-response durations for an approved normal-request workload and forecast workload, compute p95 for each, and compare separately to the two thresholds. Workload mix, dataset size, concurrency, test environment, request classification, measurement boundaries (including network and cold starts) and run length remain TBD. No performance result is claimed.

### Maintainability

**NFR-007 — Change and schema management:** Database schema changes shall be versioned and reproducible from source-controlled migrations. Generated code must be independently reviewed by the solo developer. Review checklist and supported-version policy are **TBD** for Design.

### Reliability

**NFR-008 — Failure handling and recovery:** **Owner-approved 1 November 2026:** take daily PostgreSQL backups and complete at least one successful restore test before Deployment. Failed inventory transactions shall leave no partial stock or audit changes (NFR-003). **Proposed verification:** retain dated backup evidence for each required day, restore at least one backup into an isolated PostgreSQL environment, verify representative inventory and audit records, and record source revision, backup time, restore result and environment before Deployment gate review. Backup destination, retention, recovery point/time objectives, restore environment/procedure and zero-cost backup storage feasibility remain TBD. No backup or restore result is claimed.

### Deployment

**NFR-009 — Staging and cost constraint:** **Owner-approved 1 November 2026:** provide an HTTPS-hosted Django/PostgreSQL staging demonstration within the S$0 cash-budget target, consistent with the Planning SGD 0 ceiling. BR-045 requires HTTPS; BR-043/BR-044 require invitation/reset email delivery; NFR-008 requires daily backups and a restore test. **Proposed verification:** demonstrate the deployed Django app over HTTPS backed by PostgreSQL, confirm database connectivity and invitation/reset email delivery, and record provider eligibility, quotas, payment/overage safeguards and backup-storage capacity with evidence of no cash charge. Hosting/database/email/backup provider choices and zero-cost feasibility remain TBD. No provider or feasibility result is claimed.

**NFR-010 — Automated CI:** **Owner-approved 1 November 2026:** GitHub Actions shall run Django automated tests against PostgreSQL for pull requests; a failed test shall fail the CI check. **Proposed verification:** submit a pull request with passing tests and observe a successful GitHub Actions check; in a controlled failing-test case, observe a failed check, with PostgreSQL used in both runs. Approved dependencies/migrations and exact job details belong to later stages. Workflow configuration, full test gate set, repository/quota and no-cost operation remain TBD; the existing documentation CI workflow is not application-test evidence. CD remains optional.

### Testability

**NFR-011 — Requirement verification:** Every approved Must requirement shall map to one or more proposed/approved acceptance tests in the traceability matrix; each formal result shall be recorded with source revision and environment. **Owner-approved audit decisions, 1 November 2026:** records shall be testable and traceable to actor or system identity, business, inventory, product, action, timestamp, affected batches/source operation, relevant quantity before/after or change, classification and applicable reason (G-09 approved Option A). Expiry-transition evidence also carries effective and actual recording times (G-02). Proposed verification links representative committed events to stock/state changes and checks attribution after deactivation. Rejected operations leave no committed mutation event; separate rejected-attempt logging is undecided. Audit schema, retention, correction policy and G-02 evidence-delay limit remain TBD. No test result is claimed here.

## 7. Business rules and data requirements

The individually approved BR-001–BR-045 are in [OWNER_REQUIREMENTS_DECISIONS.md](OWNER_REQUIREMENTS_DECISIONS.md), including the supplementary owner-provided BR-012–BR-025 record; proposed alternatives and edge cases are in [BUSINESS_RULES_AND_EDGE_CASES.md](BUSINESS_RULES_AND_EDGE_CASES.md). The SRS as a whole remains unapproved.

### Logical data concepts (proposed; not a schema design)

- **Business/catalogue product:** one shared product catalogue per business, with case-insensitive business-scoped SKU, stable identifier, display name and soft lifecycle state (BR-016–BR-019). Each SKU stays reserved to its original product, including after deactivation (BR-038). Managers create/edit/deactivate (BR-021) and reactivate (BR-028); deactivation requires zero physical stock, including quarantined units, in every inventory of that business (BR-040). SKU rename/alias and remaining-stock resolution workflow TBD.
- **Inventory:** separate inventory records and inventory-specific selling prices (BR-016/BR-018), with access limited to assignments in the same business (BR-022). Price format, assignment lifecycle and inventory identity TBD.
- **Receiving batch:** per-batch expiry when tracked, optional expiry for non-expiry-tracked products; expiry-tracked receipts are manual (BR-032/BR-036). Eligibility excludes dated stock from Singapore local 00:00 on its expiry date independently of stored status (G-02). Eligible dated batches follow expiry, committed receiving sequence and stable batch ID; undated batches follow sequence and stable ID afterward (G-01). Physical on-hand persists until authorised movement; displayed quarantine reflects expired remaining units immediately. Sequence storage, ID comparison, transition mechanism and maximum evidence-recording delay remain TBD.
- **Stock movement/audit history:** one logical event per committed inventory mutation linked to affected batches and source operation/import (G-09 approved Option A), with actor/system, business/inventory/product, action, timestamp, relevant quantities/classification and required reason. Expiry transition has effective and recorded times and system attribution (G-02). Stock/state and committed evidence are atomic; rejected operations create no committed mutation event. Both roles may view authorized history (BR-024); deactivation preserves attribution (BR-019/BR-026). Separate rejected-attempt logging, schema, view fields, retention and correction remain TBD.
- **Import batch:** identify successful imports by selected inventory and exact file bytes; reject a prior byte-identical success only within that inventory (BR-041). Every row applies to the Manager's explicitly selected authorized inventory (BR-039). Byte comparison/retention implementation, concurrency safeguard and row-level validation records TBD.
- **Supplier/reorder settings:** per-product positive whole-calendar-day lead time and nonnegative whole-number safety stock, including zero; these are the only MVP reorder settings (BR-010/BR-014/BR-015). Managers edit and Staff view within their authorized scope (BR-025).
- **Demand observation/forecast:** trustworthy per-product daily coverage evidence, including verified zero-demand days, is needed in addition to dated movements. Absence of records alone does not prove coverage. Coverage method, schema and retention TBD.
- **User/role and inventory assignment:** initial Manager provisioned during setup; Managers securely invite Staff by email and invitees set their own passwords (BR-023/BR-043). Django email/password identity, active status, attributable history, Manager/Staff role, business boundary and assignments support BR-021–BR-027/BR-042. Time-limited single-use reset links (BR-044), server-managed sessions, HttpOnly cookies, HTTPS and CSRF protection (BR-045) are logical needs, not a prescribed schema. Email delivery, invitation/reset expiry duration, session timeout, rate limiting, reactivation and assignment lifecycle remain TBD.

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

See [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) for remaining decisions. The p95 thresholds, atomicity, audit fields, daily backup/restore gate, GitHub Actions pull-request testing, HTTPS staging target and G-01/G-02/G-09 Option A behaviours are owner-approved; their measurement and implementation mechanisms remain TBD. Blocking issues include G-02 maximum evidence-recording delay, G-09 separate rejected-attempt logging disposition, performance workload/dataset/boundaries, audit retention/correction disposition, backup destination/retention/recovery objectives and zero-cost storage, full CI gate/quota, staging provider/database/email/HTTPS feasibility, SKU rename/alias, invitation/reset token duration, session timeout/rate limiting, remaining-stock resolution, cross-inventory/CSV concurrency, forecast coverage and other details in the review. BR-042–BR-045 settle the authentication method, secure Staff invitation and password ownership, reset-link single use/time limit, and core session/transport/CSRF protections.

### Explicit boundaries

- Product CSV import is excluded.
- Reorder recommendations do not place orders.
- No frontend framework, hosting provider, application architecture or CD solution is selected here. GitHub Actions is approved for pull-request Django/PostgreSQL testing (NFR-010); detailed workflow design remains TBD.
- BR-003 requires recording the adjustment difference/reason; BR-005/BR-041 require enough successful-import history to reject a same-inventory byte-identical re-upload; BR-006–BR-008 and BR-031 require trustworthy dated movements, classification and observation coverage. The audit NFR decision fixes required record fields, but schema, retention and interface details remain TBD. NFR-008 requires daily PostgreSQL backups and a successful restore test before Deployment; backup destination, retention and recovery objectives remain TBD. BR-023 approves initial Manager setup and Manager Staff invitation/creation; BR-026–BR-027 approve Manager Staff deactivation and constrained assignment. Other account administration remains TBD. Export is not an approved feature.
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
