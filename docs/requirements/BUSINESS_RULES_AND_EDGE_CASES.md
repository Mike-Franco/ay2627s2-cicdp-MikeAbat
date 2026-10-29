# Tory Business Rules and Edge Cases

**Status:** Proposed rules for owner decision. The approved Planning baseline fixes capabilities but does not approve the detailed rules below. The isolated PoC contract is cited as evidence, not automatically promoted to a production requirement.

| Topic | Proposed rule / edge-case behavior | Status and owner choice |
|---|---|---|
| Product identifier / SKU | SKU is required, non-empty, trimmed and unique among active products. Propose case-insensitive uniqueness after normalization; preserve user-entered display form. | **PROPOSED.** Confirm case sensitivity, allowed characters, length, mutability and reuse after deactivation. PoC uses unique `sku` but does not establish final lifecycle policy. |
| Product lifecycle | Prefer deactivation rather than hard deletion once any stock movement exists. | **PROPOSED.** Product create/edit/deactivate operations and history implications need approval. |
| Quantity representation | On-hand is a whole-number unit count; fractional quantities are rejected unless the product/unit model is expanded by approval. | **PROPOSED.** Confirm unit-of-measure and maximum quantity. PoC uses a PostgreSQL nonnegative integer field, but this is not the approved production schema. |
| Stock-in | Accept a positive quantity; add it atomically to current on-hand. Zero, negative and nonnumeric inputs are rejected. | **PROPOSED detail** supporting confirmed manual stock-in. Confirm whether correction/reversal is a separate movement. |
| Stock-out | Accept a positive requested quantity; subtract atomically. Proposed behavior rejects an operation that would make stock negative. | **PROPOSED.** Confirm whether emergency negative stock is ever permitted and who can override. |
| Stock adjustment | Propose absolute-count adjustment: user enters counted quantity, system records delta from prior on-hand. Require a reason and proposed Manager permission. | **PROPOSED.** Alternative is signed delta; owner must choose semantics, actor permission, reason codes and whether Staff can request/perform adjustments. |
| Concurrent requests | Serialize or otherwise protect concurrent updates so accepted movements preserve the approved balance rule. Rejected conflicts must not partially apply. | Correctness need is **PROPOSED detail**; PoC observed one specific stock-out concurrency scenario only. Define broader conflicts/deadlock/retry policy in Design. |
| Duplicate manual request | Avoid accidental double-application on retry/double-submit. Propose a unique request identifier for an operation and return the prior outcome on a recognized retry. | **PROPOSED.** Confirm whether UI retries, network retries and manual repeated submissions should be deduplicated; no PoC evidence for this. |
| CSV file header/encoding | Propose UTF-8 text with exact first row `sku,change`; header order and case exact, matching PoC input contract. | **PROPOSED.** Confirm UTF-8 BOM behavior, delimiter/quote rules, newline handling and whether header contract is frozen. |
| CSV row values | Propose exactly two columns; SKU must identify an existing product; `change` is a signed, non-zero base-10 integer; whitespace/blank rows and extra columns rejected. Repeated SKUs processed in file order. | **PROPOSED**, informed by PoC implementation. Confirm whitespace, signs, leading zeros, blank lines and duplicate-SKU semantics. |
| CSV atomicity | Any invalid row or execution/database failure rejects the entire batch; no transaction from that batch remains committed. | Whole-batch rejection is **CONFIRMED baseline**. Exact error aggregation and validation sequence are **PROPOSED**. Test rollback at beginning, middle and final row in formal Testing. |
| Empty/header-only CSV | Propose reject a header-only file because there is no transaction to import. | **PROPOSED PoC assumption**, not an approved product rule. |
| Duplicate CSV submission | Propose detect identical file re-submission and prevent accidental second application. | **TBD.** Requires batch identity/hash and retention rule; may be outside scope. Do not assume idempotency currently exists. |
| CSV size/limits | Define a maximum file size and row count before implementation. | **TBD.** Must fit staging memory/time and student project constraints; no number is approved. |
| Forecast window | Propose the seven complete calendar days immediately preceding the calculation date, using a business timezone selected by owner. Daily average = sum of eligible demand quantities / 7. | Seven-day moving average is **CONFIRMED baseline**; calendar-day boundaries/timezone/formula interpretation are **PROPOSED**. |
| Demand source | Propose count only explicit demand/issue stock-out movements; exclude stock-in and adjustment movements. A generic stock-out may not equal customer demand. | **TBD / blocking.** Owner must identify source data and approve whether manual stock-out is a demand proxy. Existing PoC does not record a movement ledger or demand series. |
| Zero-demand days | Treat a day as zero only if the approved source confirms that day was observed and there were no eligible demand events. | **PROPOSED.** Confirm source completeness semantics. |
| Missing/incomplete days | Propose show forecast as unavailable when any of the seven days lacks reliable coverage, instead of silently imputing zero. | **PROPOSED.** Owner may approve an imputation or partial-window policy; explain it if chosen. |
| Insufficient history | Propose no numeric forecast until a complete approved seven-day window exists. | **PROPOSED.** Confirm whether partial history is permitted and how it is labelled. |
| Forecast rounding | Propose retain full precision for calculations and display the daily average to two decimal places. | **PROPOSED.** Confirm display precision; never round intermediate values before reorder calculation. |
| Supplier lead time | Propose positive whole calendar days per product. No holiday/business-day calendar is assumed. | **PROPOSED.** Confirm minimum, units (calendar/business days), zero-day suppliers and whether lead time changes historically affect prior recommendations. |
| Safety stock | Propose nonnegative whole units per product. | **PROPOSED.** Confirm integer/fraction support and whether zero is valid. |
| Reorder formula | Candidate: reorder point = (seven-day average daily demand × lead-time days) + safety stock. Recommend quantity = `max(0, ceil(reorder point − current on-hand))`; display every input and intermediate value. | **PROPOSED.** Confirm whether recommendation appears at `on-hand ≤ reorder point`, how inbound stock/pending orders are treated, and whether supplier minimum/pack quantities apply. |
| Additional reorder settings | “Reorder settings” may include minimum order quantity, pack size, review period or target quantity. | **TBD.** Do not add fields until owner selects required settings. Automatic purchasing remains excluded. |
| Recommendation action | Recommendation is informational; no purchase order or supplier communication is created. | Automatic purchasing is excluded by current scope. Confirm any later change through formal change control. |

## Edge-case acceptance examples to approve

1. Stock-out exactly equal to available stock; one unit over available stock; repeated concurrent stock-outs.
2. Adjustment below zero, adjustment to zero, and adjustment with missing reason if reasons are approved.
3. CSV valid rows around an invalid row; unknown SKU; repeated SKU; repeated whole file; malformed quotes; empty/header-only file; UTF-8 BOM; maximum size boundary.
4. Forecast all-zero fully observed week; one missing day; no history; demand transaction at day boundary; adjustment in window; lead time zero/one; reorder quantity fractional before ceiling.
5. Product SKU case/space variations and attempts to rename/deactivate a product with movements.

No example in this document constitutes a completed test or approved rule. The owner must accept the chosen rules, and the resulting requirements must be traceable to the SRS before Design.
