# Tory stock resolution and demand coverage owner decision package

**Status:** Owner-approved G-05 and G-06 Option A, recorded **3 November 2026**. G-05 remains **BLOCKING** for unsupported physical-stock disposition; G-06 Requirements behaviour is resolved with Design verification open. Examples below are approved acceptance criteria, not executed tests. The complete SRS, Requirements exit and Design entry remain **NOT APPROVED**. No new BR, FR or NFR ID is created.

## 1. Executive summary and approved boundary

| Gap | Decision context | Owner-approved selection and remaining boundary |
|---|---|---|
| **G-05 — product deactivation and stock resolution** | Resolve all physical stock before a Manager deactivates a product. | **Option A approved, 3 November 2026:** legitimate issue, genuine evidenced Manager count adjustment, Manager reasoned quarantined disposal, then atomic zero recheck across all business inventories. Damaged nonquarantined and unclassified returned physical goods remain blocking exceptions. |
| **G-06 — seven-day observation completeness** | Prove each complete Singapore day was observed per product/inventory. | **Option A approved, 3 November 2026:** attributable Manager verification after day end; seven verified previous complete days required; late discoveries invalidate affected verification and dependent outputs. |

Approved [BR-001–BR-045](OWNER_REQUIREMENTS_DECISIONS.md) and the six NFR decisions remain intact. [G-01/G-02/G-09](BATCH_INTEGRITY_OWNER_DECISIONS.md) and [G-03/G-04](CSV_GAP_OWNER_DECISIONS.md) remain as recorded. The 3 November decisions authorise no fabricated zero counts, generic damaged-stock disposal, historical `sku,change` backdating or unverified zero-demand days. G-05 retains a blocking exception; G-06's observable behaviour is resolved.

## 2. G-05 — product deactivation and stock resolution

### Approved references, ambiguity and impact

| Source | Existing approved outcome |
|---|---|
| BR-019/BR-021/BR-028/BR-040; FR-001/FR-007 | Product deactivation is soft, preserves transaction history and is a **Manager** action. No ordinary transaction may occur after deactivation. Before deactivation, every inventory in the product's business must have **zero physical stock**, including quarantine. |
| BR-002/BR-003/BR-020/BR-022; FR-004/FR-005, NFR-001/NFR-003 | Authorised ordinary issue cannot drive stock negative. Manager-only adjustment records an **actual physical count**, mandatory reason and difference. Inventory operations obey assignment and same-business access. |
| BR-029–BR-031/BR-035/BR-037; FR-004/FR-009, NFR-003/NFR-004 | Expired units are quarantined from Singapore midnight; only a Manager may dispose of quarantined units with a reason and attributable history. Quarantine/disposal/adjustment do not count as forecast demand. |
| G-09 approved Option A; NFR-003/NFR-011 | Committed stock/state and linked audit evidence succeed or roll back together; rejected operations create no committed inventory-mutation event, and actor/product attribution survives deactivation. |

The approved zero-stock precondition now has three permitted resolution operations under G-05 Option A. It still lacks a disposition for physically present damaged goods outside quarantine and returned goods without an approved movement category. A false zero count would defeat BR-003/BR-040, and concurrent receipt requires an atomic zero guard. Planning [R02 stock accuracy](../planning/RISK_REGISTER.md), [R03 concurrency](../planning/RISK_REGISTER.md) and the fixed [Requirements gate](../planning/PROJECT_SCHEDULE.md) make the remaining exception material.

### Options and trade-offs

| Option | Observable workflow | Advantage | Disadvantage / boundary |
|---|---|---|---|
| **A. Legitimate approved operations** | Resolve genuine eligible issues through authorised ordinary stock-out; correct a **verified physical discrepancy** through Manager count-and-reason adjustment; dispose of quarantined units only through Manager reasoned disposal. Check physical zero across all business inventories before Manager deactivation. | Uses existing authorised actions, preserves classification/audit and allows a real count correction. | Requires evidence that an adjustment reflects reality. Physically present nonquarantined damaged stock has no approved generic disposal route; deactivation stays blocked. |
| **B. Issue or quarantined disposal only** | Do not use adjustments as part of the deactivation-resolution workflow; require legitimate ordinary issue of eligible stock or Manager disposal of quarantined stock until all inventories are physically zero. | Simple, conservative movement paths. | Recorded phantom stock cannot be reconciled to a true zero within this workflow, despite BR-003's separate adjustment permission. A genuine discrepancy may indefinitely block deactivation. |
| **C. Guard-only deferral** | Supply no in-app resolution workflow for MVP; allow Manager deactivation only when the approved zero guard is already true through independently authorised operations. | Narrowest behaviour and no new movement classification. | Gives no operational answer for leftover stock and may strand products indefinitely; any external resolution still needs attributable, accurate records. A bounded owner deferral would be required before SRS acceptance. |

**Owner-approved Option A — recorded 3 November 2026.** A Manager may soft-deactivate only after physical on-hand is zero for the product in every business inventory, including quarantine. Authorised ordinary issue of eligible units is demand. An authorised Manager may reconcile a genuine observed discrepancy by an absolute physical count with mandatory reason and evidence of the actual count; the difference is non-demand. A zero count while units remain physically present is prohibited. Only an authorised Manager may dispose of quarantined units with mandatory reason, retained history and non-demand classification. Deactivation atomically rechecks all inventories. If a concurrent ordinary receipt commits first, deactivation fails; if deactivation commits first, the later receipt fails. Preserve product identity, movement history and attribution. The precise concurrency mechanism is Design TBD under G-11.

Returned goods and damaged goods need explicit classification before use of an operation. An actual returned, usable unit that is accepted into inventory remains physical stock; any ordinary receiving must obey the already-approved receipt rules and does not help satisfy zero until a later legitimate issue. A damaged **nonquarantined** unit still physically present cannot be made to disappear by an adjustment or ordinary issue described as disposal; no generic damaged-stock disposal action is approved. An expired unit remains quarantined and physical until an authorised Manager disposal. If physically present returned/damaged stock has no approved route, **deny deactivation** and seek a separate owner disposition; this approval does not expand BR-037 beyond quarantined units.

All-inventory checking must include inventories the requesting Manager is **not** individually assigned to; their units still block BR-040 deactivation. The Manager may perform stock resolution only in inventories they are authorised to access (BR-022); another appropriately authorised Manager may resolve other inventories. G-13 still needs the precise catalogue-level deactivation authority and assignment-change timing. Preserve the product identity and all prior movement, adjustment, disposal and actor history after deactivation. No successful deactivation may race with a stock-in to leave an inactive product holding physical units or accept a later ordinary transaction; conflict response is Design TBD under G-11.

| Approved acceptance example | Expected outcome |
|---|---|
| Product P has eligible physical 4 in inventory A and quarantined physical 2 in B. Manager is authorised for A only and requests deactivation. | Deny; both inventories count, including B. Staff cannot deactivate. No stock or lifecycle mutation is committed and no committed inventory-mutation event is created for the rejected request. |
| A legitimate authorised issue removes A's 4 eligible units. An authorised Manager for B disposes of its 2 quarantined units with a reason. | Physical stock becomes zero in both inventories; issue counts as demand, disposal does not. Distinct linked actor/quantity histories persist. A Manager with authorised catalogue scope may then deactivate P, subject to an atomic zero recheck. |
| Inventory A records 3 units but a verified physical count finds 0; a Manager authorised for A enters count 0 with mandatory reason and evidence of the actual count. | Adjustment records physical count 0 and difference −3 without demand. If every other business inventory is physically zero, deactivation may proceed. Entering 0 while 3 units are actually present is invalid as a resolution method. |
| P has one physically present, unexpired damaged unit; a Manager submits count 0 solely to deactivate. | Do not treat the count as a legitimate reconciliation or commit deactivation. No approved generic damaged-stock disposal is inferred. The owner must decide a disposition or the product stays active. |
| P has one quarantined expired unit; Staff tries disposal, then a Manager omits the reason. | Both attempts are denied without physical/lifecycle mutation. Only an authorised Manager's reasoned disposal can make that inventory physically zero (BR-037). |
| A stock-in and deactivation race while every inventory initially has zero physical stock. | At most one consistent order commits: if stock-in commits first, deactivation fails the zero guard; if deactivation commits first, later ordinary stock-in is denied. No inactive product retains new physical stock; no partial audit/lifecycle result. |
| After authorised deactivation, a user attempts ordinary manual or CSV stock-in/out and views prior history. | Ordinary mutations are denied; authorised history still identifies prior actors, product, business/inventory, reasons and quantities. Reactivation authority remains as already approved under BR-028. |

**Remaining owner responsibility:** Decide a legitimate disposition for physically present damaged goods outside quarantine and returned goods without an approved movement category, or record a formally justified bounded scope exception. Until then those units block deactivation. G-13 catalogue-level Manager authority and G-11 conflict behaviour remain open. **Design-stage details:** evidence presentation for observed counts, atomic cross-inventory guard/locking, audit/lifecycle representation, error wording and concurrency tests.

**G-05 status: OPTION A APPROVED; BLOCKING PHYSICAL-STOCK EXCEPTION.**

## 3. G-06 — seven-day observation completeness

### Approved references, ambiguity and impact

| Source | Existing approved outcome |
|---|---|
| BR-006–BR-009/BR-031/BR-037; FR-009–FR-011, NFR-004 | Demand is committed ordinary manual/negative-CSV stock-out quantity, not validated sales; stock-in, adjustments, quarantine and Manager disposal are excluded. Use the **previous seven complete Asia/Singapore calendar days**, never the current day. A reliably verified zero counts as zero; any missing/incomplete day makes the forecast and dependent recommendation unavailable. Display average to two decimals but calculate downstream with full precision. |
| BR-021/BR-022; FR-009–FR-011, NFR-001 | Manager and Staff may view assigned-inventory forecasts/reorder advice. G-06 Option A, approved 3 November 2026, authorises only a same-business Manager assigned to the inventory to verify that product/inventory day after the Singapore day ends. Staff cannot verify. |
| G-04/G-09 approved Options A; FR-006/FR-009, NFR-003/NFR-011 | A successful negative CSV row is an attributable committed demand movement linked to an import; failed rows and stock corrections are not demand. The CSV header remains `sku,change` and contains **no occurrence-date field**. |

An empty movement list cannot distinguish verified zero from missing observation. G-06 Option A fixes the observable per-day verification and unavailability rule; coverage representation and correction concurrency still require Design. Planning [R05 forecast accuracy](../planning/RISK_REGISTER.md) and [R02 movement integrity](../planning/RISK_REGISTER.md) remain relevant; the [feasibility assessment](../planning/FEASIBILITY_ASSESSMENT.md) does not claim a working Tory forecast.

### Options and trade-offs

| Option | Observable coverage rule | Advantage | Disadvantage / boundary |
|---|---|---|---|
| **A. Explicit product/inventory/day verification** | Each previous Singapore day has a per-product/per-inventory status such as unverified or verified complete, including a verified zero-demand total, with attributable verifier/time and source evidence. | Directly testable; a missing day cannot silently become zero; clear availability explanation. | Daily verification effort and records grow with products/inventories; a trustworthy verification procedure is still needed. |
| **B. Continuous event-log coverage** | Prove an opening date for product/inventory observation and uninterrupted capture across each complete day; derive zero from proven log coverage, not from absence of movements alone. | Less per-product manual attestation once operational evidence is reliable. | Hard to prove no gaps, outages or missed manual events in a small MVP; log existence alone does not prove physical transactions were entered. |
| **C. Bounded hybrid** | Verify per-inventory/day operational log coverage, then require per-product exception or zero confirmation only where product-level evidence is uncertain. | May reduce daily per-product attestations while retaining explicit exceptions. | More conditional rules and evidence reconciliation; a missed product-level issue may still be hidden by an inventory-wide “healthy” day. |

**Owner-approved Option A — recorded 3 November 2026.** For each product, inventory and complete Asia/Singapore calendar day, retain attributable complete/unverified observation status. Only an authorised Manager may verify after that day ends. A verified day with no eligible stock-out contributes zero. Any unverified/incomplete day makes the previous-seven-complete-day forecast and dependent recommendation unavailable. Reverification follows correction of a missing or late transaction; until then affected verification and dependent outputs are invalid. Preserve full internal calculation precision and display the average to two decimal places. Timestamp-free `sku,change` CSV movements use the successful import/commit timestamp; historical backdating through this contract is prohibited. Quarantine, adjustment and disposal are non-demand. Coverage representation, UI and invalidation mechanism belong to Design.

A product/inventory cannot borrow another product's or inventory's verification. A day without eligible issues contributes zero only if its full Singapore-day observation is verified after day end. Missing movement evidence or a later discovery invalidates that day and dependent output until correction and reverification. Start-of-observation treatment for newly created products/inventories requires Design evidence that a complete day was observed; no pre-opening day is silently treated as zero.

For ordinary and negative-CSV issues, use attributable committed movement evidence and its Asia/Singapore calendar date. The approved `sku,change` CSV has no occurrence-date field: its negative rows use the successful import/commit timestamp and cannot backdate demand. A late-discovered historical issue invalidates its affected day, and a physical-count adjustment cannot be counted as demand. Historical correction representation and concurrent reverification are Design details; the approved observable requirement is unavailability until correction and reverification.

| Approved acceptance example | Expected outcome |
|---|---|
| Product P in inventory I has seven previous complete Singapore dates, with verified daily issue quantities `[1,0,1,0,1,0,0]`; each zero has affirmative coverage evidence. | Forecast is available: total 3, full-precision average `3/7`, displayed `0.43`. The dependent recommendation may use `3/7` without intermediate rounding. |
| Same seven dates, but one no-movement day has no verified coverage status. | Forecast and dependent recommendation are unavailable; absence of a stock-out row is not treated as verified zero. |
| Product P is newly created in inventory I while another inventory has older P history. | I cannot borrow the other inventory's coverage. Forecast remains unavailable until seven prior complete Singapore days for P/I are verified after their respective day ends. |
| At 00:00 Asia/Singapore on 8 November, inspect the forecast window; an issue commits at 7 November 23:59:59 and another at 8 November 00:00. | Window is 1–7 November complete days. The first issue belongs to 7 November; the second belongs to current 8 November and is excluded. Coverage for each prior day still must be verified. |
| A negative `sku,change` CSV issue commits successfully at 00:01 on 8 November; file contains no date field. | Its demand belongs to 8 November, not 7 November, and cannot change the 1–7 November window. A failed CSV contributes no demand; historical backdating is prohibited. |
| A 5 November issue is discovered missing after a previously available forecast was shown. | Mark 5 November incomplete/unverified; prior computed output is stale and no current numeric forecast/recommendation is shown until historical correction and coverage are properly reverified. Do not treat a Manager stock adjustment as demand. |
| Seven complete verified days include quarantine, an adjustment and Manager disposal but no ordinary issues. | All seven demand values are verified zero; excluded movements add zero demand. Forecast may display `0.00` only because daily coverage is verified. |

**Approved observable outcome:** A missing or late transaction invalidates the affected day's verification and dependent forecasts/recommendations until records are corrected and the authorised Manager reverifies the day. **Design-stage details:** coverage data representation, daily verification UI, timestamp source/timezone conversion, invalidation and recomputation mechanism, retention and concurrent correction handling. G-09 audit, G-11 atomicity and G-17 other recommendation questions remain open.

**G-06 status: OPTION A APPROVED; REQUIREMENTS BEHAVIOUR RESOLVED, DESIGN VERIFICATION OPEN.**

## 4. Owner decision record and gate boundary

| Gap | Owner selection or bounded deferral | Responsible role / target stage / verification evidence | Status |
|---|---|---|---|
| G-05 | Option A approved; recorded 3 November 2026 | Owner: damaged/nonquarantined and unclassified returned-stock disposition or justified bounded exception; Design: evidence and atomic guard; Test: stock/race criteria | **BLOCKING exception; partial disposition** |
| G-06 | Option A approved; recorded 3 November 2026 | Design: coverage and invalidation representation; Test: seven-day, late correction, midnight and CSV timestamp criteria | **Requirements behaviour resolved; Design verification open** |

The [Requirements review](REQUIREMENTS_REVIEW.md) and [gap analysis](REQUIREMENTS_GAP_ANALYSIS.md) reflect these dispositions. G-05's physical-stock exception still requires owner disposition before SRS acceptance. The complete SRS, Requirements exit and Design entry remain pending.
