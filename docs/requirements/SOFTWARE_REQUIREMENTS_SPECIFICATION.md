# Tory Software Requirements Specification

**Course:** Singapore Polytechnic ST0529 CA1  
**Product:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*  
**Lifecycle:** Waterfall: Planning, Requirements, Design, Implementation, Testing, Deployment  
**Requirements window:** 31 October–5 November 2026 (target; schedule risk tracked)  
**Status:** Draft for owner review — **not approved; Requirements exit pending**  
**Backend constraint:** Django 5.2 LTS + PostgreSQL approved in [ADR-001](../decisions/ADR-001-backend-and-database.md).

## 1. Purpose

This SRS translates the approved high-level Tory baseline into testable requirements for owner review. It is a Requirements-stage draft, not a Design, architecture, implementation or testing record. Detailed behaviour is marked as approved owner decisions or proposed detail requiring later owner approval. No requirement in this draft claims implementation or test completion.

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

As a Tory Staff user, I set my own password after a Manager's email invitation, then use email/password sign-in to view assigned inventory and its transaction history, record ordinary stock-in/out, view supplier lead time and safety stock, and inspect forecasts/reorder suggestions. I cannot perform Manager-only actions. Email delivery feasibility and token/session implementation remain TBD; G-07 Option A fixes observable timing on 3 November 2026.

### Project owner / solo developer

The same person owns the project and performs development, review, testing and demonstration. Codex is a guided coding aid; generated changes are independently reviewed and tested. This is a delivery constraint, not a product user role.

## 4. Requirement status and priority conventions

- **Confirmed baseline / owner rule:** Charter/P1 capabilities and [BR-001–BR-045](OWNER_REQUIREMENTS_DECISIONS.md) are approved individually. BR-012–BR-025 were supplied as supplementary owner evidence and documented on 1 November 2026; their original approval timestamp is not known. Other detailed criteria remain draft until SRS approval.
- **PROPOSED detail:** a specific interpretation added to make the baseline testable; it is not an approved business rule until accepted by the owner.
- **TBD:** information is absent and must be resolved or explicitly deferred with an owner and due stage.
- Priority: **Must** = needed to satisfy the fixed baseline; **Should** = proposed quality/detail that materially supports baseline completion; **TBD** = owner decides whether it is required.

## 5. Functional requirements

Acceptance criteria describe planned verification. Approved BR and gap decisions are binding observable requirements; unapproved details remain proposals until owner acceptance of the full SRS.

### FR-001 — Identify and select a product

- **Priority/status:** SKU and business uniqueness plus permanent original-product reservation **APPROVED BR-001/BR-017/BR-038**; shared business catalogue, inventory-specific price and soft deactivation **APPROVED BR-016/BR-018/BR-019**; Manager product actions and all-inventory zero-stock deactivation guard **APPROVED BR-021/BR-028/BR-040**. Other lifecycle details TBD.
- **Actor:** Manager or Staff, subject to approved permissions.
- **Preconditions:** User is authenticated and authorized; product exists and its lifecycle state permits the requested action under BR-028.
- **Main flow:** User selects a product using its approved identifier; Tory presents the product identity and current recorded stock.
- **Errors:** Unknown or unauthorized selection is rejected without mutation. Inactive products remain available to authorized lifecycle/history views; ordinary transactions against them are rejected (BR-019/BR-028).
- **Acceptance criteria:** Reject missing/blank-after-trim SKU and case collisions within a business. A SKU remains reserved to its original product after deactivation (BR-038). One business shares a catalogue while inventories and selling prices remain separate. Managers create/edit/deactivate/reactivate within approved authority (BR-021/BR-028); exact catalogue-level authority remains G-13 open. **G-05 Option A, approved 3 November 2026:** every business inventory, including quarantine, must have zero physically held units before deactivation, checked atomically at commit. If receipt commits first, deactivation fails; if deactivation commits first, later ordinary receipt fails. Preserve product identity and attributable history. Physically present damaged goods outside quarantine and returned goods without an approved movement category block deactivation pending owner disposition or formally justified bounded exception. SKU rename and price format remain TBD.

### FR-002 — View current inventory

- **Priority/status:** Assigned-inventory view and history **APPROVED BR-021/BR-022/BR-024**; list/search/filter detail **PROPOSED**.
- **Actor:** Manager and Staff, limited to assigned inventories within their own business (BR-022). BR-027 further constrains Manager assignment of Staff; it does not expand viewing scope.
- **Preconditions:** User is authenticated; products exist.
- **Main flow:** User requests an assigned inventory; Tory displays its product identity, recorded quantities and inventory-specific selling prices where included in the view. Both roles may view its transaction history.
- **Errors:** Unauthorized request is denied; unavailable database data is reported without presenting an unverified quantity as current.
- **Acceptance criteria:** Both roles can view assigned inventories and their transaction history; requests for unassigned or other-business inventories are denied (BR-021/BR-022/BR-024). Separate inventories may have different prices for the same catalogue product (BR-016/BR-018). Displayed physical on-hand matches committed stock; available-to-issue and quarantine views apply approved G-02 expiry eligibility from Singapore midnight even before a stored transition. History view fields, price format and search/filter details remain TBD.

### FR-003 — Record stock-in

- **Priority/status:** Ordinary stock-in for both roles **APPROVED BR-021**; whole-number base units **APPROVED BR-020**; expiry per receiving batch **APPROVED BR-032**; manual receiving with batch/expiry details for expiry-tracked products **APPROVED BR-036**; one eligible undated batch per valid non-expiry positive CSV row **APPROVED G-03 Option A, 1 November 2026**; other manual input fields TBD.
- **Actor:** Manager or Staff for an assigned inventory in their own business (BR-021/BR-022).
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User manually receives expiry-tracked stock with batch/expiry details; for a product not tracked for expiry, expiry is optional. Tory validates the whole-number stock-in and updates stock atomically.
- **Errors:** Invalid/nonpositive quantity, unknown product or database failure is rejected without partial state. Manual duplicate-request handling remains TBD.
- **Acceptance criteria:** For valid positive whole-number base-unit quantity `q`, committed on-hand becomes prior quantity + `q`; fractional units are rejected (BR-020). An expiry-tracked product is received manually with batch/expiry details (BR-032/BR-036); positive CSV rows for it are rejected under FR-006. Expiry is optional for a non-expiry-tracked product. A positive CSV row for a non-tracked product creates its own eligible undated batch with stable identity and committed receipt sequence (G-03); manual and CSV undated receipts share the same order. An unassigned inventory or deactivated product rejects ordinary stock-in (BR-022/BR-028). Invalid input leaves quantity unchanged. Packaging conversion, exact sequence/identifier representation and history retention remain TBD.

### FR-004 — Record stock-out

- **Priority/status:** Ordinary stock-out for both roles **APPROVED BR-021/BR-022**; whole-number base units and no-negative rule **APPROVED BR-020/BR-002**; demand proxy with quarantine/disposal exclusion **APPROVED BR-006/BR-031**; expiry eligibility, FEFO then undated FIFO **APPROVED BR-029/BR-033–BR-035**; Manager-only reasoned disposal **APPROVED BR-037**.
- **Actor:** Manager or Staff for an assigned inventory in their own business.
- **Preconditions:** User authorized; product exists; quantity input satisfies approved validation.
- **Main flow:** User submits an ordinary issue quantity; Tory allocates eligible dated batches by earliest expiry (FEFO), followed by eligible undated batches in receiving order (FIFO), and commits atomically. An expiry-dated batch is unavailable for ordinary issue from 00:00 on its expiry date in Asia/Singapore (BR-034/BR-035). Separately, only a Manager may dispose of quarantined units with a required reason and attributable history (BR-037).
- **Errors:** Reject a stock-out that would make on-hand negative without partial mutation. Other validation and manual duplicate handling remain TBD.
- **Acceptance criteria:** Reject fractional base-unit quantity and access to an unassigned inventory. An ordinary issue cannot use a deactivated product or a batch expired at Singapore local midnight on its expiry date, even if stored quarantine transition is delayed. Within a product/inventory, consume eligible dated batches by `(expiry date, committed receiving sequence, stable batch ID)`, then eligible undated batches by `(committed receiving sequence, stable batch ID)` (G-01 approved Option A; BR-033/BR-034 preserved). Insufficient eligible stock is rejected atomically even if quarantined physical stock remains. Display quarantine and exclude expired remaining units from available-to-issue immediately while physical on-hand is unchanged (G-02 approved Option A). Only Managers may dispose of quarantined units with reason and attributable, nondemand history (BR-037). **Acceptance examples:** equal-expiry B-20 sequence 41 precedes B-10 sequence 42; a dated batch precedes undated U-2 sequence 7 then U-1 sequence 8. At 8 November 2026 00:00 Asia/Singapore, a five-unit expiring batch has physical 5, available 0 and quarantine 5; a reasoned Manager disposal of 2 changes physical/quarantine to 3/3 without demand, while Staff or reasonless attempts fail. Exact batch-ID comparison convention, quarantine evidence-delay bound, reason format and G-11 concurrency mechanics remain TBD.

### FR-005 — Record stock adjustment

- **Priority/status:** Manager-only absolute whole-base-unit physical count, required reason and recorded difference **APPROVED BR-003/BR-020/BR-021**. G-05 Option A, approved 3 November 2026, requires evidence of the actual observed count when used to resolve a genuine discrepancy; reason format/evidence representation remain Design TBD.
- **Actor:** Manager only; Staff cannot perform adjustment.
- **Preconditions:** User has adjustment permission; product exists; adjustment input is valid.
- **Main flow:** Manager enters physical count and reason; Tory sets on-hand to that count and records `new count − prior on-hand` atomically.
- **Errors:** Unauthorized, invalid or conflicting adjustment is rejected without partial update. Whether a particular adjustment is an ordinary transaction against a deactivated product requires classification under BR-028.
- **Acceptance criteria:** Prior `p`, whole-number actual physical count `c` yields on-hand `c` and recorded difference `c − p` with mandatory reason and evidence of the actual count. Adjustment is non-demand. A Manager cannot enter zero while goods remain physically present to force deactivation (G-05 Option A). Reject Staff, unassigned inventory, missing reason/evidence, fractional count and negative resulting count without partial mutation. Packaging conversion and retention remain TBD.

### FR-006 — Import stock transactions atomically from CSV

- **Priority/status:** Manager import permission **APPROVED BR-021**; `sku,change`, atomicity, empty/header-only rejection **APPROVED BR-004**; successful same-inventory byte-identical re-upload rejection **APPROVED BR-005/BR-041**; whole-number base units **APPROVED BR-020**; before-upload inventory selection, all-row scope, expiry-tracked positive-row rejection and negative batch allocation **APPROVED BR-036/BR-039**. G-03 per-positive-row undated receiving and G-04 strict CSV contract/limits were **owner-approved 1 November 2026**.
- **Actor:** Manager for an assigned inventory in the same business; Staff denied (BR-021/BR-022).
- **Preconditions:** Before upload, Manager explicitly selects one inventory they are authorized to access (BR-039); upload satisfies approved G-04 strict UTF-8, 262,144-byte and 1,000-data-row limits; referenced products are valid for that inventory.
- **Main flow:** Tory validates the entire stock-transaction file, evaluates repeated SKU rows sequentially in file order, and commits every valid row with its batches and G-09 audit evidence as one atomic import. Positive non-expiry rows each create an eligible undated batch; negative rows allocate eligible stock under approved FEFO/FIFO.
- **Errors:** Invalid rows, malformed UTF-8/BOM, malformed/empty/header-only uploads, size/row-limit violations, insufficient eligible stock, or same-inventory byte-identical re-upload after success reject the whole file without committed stock, batch, demand, successful-import marker or inventory-mutation audit changes. Give at least the first failing row and field when applicable, or a file-level error category (G-04).
- **Acceptance criteria:** Before upload, a Manager selects one authorized inventory; every row applies only there (BR-039). Staff and out-of-scope imports are denied. Strict UTF-8 is required; reject malformed UTF-8 and BOM. The first record is exactly lowercase `sku,change` with no surrounding whitespace or extra column. LF and CRLF are accepted. Each data record has exactly two fields; standard CSV quoting for commas/quotes is allowed, but embedded record newlines and blank records fail. Trim outer SKU spaces for lookup, never `change`. A nonzero change matches `[+-]?[0-9]+`; reject `0`, `-0`, fractions, scientific notation, surrounding change whitespace and unsafe magnitudes. Reject empty/header-only files, unknown/inactive/unauthorised products and other invalid transactions. Raw bytes must be **≤262,144** and data rows **≤1,000** independently and inclusively. Repeated SKU rows execute in file order without aggregation. Each valid positive row for a non-expiry-tracked product creates a distinct eligible undated batch with stable identity and committed sequence; positive rows for expiry-tracked products reject the whole file (BR-036). Negative rows allocate by approved dated FEFO/undated FIFO and G-01 ties; expired units never satisfy them (G-02). `P,+5` then `P,+3` creates batches 5 and 3; subsequent `P,-6` consumes 5 then 1 and leaves 2. With zero initial stock, `P,+5` then `P,-2` commits with 3 remaining, while `P,-2` then `P,+5` fails wholly. A later invalid row rolls back all stock, new batches, allocation, demand, success marker and committed audit evidence (G-09). Successful row movements link to one import identity without double-counted demand. Reject exact bytes of a prior success in the **same inventory** (BR-041); a prior failure or success in another inventory does not establish a duplicate there. Concurrent identical same-inventory imports cannot both commit. Ordinary negative issues count as demand; receipts, quarantine and disposal do not. Batch/sequence storage, safe integer magnitude, byte-identity retention, parser, concurrency mechanism and broader error presentation remain Design/open-gap details. These criteria are approved behaviour, not implementation or test evidence.

### FR-007 — Authenticate users and distinguish Manager/Staff access

- **Priority/status:** BR-021–BR-027 and BR-042–BR-045 approve roles, scope, Django email/password authentication, Staff invitation, reset links and session/transport/CSRF controls. **G-07 Option A, owner-approved 3 November 2026**, fixes invitation/reset lifetimes and invalidation, session clocks/revocation, abuse thresholds, generic account feedback and MFA outside MVP. Email delivery service, G-09 rejected-attempt logging, G-10 feasibility, G-13 catalogue scope and implementation mechanisms remain open.
- **Actor:** Manager, Staff, and any proposed account administrator.
- **Preconditions:** Initial Manager provisioned during setup or Staff securely invited by a Manager through email (BR-023/BR-043); invitee sets their own password. Email login identity is unique per account and case-insensitive (TORY-10 owner clarification, 3 November 2026). Email delivery and initial Manager credential setup TBD.
- **Main flow:** Manager or Staff signs in with email and password through Django-based authentication (BR-042). Server-managed session access uses HttpOnly cookies, HTTPS and CSRF protection (BR-045). Protected operations enforce the approved role/action matrix and assigned-inventory/business boundary (BR-021/BR-022). Managers invite Staff by email without choosing their passwords (BR-043), may deactivate Staff while preserving attributable history (BR-026), and may assign Staff only to inventories they are authorized to manage in the same business (BR-027). Users may request a time-limited, single-use password reset link (BR-044). Before CSV upload, a Manager explicitly selects an authorized inventory (BR-039).
- **Errors:** Wrong password, inactive account, expired/revoked/reused/superseded invitation or reset link, missing permission, failed CSRF or exceeded approved abuse threshold grants no protected access or mutation. Public account responses are generic for active, inactive and unknown identities, with no materially distinguishable status or timing. Exact wording/response mechanism is Design TBD.
- **Acceptance criteria:** Correct email/password credentials establish a server-managed session for an active role within BR-022/BR-027 scope; wrong credentials do not. **G-07 approved Option A (3 November):** Staff invite is single-use and valid 24 hours; at most one usable link per identity; an authorised Manager may revoke/resend within scope, and resend supersedes older links. Expired/revoked/used/superseded links grant no access. Reset link is single-use and valid 30 minutes; R2 supersedes R1; successful R2 invalidates all reset links and prior sessions and requires sign-in. Sessions expire after 30 minutes idle or 8 hours absolute from creation; successful authenticated protected requests count as idle activity but cannot extend absolute life. Logout ends current session; deactivated Staff is denied on next protected request, including an old session. Owner-controlled credible compromise response revokes all affected sessions, requires reset and preserves attribution. Enforce independent login failures of 5/identity/15 minutes and 20/IP/15 minutes, reset requests of 3/identity/hour and 20/IP/hour, and 5 Staff invites/Manager/day; the next excess attempt is throttled without an invented extra ban. Public account feedback does not reveal active/inactive/unknown identity; eligible email failure permits safe authorised retry, and attempted delivery alone does not activate or change a password. Do not disclose raw tokens/passwords to unauthorised parties. Invalid CSRF or out-of-scope inventory requests cause no mutation. MFA is outside MVP, with risk and future change control. Window/day boundaries, token/clock/rate/session mechanisms, delivery feasibility and unlisted administration remain Design/open-gap details.

### FR-008 — Maintain per-product supplier and reorder settings

- **Priority/status:** Supplier lead time and safety stock only **APPROVED BR-010/BR-014**; nonnegative whole-number safety stock including zero **APPROVED BR-015**; Manager edit/Staff view-only **APPROVED BR-025**.
- **Actor:** Manager edits; Staff views settings for authorized inventories. Other settings are outside MVP (BR-014/BR-025).
- **Preconditions:** Product exists; user has approved configuration permission.
- **Main flow:** An authorized user views a product's supplier lead time and safety stock; an authorized Manager may update them. Tory validates and persists approved changes.
- **Errors:** Invalid values, missing product or unauthorized edit is rejected with no partial configuration update.
- **Acceptance criteria:** Each product's lead time is a positive whole number of calendar days; reject zero, negative or fractional days. Safety stock is a nonnegative whole number, including zero; reject negative or fractional values. Managers may edit; Staff may view but not edit; both remain within assigned inventories. Minimum order quantities, pack sizes and other advanced reorder settings are outside MVP. Values for one product do not alter another. Editing workflow and maximum values TBD.

### FR-009 — Supply eligible demand observations for forecasting

- **Priority/status:** Stock-out proxy and prior seven complete Singapore days **APPROVED BR-006–BR-008**; quarantine/disposal exclusion **APPROVED BR-031**; attributable per-product/inventory/day Manager verification after day end and CSV commit-time dating **APPROVED G-06 Option A, 3 November 2026**. Data representation/UI remain Design TBD.
- **Actor:** System aggregates committed movements; only an authorised Manager verifies the completed product/inventory Singapore day. Manager and Staff view results under FR-010 within assigned scope.
- **Preconditions:** Dated committed movements and Manager-verified complete observation for each of the previous seven Asia/Singapore calendar days for this product/inventory. The current day is excluded.
- **Main flow:** Count committed ordinary manual and negative-CSV stock-outs as demand; exclude stock-in, adjustments, quarantine, Manager-recorded disposal and rejected-batch rows. Group by the previous seven complete Singapore calendar days, excluding current day. BR-031/BR-037 keep quarantine and disposal out of ordinary demand.
- **Errors:** Any unobserved/incomplete day makes the forecast unavailable. Absence of movement records alone does not establish a verified zero day.
- **Acceptance criteria:** **G-06 Option A, approved 3 November 2026:** retain attributable verification status for each product/inventory/complete Asia/Singapore day. Only an authorised Manager may verify after local day end. A verified no-issue day contributes zero; any unverified/incomplete day makes the prior-seven-complete-day forecast and dependent reorder recommendation unavailable. Late/missing discovery invalidates the affected verification and dependent outputs until correction and reverification. Successful negative `sku,change` CSV issues use successful import/commit time; backdating through this timestamp-free contract is prohibited. Singapore midnight separates prior/current days. Receipts, adjustments, quarantine and disposal are non-demand; linked CSV and multi-batch issues count once. Coverage representation, UI and invalidation/concurrent-correction mechanism remain Design TBD.

### FR-010 — Calculate and display an explainable seven-day moving average

- **Priority/status:** Seven-day average confirmed; window, coverage and precision **APPROVED BR-007–BR-009**; both roles may view for assigned inventories **APPROVED BR-021/BR-022**; quarantine/disposal exclusion **APPROVED BR-031**.
- **Actor:** Manager and Staff for assigned inventories within their own business.
- **Preconditions:** Seven previous complete, reliably observed Asia/Singapore days exist for the product.
- **Main flow:** Tory calculates the moving-average value from the approved seven-day window and displays the result with the dates and daily inputs/assumptions needed to explain it.
- **Errors:** Missing or incomplete coverage on any day makes forecast unavailable; do not infer zero from no records.
- **Acceptance criteria:** Use the previous seven complete Singapore days, excluding the current day, each verified for this product/inventory after day end by an authorised Manager. Verified `[1,0,1,0,1,0,0]` totals 3 and yields full-precision `3/7` units/day, displayed `0.43`; retain `3/7` for downstream calculations. One unverified/incomplete or later-invalidated day makes the forecast unavailable until correction and reverification. Do not infer zero from no records. See [approved G-06 examples](STOCK_DEMAND_GAP_OWNER_DECISIONS.md).

### FR-011 — Produce an explainable reorder recommendation

- **Priority/status:** Formula and informational nature **APPROVED BR-011**; threshold alert, pending-delivery exclusion, settings scope and safety-stock validation **APPROVED BR-012–BR-015**; both roles may view for assigned inventories **APPROVED BR-021/BR-022**; available-to-issue quantity excluding quarantine **APPROVED BR-030**.
- **Actor:** Manager and Staff for assigned inventories within their own business.
- **Preconditions:** FR-010 result and approved product supplier/reorder settings are available.
- **Main flow:** Compute reorder point = full-precision average daily demand × positive whole calendar-day lead time + nonnegative whole-number safety stock. Use available-to-issue quantity, excluding quarantined stock and ignoring incoming/pending supplier deliveries, for `max(0, ceil(reorder point − available-to-issue quantity))` (BR-011/BR-013/BR-030). Trigger a reorder alert when available-to-issue quantity is at or below the reorder point (BR-012). Display the alert and suggested quantity separately; create no purchase order.
- **Errors:** Missing forecast/settings or invalid values yield an unavailable recommendation with a reason; no purchase order is created.
- **Acceptance criteria:** For verified demand total `3` over seven days, lead time `7`, valid safety stock `0`, available-to-issue quantity `0`: full-precision average `3/7`, reorder point `3`, suggested quantity `3`; displayed `0.43` must not be multiplied back. At available-to-issue quantity equal to reorder point, show the alert even when suggested quantity is `0` (BR-012). Pending deliveries and quarantined stock do not increase the stock input (BR-013/BR-030). At Singapore midnight on an expiry date, the stock input excludes expired remaining units even if transition evidence is delayed (G-02 approved Option A). Missing, incomplete or late-invalidated G-06 daily verification yields no numeric recommendation until correction and Manager reverification. Advanced settings and automatic purchasing remain outside MVP; exact alert presentation when inputs are unavailable remains TBD.

### FR-012 — Provide controlled validation feedback

- **Priority/status:** **PROPOSED detail** supporting movement and CSV baseline.
- **Actor:** Authorized user.
- **Preconditions:** User submits a transaction or batch.
- **Main flow:** Tory reports success or identifies the relevant row/field and reason for rejection without exposing secrets or internal stack traces.
- **Errors:** Error-reporting failure must not weaken atomicity or authorization.
- **Acceptance criteria:** **Approved G-04 minimum for rejected CSV:** identify at least the first failing row and field where applicable, or an appropriate file-level category; reject without committed mutation. Other invalid-movement feedback and broader usability detail remain **proposed** under FR-012/NFR-005. Exact wording and whether additional errors are shown remain open under G-19.

## 6. Nonfunctional requirements

The six owner-approved nonfunctional decisions dated 1 November 2026 map to NFR-003, NFR-006 and NFR-008–NFR-011 below and are recorded in [OWNER_REQUIREMENTS_DECISIONS.md](OWNER_REQUIREMENTS_DECISIONS.md#owner-approved-nonfunctional-decisions--1-november-2026). Measurement parameters and infrastructure details marked **TBD** are not approved. None is a measured result; formal execution evidence belongs in later Waterfall stages.

### Security

**NFR-001 — Authorization:** Every protected operation enforces BR-021–BR-027 role and assigned same-business inventory scope server-side; denial precedes mutation. BR-026 and G-07 Option A (3 November) deny deactivated Staff on the next protected request, including an old session; owner-controlled suspected-compromise response revokes all affected sessions without granting Managers a general session-administration right. BR-037 limits quarantine disposal to Managers; BR-039 requires authorised CSV inventory selection. BR-042/BR-045 require authenticated server-managed sessions and CSRF. **Planned verification:** denied Staff, stale-session, invalid-CSRF and cross-business/out-of-scope requests cause no protected mutation. G-13 catalogue authority and session mechanism remain open.

**NFR-002 — Credential and secret handling:** BR-042–BR-045 and owner-approved G-07 Option A (3 November) require Django email/password, Staff-controlled password setup, 24-hour single-use/latest-only invitation, 30-minute single-use/latest-only reset, prior-session revocation after reset, 30-minute idle/8-hour absolute session limits, logout and deactivation denial, independent 5/identity and 20/IP failed logins per 15 minutes, 3/identity and 20/IP reset requests per hour, 5 invites/Manager/day, generic public identity responses, safe eligible email retry and no raw-token/password disclosure to unauthorised parties. Successful authenticated protected requests count as idle activity but cannot extend the 8-hour limit. Owner-controlled compromise response revokes all account sessions and requires reset; MFA is outside MVP with future change control. Approved HttpOnly/HTTPS/CSRF remain mandatory. **Planned verification:** clock-controlled link/session boundaries, supersession/reuse, threshold next-attempt denials, generic account responses, delivery failure, CSRF and scoped access. Token persistence, clock/window mechanics, concurrent throttling, rejected-attempt logging (G-09), email feasibility (G-10) and exact response wording remain open. No security implementation or test is claimed.

### Correctness and data integrity

**NFR-003 — Transaction integrity and audit:** **Owner-approved 1 November 2026:** every inventory transaction is atomic; an accepted operation cannot leave a negative available-to-issue balance or allocate the same batch units twice under concurrency. An invalid CSV import commits no rows, and byte-identical previously successful imports for the same inventory are rejected per BR-041. The separate G-01/G-02/G-03/G-04/G-09 Option A approvals of 1 November fix deterministic batch ties, expiry-derived eligibility, one undated batch per non-expiry positive CSV row, strict CSV contract/limits and one logical event per committed inventory mutation linked to batches and source operation/import. Each event identifies actor or system, business, inventory, product, action, timestamp, affected batches, relevant quantity before/after or change, classification and required reason; distinguish physical, available and quarantine quantities where relevant. Commit stock/state and evidence together; rejected operations have no committed inventory-mutation event. Sequential repeated CSV rows and their new batches roll back together on any failure. Link successful CSV row movements to import identity without double-counting demand; preserve actor/product attribution after deactivation. Existing BR-002–BR-005, BR-020, BR-028–BR-041 remain binding. **Proposed verification:** PostgreSQL integration/concurrency cases cover tied allocation, no double allocation, midnight expiry, per-row positive receiving, repeated-SKU order, strict CSV boundary/invalid cases, same-inventory concurrent byte duplicate, full stock/batch/audit rollback and retained attribution. **Open:** G-02 maximum evidence-recording delay; G-09 separate rejected-attempt logging; transaction/locking and batch/sequence storage, safe integer magnitude, byte-identity retention, audit schema/retention/correction, other holds and workload. No formal test or capacity result is claimed.

**G-08/NFR-003 concurrency acceptance, owner-approved 3 November 2026:** In at least 20 repeated two-request races for one remaining eligible unit, exactly one issue commits in every race. The rejected issue leaves no negative physical or available quantity, double allocation or partial committed inventory-mutation audit evidence. PostgreSQL locking and transaction implementation remain G-11 Design details; this is planned verification, not a test result.

**NFR-004 — Forecast reproducibility:** G-06 Option A, approved 3 November 2026, requires attributable Manager-after-day-end verification for each prior complete Singapore day and invalidation of dependent output on a late/missing discovery until correction and reverification. Timestamp-free CSV uses successful import/commit time without historical backdating. For fixed dated ordinary stock-out inputs, verified daily coverage, available-to-issue quantity and approved settings, use BR-007–BR-015 and BR-030–BR-031/BR-037 deterministically. G-09 approved classification counts each ordinary issue once even when it spans batches or CSV-linked rows; quarantine and attributable disposal are excluded from demand. G-02 excludes expired remaining units from reorder available-to-issue at Singapore midnight even if transition evidence is delayed; pending deliveries remain excluded. Show the Singapore seven-day window, two-decimal display, full-precision inputs and alert separately from suggested quantity; unobserved days yield unavailable rather than an imputed zero. Formula version, coverage representation/UI, concurrent correction handling and record-retention details TBD.

### Usability

**NFR-005 — Understandable outcomes:** Users shall be able to distinguish stock-in, stock-out and adjustment outcomes and understand why a CSV batch or forecast is rejected/unavailable. Exact interface and usability testing method are **TBD**; no frontend is selected.

### Performance

**NFR-006 — Response time:** **Existing owner approval, 1 November 2026:** ordinary HTTP p95 ≤2 seconds and forecast-class p95 ≤3 seconds; neither is relaxed. **G-08 owner approval, 3 November:** formal Envelope B has 2 businesses, 4 inventories total, 500 products, 2,000 receiving batches, 20,000 historical transaction rows, 5 simultaneous users and up to 5 in-flight HTTP requests. Time from HTTP client start to full response over a controlled local network. Per run, 20 warm-up requests per class precede 500 measured ordinary plus 500 forecast-class requests; conduct 3 runs, each independently passing both limits. Nearest-rank p95 is sorted duration at one-based `ceil(0.95 × n)`; do not average runs. A is development smoke only; C optional diagnostic. Valid 1,000-data-row CSV import is a separate completion class with **≤30 seconds** in the formal environment; existing 256 KiB/1,000-row acceptance maxima remain unchanged. Report cold starts separately and do not infer hosted/remote performance from warm local results. **Still blocking for complete G-08 acceptance:** exact ordinary and forecast/reorder endpoint mixes, verified controlled environment/reproducibility and cold-start pass/fail treatment. Draft 20%-each/50–50 mixes and 2 vCPU/4 GiB floor remain **PROPOSED, NOT APPROVED**. No measurement or hardware-capacity result is claimed.

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

- **Business/catalogue product:** one shared product catalogue per business, with case-insensitive business-scoped SKU, stable identifier, display name and soft lifecycle state (BR-016–BR-019). Each SKU stays reserved to its original product, including after deactivation (BR-038). Managers create/edit/deactivate (BR-021) and reactivate (BR-028); deactivation requires zero physical stock, including quarantined units, in every inventory of that business (BR-040). SKU rename/alias and G-13 catalogue authority remain TBD; G-05 Option A fixes the permitted issue, genuine evidenced adjustment, quarantined disposal and atomic zero guard, while damaged nonquarantined and unclassified returned physical stock still block deactivation.
- **Inventory:** separate inventory records and inventory-specific selling prices (BR-016/BR-018), with access limited to assignments in the same business (BR-022). Price format, assignment lifecycle and inventory identity TBD.
- **Receiving batch:** per-batch expiry when tracked, optional expiry for non-expiry-tracked products; expiry-tracked receipts are manual (BR-032/BR-036). Each committed positive CSV row for a non-tracked product creates one eligible undated batch with stable identity/committed receipt sequence; manual and CSV undated receipts share ordering (G-03). Eligibility excludes dated stock from Singapore local 00:00 on its expiry date independently of stored status (G-02). Eligible dated batches follow expiry, committed receiving sequence and stable batch ID; undated batches follow sequence and stable ID afterward (G-01). Physical on-hand persists until authorised movement; displayed quarantine reflects expired remaining units immediately. Sequence storage, ID comparison, transition mechanism and maximum evidence-recording delay remain TBD.
- **Stock movement/audit history:** one logical event per committed inventory mutation linked to affected batches and source operation/import (G-09 approved Option A), with actor/system, business/inventory/product, action, timestamp, relevant quantities/classification and required reason. Expiry transition has effective and recorded times and system attribution (G-02). Stock/state and committed evidence are atomic; rejected operations create no committed mutation event. Both roles may view authorized history (BR-024); deactivation preserves attribution (BR-019/BR-026). Separate rejected-attempt logging, schema, view fields, retention and correction remain TBD.
- **Import batch:** identify successful imports by selected inventory and exact raw file bytes; reject a prior byte-identical success only within that inventory (BR-041). Every row applies to the Manager's explicitly selected authorized inventory (BR-039). G-04 approves strict UTF-8 without BOM, exact `sku,change` header, two-field CSV records, sequential repeated rows and inclusive 262,144-byte/1,000-data-row caps. G-03 positive rows create separate undated batches; any failed row rolls back all rows and new batches. Byte comparison/retention implementation, concurrency safeguard and row-level validation representation remain Design details.
- **Supplier/reorder settings:** per-product positive whole-calendar-day lead time and nonnegative whole-number safety stock, including zero; these are the only MVP reorder settings (BR-010/BR-014/BR-015). Managers edit and Staff view within their authorized scope (BR-025).
- **Demand observation/forecast:** G-06 Option A (3 November 2026) requires attributable per-product/inventory/complete-Singapore-day verification by an authorised Manager after day end, including verified zero days. Missing/invalidated coverage makes forecast and dependent recommendation unavailable. Late discoveries invalidate affected verification/output until correction and reverification. Timestamp-free CSV uses successful import/commit time; historical backdating is prohibited. Data representation, UI, retention and concurrent correction handling are Design TBD.
- **User/role and inventory assignment:** initial Manager provisioned during setup; Managers securely invite Staff by email and invitees set their own passwords (BR-023/BR-043). Django email/password identity, active status, attributable history, Manager/Staff role, business boundary and assignments support BR-021–BR-027/BR-042. Time-limited single-use reset links (BR-044), server-managed sessions, HttpOnly cookies, HTTPS and CSRF protection (BR-045) are logical needs, not a prescribed schema. G-07 Option A fixes invitation/reset expiry, session limits and rate thresholds; email delivery feasibility, clock/token/session/throttle implementation, reactivation and assignment lifecycle remain open.

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

See [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) for remaining decisions. Existing BR-001–BR-045, six NFR decisions and G-01–G-06/G-09 dispositions remain as recorded. G-07 Option A is approved with Design verification open. G-08 Envelope B, separate CSV ≤30-second target, local timing, run/p95 and 20-race outcomes are approved, but exact traffic mixes, verified environment and cold-start pass/fail treatment still block complete benchmark definition. G-02 delay, G-05 unsupported physical stock, G-09 rejected-attempt logging, G-10 zero-cost HTTPS/email/PostgreSQL/backup feasibility, G-11 concurrency design and other review items remain open. No full SRS, Requirements exit or Design entry approval is implied.

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
