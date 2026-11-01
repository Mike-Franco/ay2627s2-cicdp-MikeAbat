# Tory Business Rules and Edge Cases

**Status:** [BR-001–BR-033](OWNER_REQUIREMENTS_DECISIONS.md) are individually approved. BR-012–BR-025 are supplementary owner-provided ChatGPT Requirements review approvals documented 1 November 2026; their original approval timestamp was not supplied. BR-034 onward have no implied approval. Other details remain proposed/TBD. The isolated PoC is historical evidence, not a product-rule approval.

| Topic | Proposed rule / edge-case behavior | Status and owner choice |
|---|---|---|
| Product identifier / SKU | Require SKU; trim leading/trailing spaces; enforce case-insensitive uniqueness among active products and within a business. | **APPROVED BR-001/BR-017.** BR-001's active qualifier and BR-017's business-wide uniqueness leave inactive-SKU reuse unresolved. Renaming, length, character set and display form TBD. |
| Catalogue and inventories | One shared product catalogue per business with separate inventory records; selling prices are inventory-specific. | **APPROVED BR-016/BR-018.** Inventory identity, catalogue-level authorization, price format/maintenance TBD. |
| Product lifecycle | Soft-deactivate products and preserve transaction history. Managers may create/edit/deactivate (BR-021) and reactivate (BR-028). Resolve remaining stock before deactivation; no ordinary transactions afterward. | **APPROVED BR-019/BR-021/BR-028.** BR-019 alone does not name the actor. Exact stock-resolution workflow and ordinary-transaction classification TBD. |
| Staff deactivation and history | Managers may deactivate Staff accounts, revoke access and retain attributable history. | **APPROVED BR-026.** Provisioning, reactivation, active-session timing and retention method TBD. |
| Staff inventory assignment | A Manager assigns Staff only to inventories that Manager is authorized to manage within the same business. | **APPROVED BR-027.** Assignment lifecycle, scope changes and concurrent authorization checks TBD. |
| Quantity representation | On-hand cannot be negative; quantities use whole-number base units. | **APPROVED BR-002/BR-020.** Packaging conversion, maximum and migration of any fractional history TBD. PoC schema is not the product schema. |
| Stock-in and receiving batches | Record expiry per receiving batch; expiry is optional for products not tracked for expiry. Positive-quantity validation is proposed. | **APPROVED BR-032** for expiry handling. Batch identity, tracking transitions and correction/reversal TBD. |
| Ordinary stock-out | Reject a stock-out that would make on-hand negative without partial mutation. Committed ordinary manual and negative-CSV issues count as demand; quarantine/disposal do not. | **APPROVED BR-002, BR-006, BR-031.** Proxy, not validated sales. Actor, quantity precision and movement classification TBD. |
| Expired batches | Quarantine expired batches; exclude them from ordinary issue. | **APPROVED BR-029.** Exact expiry boundary and quarantine implementation TBD. |
| Batch allocation | Automatically consume eligible batches by earliest expiry (FEFO). | **APPROVED BR-033.** Ties, no-expiry ordering, transaction/CSV allocation and concurrency TBD. |
| Stock adjustment | Manager enters absolute physical count and reason; record `new count − prior on-hand`; adjustment does not count as demand. | **APPROVED BR-003, BR-006.** Reason format and record retention TBD. |
| Concurrent requests | Preserve stock balance, eligibility, FEFO order and authorization under simultaneous issues, quarantine, deactivation and Staff assignment. | Correctness need follows BR-002/BR-026–BR-033; exact locking, conflict and retry policy **TBD**. PoC observed only one stock-out concurrency scenario. |
| Duplicate manual request | Avoid accidental double-application on retry/double-submit. Propose a unique request identifier for an operation and return the prior outcome on a recognized retry. | **PROPOSED.** Confirm whether UI retries, network retries and manual repeated submissions should be deduplicated; no PoC evidence for this. |
| CSV file header/encoding | Stock-transaction CSV uses `sku,change`. | **APPROVED BR-004.** Exact encoding, BOM, whitespace, quote/newline and row-limit rules TBD. |
| CSV row values | Propose exactly two columns; SKU must identify an existing product; `change` is a signed, non-zero base-10 integer; whitespace/blank rows and extra columns rejected. Repeated SKUs processed in file order. | **PROPOSED**, informed by PoC implementation. Confirm whitespace, signs, leading zeros, blank lines and duplicate-SKU semantics. |
| CSV atomicity and batches | Invalid row or failure rejects the entire batch with no partial mutation. Ordinary negative issues count as demand; rejected rows and quarantine/disposal do not. | **APPROVED BR-004, BR-006, BR-031.** `sku,change` cannot by itself select among separate inventories or express receiving-batch expiry/disposal classification; compatibility with BR-016/BR-022/BR-028/BR-029/BR-032/BR-033 **TBD**. No new CSV columns are approved. |
| Empty/header-only CSV | Reject empty and header-only uploads. | **APPROVED BR-004.** Whitespace-only row treatment TBD. |
| Duplicate CSV submission | Reject identical re-upload after a previously successful import; do not apply twice. | **APPROVED BR-005.** Identity, hashing, retention and concurrency safeguards TBD. A failed prior upload does not satisfy the success condition. |
| CSV size/limits | Define a maximum file size and row count before implementation. | **TBD.** Must fit staging memory/time and student project constraints; no number is approved. |
| Forecast window | Previous seven complete Asia/Singapore calendar days; exclude current day. Average = eligible demand total / 7. | **APPROVED BR-007.** Requires trustworthy dated movements. |
| Demand source | Committed ordinary manual/negative-CSV stock-outs count; stock-in, adjustments, quarantine and disposal are excluded. | **APPROVED BR-006, BR-031.** Proxy, not validated sales; movement classification, source retention and coverage TBD. |
| Zero-demand days | Count verified, reliably observed zero-demand day as zero. No records alone cannot prove coverage. | **APPROVED BR-008.** Coverage evidence method TBD. |
| Missing/incomplete days | Forecast unavailable if any of seven days is unobserved or incomplete. | **APPROVED BR-008.** No silent zero imputation. |
| Insufficient history | Require seven complete, reliably observed days. | **APPROVED BR-008.** Availability message/detail TBD. |
| Forecast rounding | Show average daily demand to two decimals; use full precision for calculations without intermediate rounding. | **APPROVED BR-009.** |
| Supplier lead time | Positive whole calendar days per product. | **APPROVED BR-010.** Other supplier-setting policy TBD. |
| Safety stock | Nonnegative whole number per product; zero is valid. | **APPROVED BR-015.** Maximum and editing feedback TBD. |
| Reorder formula | Reorder point = average daily demand × lead-time days + safety stock; suggested quantity = `max(0, ceil(reorder point − available-to-issue quantity))`, excluding quarantined stock and pending deliveries. Show inputs and calculation. | **APPROVED BR-011/BR-013/BR-030.** BR-030 updates BR-011's stock input; BR-013 excludes pending deliveries for MVP. Other holds TBD. |
| Reorder trigger | Alert when available-to-issue quantity is at or below reorder point; keep alert separate from suggested quantity, which can be zero at equality. | **APPROVED BR-012.** Alert presentation when inputs unavailable TBD. |
| Reorder settings scope | Supplier lead time and safety stock only; minimum order quantity, pack size and advanced settings outside MVP. | **APPROVED BR-014.** Future expansion requires change control. |
| Settings permission | Managers edit lead time and safety stock; Staff view but cannot edit within authorized scope. | **APPROVED BR-025.** Editing workflow TBD. |
| Inventory access and roles | Both roles view assigned inventory, record ordinary stock-in/out and view forecasts/reorder suggestions. Managers additionally create/edit/deactivate products, adjust stock, import CSV and edit settings. | **APPROVED BR-021/BR-022.** Only assigned inventories in own business; BR-027 limits Manager Staff assignments. Unlisted actions TBD. |
| Accounts and history | Initial Manager is provisioned during setup; Managers invite/create Staff. Both roles view transaction history for authorized inventories. | **APPROVED BR-023/BR-024.** Invitation/authentication mechanics and history-view details TBD. |
| Recommendation action | Recommendation is informational and creates no purchase order. | **APPROVED BR-011.** Supplier communication remains outside approved scope. |

## Edge-case acceptance examples to approve

The following deterministic examples apply approved rules; they are proposed acceptance cases, not executed tests. Assume every listed day has independently verified complete observation coverage.

| Case | Input | Expected outcome |
|---|---|---|
| Verified zero and two-decimal display | For 1–7 November 2026 (Asia/Singapore), daily stock-out demand is `[1, 0, 1, 0, 1, 0, 0]`; zero days have verified coverage. | Total `3`; unrounded average `3/7`; displayed average `0.43`. The zero days count as zero (BR-007–BR-009). |
| Missing coverage | Same series, but 3 November lacks reliable observation coverage, even if no stock-out record exists. | Forecast and dependent recommendation are unavailable; do not substitute zero (BR-008). |
| Singapore midnight | At 8 November 2026 00:00 Asia/Singapore, window is 1 November 00:00 through 7 November 23:59:59… local time. | A stock-out at 7 November 23:59 is included; at 8 November 00:00 is excluded; at 31 October 23:59 is excluded (BR-007). |
| No intermediate rounding | For the verified `3/7` average above, lead time `7` days, valid safety stock `0` and available-to-issue quantity `0`. | Reorder point `(3/7) × 7 + 0 = 3`; suggested quantity `3`. Using displayed `0.43` would incorrectly yield `ceil(3.01) = 4` (BR-009–BR-011, BR-015, BR-030). |
| Alert at threshold | Reorder point `8`; available-to-issue `8`; pending delivery `5`. | Show reorder alert and suggested quantity `0` separately; pending delivery does not change the calculation (BR-012/BR-013). |
| Quarantine and reorder input | On-hand `10`, of which `4` are quarantined; reorder point `8`; assume no other holds. | Available-to-issue quantity `6`; suggested quantity `2` (BR-030). Quarantine/disposal movements contribute zero forecast demand (BR-031). |
| FEFO and eligibility | Two eligible batches expire on different dates; a third batch is expired and quarantined. | Ordinary issue allocates from the earlier eligible expiry first; quarantined units cannot satisfy it (BR-029, BR-033). Exact expiry boundary and no-expiry order remain TBD. |

These cases require dated stock movement evidence and a trustworthy indication that each day was observed. The observation mechanism and database schema belong to later decisions.

1. Stock-out exactly equal to available stock; one unit over available stock; repeated concurrent stock-outs.
2. Adjustment below zero, adjustment to zero, and adjustment with missing reason if reasons are approved.
3. CSV valid rows around an invalid row; unknown SKU; repeated SKU; repeated whole file; malformed quotes; empty/header-only file; UTF-8 BOM; maximum size boundary.
4. Forecast all-zero fully observed week; one missing day; no history; demand transaction at day boundary; adjustment in window; lead time zero/one; reorder quantity fractional before ceiling.
5. Product SKU case/space variations and attempts to rename/deactivate a product with movements.

No example is an executed test. The individually approved rules are recorded separately; remaining details require owner disposition before Requirements exit.
