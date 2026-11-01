# Tory batch integrity owner decision package

**Status:** DRAFT — **G-01, G-02 and G-09 remain BLOCKING and PENDING owner decision.** Prepared for Requirements review on 1 November 2026. This document records options and proposed acceptance examples; it does not add a BR ID, approve a rule, approve the SRS, close a gap or authorise Design. BR-001–BR-045 and the six owner-approved NFR decisions remain as recorded in [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md).

The owner may approve, amend, reject or explicitly defer each package. A deferral needs a named responsible role, target stage, bounded observable outcome and verification evidence under the [Requirements gate checklist](REQUIREMENTS_REVIEW.md#5-requirements-gate-readiness-checklist). Storage, locking, scheduler and interface designs belong to a later authorised stage. The examples below are **proposed tests, not executed results**.

## G-01 — Equal-expiry and receipt-order ties

**Existing approvals and IDs.** BR-033 requires automatic FEFO allocation from eligible batches; BR-034 orders eligible dated batches by expiry, then eligible undated batches by receiving order (FIFO). BR-029/BR-035 exclude expired batches at the Singapore midnight boundary. BR-002 and approved NFR-003 prohibit negative balances and double allocation under concurrency. Relevant stable requirements: **FR-004, FR-006, NFR-003**. BR-036 permits eligible negative CSV changes to allocate through FEFO. [SRS](SOFTWARE_REQUIREMENTS_SPECIFICATION.md), [Business Rules](BUSINESS_RULES_AND_EDGE_CASES.md) and [Traceability](REQUIREMENTS_TRACEABILITY_MATRIX.md) leave equal-expiry and indistinguishable receiving-order ties TBD.

**Owner decision needed.** Which eligible batch is consumed first when expiry dates match or receipt order appears equal? What observable allocation must a concurrent ordinary issue or negative CSV issue see? No tie-breaker or locking mechanism has been approved.

| Option | Trade-off |
|---|---|
| A. Stable recorded receiving sequence within each equal-expiry group and among undated batches; if sequence still ties, stable batch ID. | Deterministic, testable and consistent with undated FIFO; requires a reliable receipt-order value and a stable identity. |
| B. Stable batch ID for equal-expiry dates and equal receipt times; retain receiving order for undated batches where distinguishable. | Simple tie resolution but a later receipt could precede an earlier one when timestamps tie, weakening the intuitive FIFO reading. |
| C. Use recorded receiving timestamp, then stable batch ID for equal expiry dates and for undated FIFO. | Deterministic if timestamps and IDs are stable, but clock resolution and equal-time receipts make the final ID tie more common than with a committed receiving sequence. |

**Recommended MVP-safe choice — PROPOSED, NOT APPROVED: Option A.** Within the same product and inventory, order eligible dated batches by `(expiry date, recorded receiving sequence, stable batch ID)` and eligible undated batches after all eligible dated batches by `(recorded receiving sequence, stable batch ID)`. A “receiving sequence” must reflect committed receipt order, including simultaneous receipts; if legacy or imported records cannot be distinguished by that value, use an agreed stable batch-ID comparison as the final tie. The sequence format and batch-ID comparison convention are Design details to specify before formal testing. This proposal does not alter the already-approved dated-before-undated rule or select a concurrency mechanism.

**Proposed deterministic acceptance examples:**

| Case | Given | Expected if Option A is approved |
|---|---|---|
| Equal expiry | Eligible B-20 and B-10 both expire 12 November; B-20 has earlier committed receiving sequence 41, B-10 sequence 42. Issue 1 unit. | Allocate B-20 first despite its lexically later ID; after its eligible units are exhausted, allocate B-10. |
| Final tie | Two eligible batches have the same expiry date and indistinguishable recorded receiving sequence; stable IDs are B-10 and B-20. | Allocate B-10 before B-20 under the final stable-ID order. The ID comparison convention must be specified before this is a formal test. |
| Undated FIFO | Eligible undated U-2 has sequence 7 and U-1 sequence 8; a dated eligible D-1 is also present. Issue spans all three. | Consume D-1 first, then U-2, then U-1. An undated batch with equal sequence uses the final stable-ID tie. |
| Simultaneous issue | Two authorised requests each issue 1 unit against the same last eligible unit. | Exactly one commits that allocation and its matching stock/audit change; the other does not allocate the same unit or create a negative available balance. Which request wins is not predetermined. This verifies approved NFR-003; conflict handling remains Design TBD. |
| Concurrent tied-batch allocation | Two eligible equal-expiry batches have sequences 41 and 42 and one unit each. Two authorised requests concurrently issue 1 unit each. | If both commit, their recorded allocation order is equivalent to one serial order: the first committed allocation consumes sequence 41 and the next consumes sequence 42. If only one commits, it consumes sequence 41. No unit is allocated twice; the winner and retry response are not prescribed. |

**Owner decision:** - [ ] Approve Option A  - [ ] Approve Option B  - [ ] Approve Option C  - [ ] Amend/defer with bounded outcome. **Current status: PENDING OWNER DECISION.** No checkbox is selected.

**If approved, update:** [Owner decisions](OWNER_REQUIREMENTS_DECISIONS.md) with the actual owner decision/date and without changing existing BR IDs; SRS FR-004/FR-006 and NFR-003; [Business Rules](BUSINESS_RULES_AND_EDGE_CASES.md) examples; [Traceability](REQUIREMENTS_TRACEABILITY_MATRIX.md) acceptance references; [Requirements review](REQUIREMENTS_REVIEW.md) and [Gap Analysis](REQUIREMENTS_GAP_ANALYSIS.md) disposition. [Role matrix](ROLE_PERMISSION_MATRIX.md) needs no permission change unless the owner changes scope. G-11 concurrency mechanics remain open.

## G-02 — Expiry quarantine state and history

**Existing approvals and IDs.** BR-029 quarantines expired batches and bars ordinary issue; BR-035 fixes unavailability from **00:00 Asia/Singapore on the expiry date**. BR-030 excludes quarantine from available-to-issue reorder quantity; BR-031 excludes quarantine/disposal from demand; BR-032 records expiry per receiving batch; BR-037 allows only Manager reasoned disposal of quarantined units. BR-033/BR-034 govern allocation of remaining eligible stock. Approved NFR-003 requires atomic inventory actions and audit fields; NFR-011 requires traceable audit records. Relevant stable requirements: **FR-003, FR-004, FR-009, FR-011, NFR-003, NFR-004, NFR-011**. Transition timing, representation and system-actor attribution remain TBD in the [SRS](SOFTWARE_REQUIREMENTS_SPECIFICATION.md) and [Gap Analysis](REQUIREMENTS_GAP_ANALYSIS.md).

**Owner decision needed.** Define the observable relationship among expiry-derived eligibility, physical on-hand, quarantined quantity and audit evidence when a status transition is delayed. Expiry itself does not dispose of or issue physical units. No scheduler, database representation or audit-transition mechanism has been approved.

| Option | Trade-off |
|---|---|
| A. Derive issue eligibility from expiry date and Singapore time at every relevant operation; keep physical stock unchanged; record an attributable quarantine-state event when the state is materialised, with effective boundary and actual recording time. | Midnight safety does not depend on prompt background processing; requires reconciliation so a delayed event cannot duplicate or misstate a transition. |
| B. Require a synchronous, atomic quarantine transition on the first relevant read or mutation after the boundary; eligibility check still enforces the boundary. | History can be materialised promptly on use, but the first operation has extra work and history may appear late if no operation occurs. |
| C. Require a scheduled transition exactly at midnight and deny ordinary issue until it completes. | Explicit transition moment, but scheduling failure could block valid unrelated operations and still requires a date-based eligibility safeguard to satisfy BR-035. |

**Recommended MVP-safe choice — PROPOSED, NOT APPROVED: Option A.** From the boundary, treat expiry-dated units as ineligible for ordinary issue and excluded from available-to-issue **even if a recorded status transition has not yet run**. The displayed quarantined quantity must reflect this expiry-derived classification immediately; a stored quarantine status or its audit event may be recorded later. Keep physical on-hand unchanged until an authorised physical movement, such as BR-037 disposal. Produce one attributable transition record per batch and expiry boundary, using a system identity for automatic expiry, an **effective time** of the Singapore boundary and the **actual recorded time** when evidence is written. Delayed recording must reconcile to the quantity still physically present and must not undo intervening disposal or create a second transition record. The deadline and method for materialising this evidence need owner acceptance; implementation is Design TBD. Quarantine classification is not a stock-out demand event.

**Proposed deterministic acceptance examples:**

| Case | Given | Expected if Option A is approved |
|---|---|---|
| Midnight cutoff | One batch has 5 physical units and expiry date 8 November 2026; no other stock. At 7 November 23:59:59 Asia/Singapore it is eligible. | At 8 November 00:00 it is unavailable for ordinary issue. Physical on-hand remains 5; available-to-issue becomes 0 and quarantined quantity is 5. An issue of 1 fails without stock/audit mutation. |
| Delayed transition | Materialisation occurs at 00:05 on 8 November, after the 00:00 boundary. | An issue at 00:01 is still denied; reorder input at 00:01 excludes the 5 units. Quarantine evidence distinguishes effective time 00:00 from recording time 00:05, identifies the system actor and is not counted as demand. Repeated evaluation does not create duplicate transitions. |
| Disposal before transition recording | The 5-unit batch expires at 00:00; at 00:02 an authorised Manager disposes of 2 units with a reason; automatic transition evidence is recorded at 00:05. | At 00:02 and afterward, physical on-hand and derived quarantine are 3. The disposal and delayed transition remain separately attributable; the later record does not restore the disposed units, claim 5 units are still quarantined, or create demand. The record preserves the effective boundary and actual recording time. |
| Physical disposal | At 00:06 a Manager with authorised inventory access disposes of 2 of the 5 quarantined units with a reason. | Physical on-hand changes 5→3 and quarantine 5→3; a distinct Manager-attributed disposal record retains the reason. Available-to-issue remains 0; disposal contributes no forecast demand. Staff or missing-reason attempts fail without mutation. |
| Mixed stock | A product has 5 expired physical units and 3 eligible undated units at the boundary. | Physical total is 8, quarantine is 5, available-to-issue is 3; an ordinary issue of 3 can use only the eligible units, subject to approved allocation order. |

**Owner decision:** - [ ] Approve Option A  - [ ] Approve Option B  - [ ] Approve Option C  - [ ] Amend/defer with bounded outcome. **Current status: PENDING OWNER DECISION.** No checkbox is selected.

**If approved, update:** owner decision log with actual decision/date; SRS FR-003/FR-004/FR-009/FR-011 and NFR-003/NFR-004/NFR-011; Business Rules balance/expiry examples; Traceability boundary/audit tests; Requirements review and Gap Analysis dispositions. The Role Matrix's approved Manager-only disposal and assigned-inventory limits remain unchanged. G-09 must align on the system-actor and event fields; G-11 concurrency and quarantine implementation remain open.

## G-09 — Audit coverage and record semantics

**Existing approvals and IDs.** The 1 November owner-approved audit decision maps to **NFR-003/NFR-011** and requires actor, business/inventory, action, timestamp, quantity before/after or change and reason where applicable; records must be testable, traceable and retain attribution after account/product deactivation. BR-003 requires Manager adjustment reason/difference; BR-019/BR-026 preserve history/attribution; BR-024 permits authorised history viewing; BR-031/BR-037 distinguish quarantine and reasoned Manager disposal from demand. BR-004 and approved NFR-003 require invalid CSV rollback. BR-021/BR-022 and the [Role Matrix](ROLE_PERMISSION_MATRIX.md) constrain actor access. Relevant stable requirements: **FR-002–FR-007, FR-009, NFR-003, NFR-011**; NFR-004 applies to movement classification for forecasts. No approved record schema, retention duration or correction method is inferred.

**Owner decision needed.** Define which committed actions produce inventory audit events, how a multi-batch or CSV action remains traceable, what system identity means for automatic quarantine, and whether rejected attempts are represented outside the committed inventory ledger. The approved minimum fields alone do not settle these coverage and linkage questions.

| Option | Trade-off |
|---|---|
| A. One logical event per committed inventory mutation, linked to affected batches and source request/import; separate quarantine-state evidence from physical movement; reject attempts produce no committed inventory event. | Compact and testable, including atomic CSV rollback; requires batch-level detail attached to the logical event. Separate security/error logging remains undecided. |
| B. One event per affected batch, all linked to one committed operation/import identity. | Fine-grained allocation history; more records and more care needed to avoid counting a multi-batch issue as multiple demand actions. |
| C. A minimal event with only approved fields and no batch/source linkage. | Lowest detail, but may be unable to prove FEFO, CSV atomicity and concurrency attribution; would need other traceable evidence to satisfy NFR-011. |

**Recommended MVP-safe choice — PROPOSED, NOT APPROVED: Option A.** For every committed inventory mutation, record a linked logical event with actor **or explicit system identity**, business, inventory, product, affected batch IDs and per-batch changes where applicable, action, actual record timestamp, effective timestamp where it differs (for expiry), quantity before/after **and/or** change, movement classification and reason where applicable. Record the relevant physical, available-to-issue and quarantine quantities separately when an action changes their classification; a single undifferentiated balance cannot explain expiry. A committed multirow CSV has traceable row movements sharing one import identity, with each row's product, batch allocation and before/after or change; the import is atomic. Distinguish ordinary demand issue, receipt, adjustment, quarantine-state change and reasoned disposal. A quarantine-state change is **not** a physical stock movement; physical disposal is. The event and its stock/state change must have an all-or-nothing outcome. Rejected attempts produce **no committed inventory mutation event**; whether to retain separate security/validation attempt logs remains TBD. Preserve historical actor/product identity or an equivalent attributable reference after deactivation. “Immutable” correction, retention duration, visibility fields and exact event representation remain for owner disposition or bounded Design deferral.

**Proposed deterministic acceptance examples:**

| Case | Given | Expected if Option A is approved |
|---|---|---|
| Multi-batch issue | An authorised Staff member issues 3 units, allocating 2 from B-1 and 1 from B-2. | One committed logical issue event identifies Staff, business/inventory/product, both batch allocations, actual timestamp, physical/available before 8 and after 5, change −3 and classification ordinary demand. It is counted as 3 demand units, not two separate demands. |
| Expiry transition | The 5-unit batch in G-02 becomes ineligible at 8 November 00:00 Singapore time; transition evidence is recorded at 00:05. | System identity, business/inventory/product/batch, action, effective and recorded times, available 5→0 and quarantine 0→5 are traceable; physical quantity remains 5. Classification is quarantine, not demand. |
| Disposal and adjustment | A Manager disposes of 2 quarantined units with a reason; separately adjusts a physical count with a reason. | Distinct committed events retain Manager identity, affected quantities and applicable reasons. Disposal is excluded from demand; adjustment records BR-003's absolute count and difference and is excluded from demand. |
| Invalid CSV rollback | A valid issue row is followed by an invalid row in one `sku,change` file. | No stock, batch allocation, demand or committed inventory audit event from any row survives; rejection feedback or separate security/error evidence is outside this committed-event rule. |
| Successful CSV import | One valid `sku,change` file commits two negative rows for different products in the selected inventory. | Both row movements and their batch allocations link to the same import identity and Manager actor. Each row has its own quantity change and ordinary-demand classification; the import has one all-or-nothing outcome, and no row is counted twice as demand. |
| Concurrent last unit | Two authorised issues compete for the final eligible unit. | At most one event links a committed allocation of that unit to one actor and one stock change; the unsuccessful request creates no committed inventory mutation event. Winner selection and conflict response remain TBD. |
| Deactivated identities | Staff S issued stock from product P, then S and P were deactivated. | The prior event remains attributable to S and P and retains its business/inventory, quantity, timestamp and classification; authorized history viewing remains limited by BR-022/BR-024. |

**Owner decision:** - [ ] Approve Option A  - [ ] Approve Option B  - [ ] Approve Option C  - [ ] Amend/defer with bounded outcome. **Current status: PENDING OWNER DECISION.** No checkbox is selected.

**If approved, update:** owner decision log with actual decision/date; SRS FR-002–FR-007/FR-009 and NFR-003/NFR-011 (plus NFR-004 classification); Business Rules acceptance examples; Traceability audit/rollback/retention evidence; Role Matrix history-view note only if observable fields change; Requirements review and Gap Analysis dispositions. Retention duration, correction procedure, security attempt logs, implementation/concurrency mechanism and full SRS approval remain separate open decisions.

## Decision record and gate boundary

| Package | Owner selection or bounded deferral | Responsible role / target stage / required evidence | Status |
|---|---|---|---|
| G-01 | TBD | TBD | **PENDING** |
| G-02 | TBD | TBD | **PENDING** |
| G-09 | TBD | TBD | **PENDING** |

No option in this package has been selected by the owner. The [Gap Analysis](REQUIREMENTS_GAP_ANALYSIS.md) still counts **10 blocking, 8 conditional and 2 nonblocking** gaps. This package supplies proposed decisions for three blockers; it does not reduce those counts or satisfy the Requirements exit checklist.
