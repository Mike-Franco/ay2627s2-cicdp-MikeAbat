# TORY-15: Stock Receiving and Allocation Decision Preparation

**Prepared:** 5 November 2026

**Status:** Proposed Design preparation; no new owner decision is recorded. The full SRS and Requirements exit remain not approved.

**Purpose:** Prepare the TORY-16 manual batch-receiving slice without changing approved rules or implementing stock behavior.

## Approved baseline and scope reconciliation

| Source | Binding outcome for this work |
|---|---|
| G-01 Option A, approved 1 November 2026; BR-033/BR-034 | For one product and inventory, eligible dated batches order by expiry date, committed receiving sequence, then stable batch ID. Undated batches follow dated batches and order by committed receiving sequence, then stable ID. This is settled behavior; TORY-15 does not reopen it. |
| G-03 Option A, approved 1 November 2026; BR-032/BR-034/BR-036 | Each valid positive CSV row for a non-expiry-tracked product creates a separate eligible undated batch in file order. Manual and CSV undated receipts share the order. Positive CSV rows for expiry-tracked products remain prohibited. TORY-16 is manual receiving; CSV remains out of scope. |
| G-02 Option A, approved 1 November 2026; BR-029/BR-032/BR-035/BR-037 | Expiry makes remaining units unavailable at 00:00 Asia/Singapore on the expiry date, regardless of delayed status/evidence recording; physical stock remains until an authorized movement. One system-attributed boundary event is required. Maximum evidence-recording delay remains **blocking and undecided**. |
| G-05 Option A, approved 3 November 2026; BR-019/BR-028/BR-037/BR-040 | Deactivation requires an atomic zero-physical-stock recheck across every business inventory. Legitimate issue, genuine evidenced Manager count adjustment, and reasoned Manager disposal of quarantined units have their approved classifications. Damaged non-quarantined goods and returned goods without an approved movement category remain unresolved and block deactivation. G-13 authority and G-11 mechanism remain open. |
| G-09 Option A, approved 1 November 2026; NFR-003/NFR-011 | Each committed inventory mutation has one attributable logical event linked to affected batches/source and relevant quantities/classification; stock and event commit or roll back together. Rejected attempts create no committed inventory-mutation event. Separate rejected-attempt security/error logging remains **blocking and undecided**. |
| BR-020/BR-021/BR-022/BR-028/BR-032/BR-036 and Role Permission Matrix | Manager and Staff may stock-in only within an assigned inventory in their own business. Quantities are whole base units. No ordinary transaction is allowed for a deactivated product. Expiry is per batch; products not tracked for expiry may omit it, while expiry-tracked products require manual receiving details. |

**Jira/repository alignment:** TORY-15's Jira wording asks to resolve equal-date ties and non-expiry receiving; those behaviors are already approved by G-01/G-03 and must not be reopened. TORY-16's current Jira description cites BR-003/BR-020/BR-032 but manual receipt also depends on BR-021/BR-022/BR-028/BR-036 and G-01/G-03/G-09. BR-003 is a Manager-only absolute physical-count adjustment; it does not authorize stock receipt and must not narrow BR-021's Manager/Staff receipt permission. This is a scope/reference contradiction to correct through the normal Jira refinement, but Jira was not changed. In the repository, TORY-13 implements Product and InventoryProduct only. There is no product active or expiry-tracking field, receiving-batch entity, committed receipt sequence, stock balance, or audit-event entity. TORY-16 must design the minimum required state before implementation. The implemented-only ERD remains unchanged.

## Proposed first receipt slice — NOT APPROVED

For an authenticated active Manager or Staff member, accept a manual receipt only for an inventory in the same business with a current active assignment, and a product currently active and linked to that inventory. Recheck authorization in the write transaction. Accept a positive whole-number quantity in base units, with no package conversion. For an expiry-tracked product require a valid calendar expiry date. BR-032 says expiry is optional for products not tracked for expiry; whether a manual receipt for such a product may include a date remains unresolved. Create one stable batch identity and one committed receiving sequence in the product/inventory ordering scope. Create exactly one attributable receipt audit event in the same PostgreSQL transaction, with G-09 actor/system, business, inventory, product, action/time, affected batch/source, quantity change or before/after, and classification evidence. Any validation, authorization, batch, sequence or audit failure leaves no receipt mutation committed.

This describes required observable behavior, not an approved schema or UI. `Product.is_active`, an expiry-tracking indicator, batch identity/sequence fields and audit records do not exist in TORY-13. A boolean active field and product-level expiry-tracking value are **provisional representation candidates** derived from BR-028/BR-032, not owner-approved schema choices. InventoryProduct existence currently represents a link; it has no independent active flag.

The following input rules need owner direction or explicit bounded disposition before TORY-16 acceptance is finalized:

- **Base-unit label and packaging:** BR-020 approves whole base units, not a product-specific label or package conversion. Proposed MVP boundary: enter base-unit integers only and do not convert packs. Owner must decide how the base unit is named/displayed, or approve a bounded generic label. No conversion is inferred.
- **Quantity maximum:** no business maximum is approved. A database integer type has a technical range, which is not a business limit. Owner must accept a stated storage ceiling or choose a smaller business validation bound; no value is selected here.
- **Already-expired receipt:** BR-035 makes a batch unavailable starting at midnight on its expiry date, but no rule says whether a newly submitted receipt whose expiry date is today or earlier is rejected, accepted directly as quarantined physical stock, or handled another way. Owner decision required; do not silently accept it as available.
- **Date on a non-expiry-tracked product:** BR-032 makes expiry optional for these products, while G-03 fixes non-tracked positive CSV receipts as undated. Whether a manual non-tracked receipt may include an expiry date, and if so whether that makes it dated for G-01 ordering, needs owner direction. The initial undated-only boundary is **PROPOSED**, not approved.
- **Repeat manual submission:** no duplicate/idempotency policy for manual receipts is recorded. BR-041 covers only byte-identical successful CSV imports per inventory. Owner decision required on whether a repeated submit is a second receipt or the same request; do not apply CSV duplicate semantics to manual receipts.

## Proposed PostgreSQL transaction and locking protocol — NOT APPROVED

Use the business-owned **Product row as the shared anchor** for all receipt operations for that product and any future cross-inventory deactivation. A proposed sequence is:

1. Authenticate, enforce CSRF, validate basic form syntax and perform an initial authorization check before taking locks. Do not reveal product/inventory details to an unauthorized caller.
2. Start `transaction.atomic()` and lock the Product row `FOR UPDATE`. This serializes compliant receipt writers for the same product across inventories and gives future deactivation one row to lock before checking every business inventory.
3. After the Product lock, recheck the active account/membership, same-business inventory, and active assignment. Lock the membership and the applicable assignment row through commit, in a consistent order, so a concurrent assignment change either commits before the recheck or waits until after the receipt. The observable point at which assignment revocation takes effect is a G-13 decision; the locking behavior here is proposed.
4. Lock/confirm the Inventory and InventoryProduct association in a globally consistent order. The current TORY-13 association trigger locks Inventory then Product on link insert/update. That order can deadlock with a Product-first receipt if a link update holds the association/inventory path while waiting on Product. Before using Product as the anchor, TORY-16 Design must reconcile the existing trigger and all association mutations to one Product-before-Inventory order, or prove another protocol that avoids this cycle. Do not claim the current trigger order is already compatible.
5. Read one authoritative server time after lock acquisition, convert it to Asia/Singapore for expiry-date decisions, and validate expiry against that instant. Prefer obtaining the timestamp from PostgreSQL so lock wait does not make an application-captured time stale. Exact clock source and already-expired handling remain to be decided.
6. While Product remains locked, allocate the next sequence for that product/inventory and create the receiving batch plus exactly one receipt event. A proposed simple allocation is `MAX(sequence)+1` under the Product lock, with a uniqueness constraint on product, inventory and sequence. All manual/CSV receipt writers must use the same lock. The lock serializes allocation for the product; it does not itself guarantee correct authorization, audit fields, batch validity or stockout allocation.
7. Commit batch and receipt event together. On any exception, roll back the entire transaction. PostgreSQL lock waits serialize same-product work; avoid automatic replay after timeout/deadlock until manual duplicate-submission semantics are decided. A retry must start a fresh transaction and reauthorize. No timeout or retry count is approved.

The Product lock protects only operations that acquire it and hold it through commit. Future ordinary stock-out and every deactivation path must use the same anchor if they can change/check physical stock. Deactivation must lock Product before checking all inventories; then either receipt commits first and the zero-stock check fails, or deactivation commits first and a later receipt sees inactive state and fails. The Product lock does not alone protect assignment freshness, InventoryProduct link removal, stock arithmetic, noncompliant direct SQL, or audit atomicity. Those need their own row locks/constraints and transaction tests. Sequence numbers allocated inside the transaction roll back with failed receipts; committed sequence order is the receiving order, not a promise of gapless IDs if a database sequence is chosen instead.

## Open decisions and bounded deferrals

### Before TORY-16 acceptance

- Define base-unit label/input and any quantity bound, including whether the storage range alone is acceptable (**G-12**).
- Decide treatment of expiry dates already expired at submission and the product-level expiry-tracking representation (**BR-032/BR-035/BR-036**; representation is Design, acceptance behavior is owner direction).
- Decide manual duplicate submission behavior. No approval exists for idempotency or for treating identical submissions as distinct receipts.
- Confirm assignment recheck/effective timing and lifecycle representation needed to reject inactive products (**G-13/BR-028**). A bounded proposal is to keep deactivation out of TORY-16 while still providing an approved active-state check; this requires agreement that the state representation is sufficient and does not implement deactivation.
- Specify receipt audit fields using approved G-09 coverage and confirm audit failure rolls the batch back. The committed receipt event remains in TORY-16; it is not deferred to TORY-20.
- Reconcile TORY-13's InventoryProduct trigger lock order before adopting Product-first locking (**G-11**).

### Later blockers and proposed bounded deferrals — NOT APPROVED

- **G-02:** maximum delay for expiry-boundary evidence remains blocking. TORY-16 may record expiry dates and the receipt event, but a proposed bound is to decide the delay before implementing expiry quarantine transitions in the expiry/history increment (TORY-20 or its predecessor). This does not defer the approved Singapore-midnight availability rule or claim G-02 closed.
- **G-05:** damaged non-quarantined and unclassified returned physical stock remain unresolved; deactivation must remain unavailable while such units are present. The mandatory disposal reason's exact format also remains open. Resolve before implementing deactivation/disposal; no generic write-off is proposed. Do not use a fake product flag to claim deactivation is complete.
- **G-09:** keep the approved committed receipt event in TORY-16 and ensure rejected requests create no committed inventory-mutation event. A bounded proposal is to decide separate rejected-attempt security/error logging before the security/audit acceptance gate or deployment; owner acceptance is required, and G-09 remains blocking until then.
- **TORY-17:** implement and verify FEFO/FIFO allocation, equal-expiry sequence/ID ties, dated-before-undated ordering, shortages, nonnegative stock, and competing stock-out races. G-01 ordering is approved; no allocation implementation belongs in TORY-16.
- **TORY-20 and other stock work:** implement authorized balance/history views, durable movement/audit history, expiry transition evidence and any disposal/deactivation workflow at their own scope. Preserve the G-02 delay and G-05 physical-stock blockers. Other open CSV, forecast and G-11 concurrency cases remain with their dependent increments.

## Acceptance test plan

| Scenario | TORY-16 receipt test or later test | Expected result |
|---|---|---|
| Assigned Manager and assigned Staff receive a valid linked active product | TORY-16; PostgreSQL | One batch with stable identity and committed sequence, correct inventory/product/actor, and exactly one committed receipt event. |
| Zero, negative, fractional or malformed quantity; missing/invalid expiry for tracked product | TORY-16 | Reject without batch, sequence reservation, balance change or committed receipt event. Quantity bound and already-expired-date cases wait for owner direction. |
| Manual receipt for non-expiry-tracked product omits or supplies an expiry date | TORY-16 acceptance boundary | Omitted date yields the approved undated case. Supplied-date behavior and ordering require owner disposition; do not assume it is rejected or changes tracking status. |
| Wrong-business inventory, unassigned inventory, inactive product, or product not linked to selected inventory | TORY-16 | Deny without disclosing foreign data or committing receipt records. Direct URL/form ID substitution does not bypass server authorization. |
| Receipt audit insert fails after batch creation | TORY-16; PostgreSQL transaction test | Batch, sequence allocation and any balance change roll back; no committed receipt event remains. |
| Two PostgreSQL connections receive the same product into one or different assigned inventories concurrently | TORY-16; barrier-controlled integration test | Both valid receipts may commit; their per-product/inventory committed sequences are unique and ordered; each has exactly one linked receipt event. A serialization/deadlock error leaves no partial receipt. |
| Two PostgreSQL connections race a final stock issue or one-unit allocation | TORY-17 | Exactly one eligible issue commits; no negative balance, double allocation or partial audit. Not a TORY-16 acceptance test. |
| Equal-expiry dated batches; dated versus undated batches; multiple undated receipts | TORY-17 allocation | Confirm approved G-01/G-03 order: earliest expiry, committed sequence, stable ID; all dated before undated; undated sequence then stable ID. TORY-16 only persists the inputs needed for this ordering. |
| Receipt races future all-inventory product deactivation | Deactivation increment (TORY-20 or predecessor), G-05/G-11 | Receipt-first makes the zero-stock guard fail; deactivation-first rejects receipt; no inactive product gains physical stock. Not implemented or accepted by TORY-16 alone. |
| Expiry boundary transition, delayed system evidence, disposal-before-transition, history and rejected-attempt security logging | Expiry/history and security increments; G-02/G-05/G-09 | Test approved observable outcomes after delay/reason/logging disposition; keep these separate from the committed manual receipt event test. |

No tests or stock implementation are claimed by this decision-preparation note.
