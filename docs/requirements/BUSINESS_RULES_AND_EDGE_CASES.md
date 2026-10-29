# Tory Business Rules and Edge Cases

**Status:** [BR-001–BR-011](OWNER_REQUIREMENTS_DECISIONS.md) were individually approved by the owner on 29 October 2026. Other details remain proposed/TBD. The isolated PoC is historical evidence, not a product-rule approval.

| Topic | Proposed rule / edge-case behavior | Status and owner choice |
|---|---|---|
| Product identifier / SKU | Require SKU; trim leading/trailing spaces; enforce case-insensitive uniqueness among active products. | **APPROVED BR-001.** Renaming/reuse, length, character set and display form TBD. |
| Product lifecycle | Prefer deactivation rather than hard deletion once any stock movement exists. | **PROPOSED.** Product create/edit/deactivate operations and history implications need approval. |
| Quantity representation | On-hand cannot be negative. Whole-unit precision is proposed. | **No-negative invariant APPROVED BR-002.** Unit/precision/maximum TBD. PoC schema is not the product schema. |
| Stock-in | Accept a positive quantity; add it atomically to current on-hand. Zero, negative and nonnumeric inputs are rejected. | **PROPOSED detail** supporting confirmed manual stock-in. Confirm whether correction/reversal is a separate movement. |
| Stock-out | Reject a stock-out that would make on-hand negative without partial mutation. Every committed stock-out counts as demand, including a negative CSV change. | **APPROVED BR-002, BR-006.** This is a proxy, not validated customer sales. Actor and quantity precision TBD. |
| Stock adjustment | Manager enters absolute physical count and reason; record `new count − prior on-hand`; adjustment does not count as demand. | **APPROVED BR-003, BR-006.** Reason format and record retention TBD. |
| Concurrent requests | Serialize or otherwise protect concurrent updates so accepted movements preserve the approved balance rule. Rejected conflicts must not partially apply. | Correctness need is **PROPOSED detail**; PoC observed one specific stock-out concurrency scenario only. Define broader conflicts/deadlock/retry policy in Design. |
| Duplicate manual request | Avoid accidental double-application on retry/double-submit. Propose a unique request identifier for an operation and return the prior outcome on a recognized retry. | **PROPOSED.** Confirm whether UI retries, network retries and manual repeated submissions should be deduplicated; no PoC evidence for this. |
| CSV file header/encoding | Stock-transaction CSV uses `sku,change`. | **APPROVED BR-004.** Exact encoding, BOM, whitespace, quote/newline and row-limit rules TBD. |
| CSV row values | Propose exactly two columns; SKU must identify an existing product; `change` is a signed, non-zero base-10 integer; whitespace/blank rows and extra columns rejected. Repeated SKUs processed in file order. | **PROPOSED**, informed by PoC implementation. Confirm whitespace, signs, leading zeros, blank lines and duplicate-SKU semantics. |
| CSV atomicity | Invalid row or failure rejects the entire batch with no partial mutation. Committed negative changes count as demand; rejected-batch rows do not. | **APPROVED BR-004, BR-006.** Error aggregation/validation order TBD. |
| Empty/header-only CSV | Reject empty and header-only uploads. | **APPROVED BR-004.** Whitespace-only row treatment TBD. |
| Duplicate CSV submission | Reject identical re-upload after a previously successful import; do not apply twice. | **APPROVED BR-005.** Identity, hashing, retention and concurrency safeguards TBD. A failed prior upload does not satisfy the success condition. |
| CSV size/limits | Define a maximum file size and row count before implementation. | **TBD.** Must fit staging memory/time and student project constraints; no number is approved. |
| Forecast window | Previous seven complete Asia/Singapore calendar days; exclude current day. Average = eligible demand total / 7. | **APPROVED BR-007.** Requires trustworthy dated movements. |
| Demand source | Every committed manual/negative-CSV stock-out counts; stock-in and adjustments excluded. | **APPROVED BR-006.** Proxy, not validated sales; source retention/coverage TBD. |
| Zero-demand days | Count verified, reliably observed zero-demand day as zero. No records alone cannot prove coverage. | **APPROVED BR-008.** Coverage evidence method TBD. |
| Missing/incomplete days | Forecast unavailable if any of seven days is unobserved or incomplete. | **APPROVED BR-008.** No silent zero imputation. |
| Insufficient history | Require seven complete, reliably observed days. | **APPROVED BR-008.** Availability message/detail TBD. |
| Forecast rounding | Show average daily demand to two decimals; use full precision for calculations without intermediate rounding. | **APPROVED BR-009.** |
| Supplier lead time | Positive whole calendar days per product. | **APPROVED BR-010.** Other supplier-setting policy TBD. |
| Safety stock | Propose nonnegative whole units per product. | **PROPOSED.** Confirm integer/fraction support and whether zero is valid. |
| Reorder formula | Reorder point = average daily demand × lead-time days + safety stock; suggested quantity = `max(0, ceil(reorder point − current on-hand))`. Show inputs and calculation. | **APPROVED BR-011.** Inventory on order, trigger semantics, safety-stock constraints and minimum/pack size TBD. |
| Additional reorder settings | “Reorder settings” may include minimum order quantity, pack size, review period or target quantity. | **TBD.** Do not add fields until owner selects required settings. Automatic purchasing remains excluded. |
| Recommendation action | Recommendation is informational and creates no purchase order. | **APPROVED BR-011.** Supplier communication remains outside approved scope. |

## Edge-case acceptance examples to approve

The following deterministic examples apply approved rules; they are proposed acceptance cases, not executed tests. Assume every listed day has independently verified complete observation coverage.

| Case | Input | Expected outcome |
|---|---|---|
| Verified zero and two-decimal display | For 1–7 November 2026 (Asia/Singapore), daily stock-out demand is `[1, 0, 1, 0, 1, 0, 0]`; zero days have verified coverage. | Total `3`; unrounded average `3/7`; displayed average `0.43`. The zero days count as zero (BR-007–BR-009). |
| Missing coverage | Same series, but 3 November lacks reliable observation coverage, even if no stock-out record exists. | Forecast and dependent recommendation are unavailable; do not substitute zero (BR-008). |
| Singapore midnight | At 8 November 2026 00:00 Asia/Singapore, window is 1 November 00:00 through 7 November 23:59:59… local time. | A stock-out at 7 November 23:59 is included; at 8 November 00:00 is excluded; at 31 October 23:59 is excluded (BR-007). |
| No intermediate rounding | For the verified `3/7` average above, lead time `7` days, safety stock `0` and on-hand `0`. | Reorder point `(3/7) × 7 + 0 = 3`; suggested quantity `3`. Using displayed `0.43` would incorrectly yield `ceil(3.01) = 4` (BR-009–BR-011). The safety-stock value is an example input, not approval that zero is permitted. |

These cases require dated stock movement evidence and a trustworthy indication that each day was observed. The observation mechanism and database schema belong to later decisions.

1. Stock-out exactly equal to available stock; one unit over available stock; repeated concurrent stock-outs.
2. Adjustment below zero, adjustment to zero, and adjustment with missing reason if reasons are approved.
3. CSV valid rows around an invalid row; unknown SKU; repeated SKU; repeated whole file; malformed quotes; empty/header-only file; UTF-8 BOM; maximum size boundary.
4. Forecast all-zero fully observed week; one missing day; no history; demand transaction at day boundary; adjustment in window; lead time zero/one; reorder quantity fractional before ceiling.
5. Product SKU case/space variations and attempts to rename/deactivate a product with movements.

No example is an executed test. The eleven approved rules are recorded separately; remaining details require owner disposition before Requirements exit.
