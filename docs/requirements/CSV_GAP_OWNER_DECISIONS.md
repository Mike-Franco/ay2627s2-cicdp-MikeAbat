# Tory CSV receiving and contract owner decision package

**Status:** DRAFT — **G-03 and G-04 remain BLOCKING and PENDING OWNER DECISION.** Prepared during Requirements review. No option, numeric limit, parsing convention, SRS revision or stage exit is approved by this package. The complete SRS, Requirements exit and Design entry remain **NOT APPROVED**. The examples are proposed acceptance tests, not executed results.

## 1. Executive summary

| Gap | Owner choice requested | Recommended MVP-safe choice — PROPOSED, NOT APPROVED |
|---|---|---|
| **G-03 — non-expiry receiving and positive CSV** | How an allowed positive `sku,change` row for a non-expiry-tracked product creates receivable stock and participates in dated FEFO/undated FIFO. | **Option A:** one eligible undated receiving batch per valid positive row, with committed receiving sequence and stable batch ID; process repeated SKU rows in file order. |
| **G-04 — CSV contract and limits** | Exact accepted bytes/records, error outcome, and bounded file/row size while retaining the approved header and atomicity. | **Option A:** strict UTF-8, no BOM, exact header, two-field records, explicit syntax and limits of **256 KiB and 1,000 data rows**. Both limits are candidate values requiring owner approval. |

The owner may approve, amend, reject or explicitly defer either decision. A bounded deferral needs a responsible role, target stage, observable outcome and verification evidence under the [Requirements review gate](REQUIREMENTS_REVIEW.md#5-requirements-gate-readiness-checklist). Neither suggested option changes an approved BR ID. [Gap analysis](REQUIREMENTS_GAP_ANALYSIS.md) continues to list both gaps as blocking.

## 2. Approved baseline and decision boundary

| Existing approval | Consequence for these decisions |
|---|---|
| BR-004/BR-005/BR-041; FR-006, NFR-003 | Transaction CSV uses the exact named columns `sku,change`; empty/header-only files fail; the whole import commits or none. A byte-identical file is rejected after a **successful** import in the **same selected inventory**. Semantically equivalent but byte-different files are not BR-041 duplicates. |
| BR-020/BR-021/BR-022/BR-028/BR-039; FR-003/FR-006/FR-007, NFR-001/NFR-003 | Quantities use whole-number base units. Only an authorised Manager imports into an explicitly selected assigned, same-business inventory. Ordinary transactions on deactivated products are barred. |
| BR-032/BR-036; FR-003/FR-006 | Expiry is per receiving batch and optional for products **not** tracked for expiry. Positive CSV rows for expiry-tracked products are rejected; they must be received manually with batch/expiry details. Negative CSV rows may issue eligible batches without adding columns. |
| BR-002/BR-006/BR-029–BR-035; FR-004/FR-006/FR-009, NFR-003/NFR-004 | No negative stock or partial mutation. Committed negative CSV issues count as demand; receipts do not. Eligible dated batches precede undated batches. Expired units are unavailable at the Singapore midnight boundary. |
| Owner-approved G-01/G-02/G-09 Options A, 1 November 2026; NFR-003/NFR-011 | Tied allocations use committed receiving sequence and stable batch ID. Expiry eligibility does not wait for a stored transition. Each committed mutation has linked audit evidence; stock and committed evidence succeed or roll back together. |

**Still ambiguous:** G-03's positive-row batch and receipt-order semantics; G-04's byte/record syntax, BOM, whitespace, limits, repeat-SKU processing and rejection feedback. BR-041 does **not** make semantically equivalent files idempotent. G-11 still needs concurrent import and allocation mechanisms; G-13 still needs assignment-change timing; G-16 still needs SKU character/length policy; G-19 still needs a general usability rubric. The choices below describe observable behaviour, not a Django parser, PostgreSQL schema or locking design.

## 3. G-03 — non-expiry receiving and positive CSV

### Practical options and trade-offs

| Option | Behaviour | Advantage | Cost or risk |
|---|---|---|---|
| **A. One undated batch per positive row** | Each accepted positive row for a non-expiry-tracked product creates one eligible undated receiving batch with committed receiving sequence and stable batch ID. Repeat rows remain distinct receipts in file order. | Preserves receipt provenance and G-01 FIFO order; consistent with manual undated receipts; no new CSV column. | More batch records; committed ordering must be defined across rows, files and manual receipts under concurrency. |
| **B. Reject all positive CSV rows** | Any positive row rejects the whole file; all receiving is manual. | Simple CSV issue-only path; manual entry can capture optional expiry. | Narrows the currently contemplated stock-transaction import workflow and adds manual effort; owner must explicitly accept that restriction. |
| **C. Add to one existing undated pool batch** | Positive rows for a non-tracked product increase a designated undated pool, while separate row-level audit evidence records each receipt. | Fewer batches and simpler aggregate balance. | Blends distinct receipt ages and may make approved undated FIFO untestable unless a separate receipt-order subledger is maintained; not recommended for MVP. |

**Recommended MVP-safe choice — PROPOSED, NOT APPROVED: Option A.** An accepted positive CSV row for a non-expiry-tracked product creates **one eligible undated receiving batch per row**, with a sequence reflecting committed receipt order and a stable batch ID as G-01's final tie-breaker. Multiple positive rows for the same SKU are separate receipts, processed in file order. Manual undated receipts and CSV undated receipts share the same observable receiving-order rule. If a non-expiry-tracked product also has eligible dated batches entered manually, ordinary or negative-CSV issue consumes eligible dated batches first, then all undated batches in committed receiving order. Positive CSV rows for expiry-tracked products remain prohibited by BR-036. No expiry or batch column is added to `sku,change`.

For sequential effects within one valid file, evaluate rows in file order against the resulting prior-row state. Thus an earlier positive row may supply a later negative row; a negative row cannot borrow from a later positive row. All rows, their batch identities/sequences, demand and G-09 committed audit evidence become visible **only if the entire import succeeds**. The selected inventory and authorization apply to every row. This is a proposed clarification of G-03/G-04, not an existing approval.

| Proposed acceptance example | Expected if Option A is approved |
|---|---|
| Product P does not track expiry. One authorised import contains `P,+5` then `P,+3`; no prior stock. | Two undated batches are committed in row order with quantities 5 and 3 and distinct receiving sequences. An ordinary issue of 6 consumes 5 from the first batch and 1 from the second; remaining physical quantity is 2. Receipt rows do not count as demand. |
| Non-tracked P has an eligible manually received dated batch D (2 units), then a manual undated batch U (1 unit), then a CSV positive row (3 units). Issue 4. | Consume D's 2 first, U's 1 next, then 1 from the CSV batch. The CSV batch retains 2. G-01 dated-before-undated and common committed receipt order apply. |
| A valid `P,+5` row is followed by an invalid row in one file. | No new batch, sequence reservation visible as a receipt, physical balance, demand or committed audit movement from the file survives. A later successful receipt receives its own committed order. |
| A product is expiry-tracked; the file contains a positive row for it after a valid negative row. | Reject the whole file under BR-036/BR-004; neither row changes stock, allocation, demand or committed audit. Manual receiving with batch/expiry details remains the approved route. |

**G-03 status: PENDING OWNER DECISION — BLOCKING.** If Option A is chosen, Design may determine batch identity/sequence storage, concurrent sequence assignment and transaction mechanics. The owner must first select the observable positive-row and repeat-row behaviour. G-11 covers concurrency implementation; G-16's SKU syntax must not silently change receipt eligibility.

## 4. G-04 — CSV contract and validation limits

### Contract options

| Option | Behaviour | Advantage | Cost or risk |
|---|---|---|---|
| **A. Strict bounded contract** | Use the proposed choices in the table below, including 256 KiB and 1,000 data-row candidate limits. | Small, predictable validation surface and reproducible acceptance cases. | Rejects BOMs, whitespace variants and files beyond the candidate caps. |
| **B. Tolerant bounded contract** | Accept an optional UTF-8 BOM, trim surrounding header/field whitespace and allow blank lines; retain the same two columns, whole-number changes and atomicity. Choose explicit size/row caps. | Friendlier to common spreadsheet exports. | More parsing equivalences; harder error precedence and testing. Byte-different variants remain separate under BR-041 and can be applied again. |
| **C. Smaller strict pilot cap** | Keep Option A syntax but cap at **64 KiB and 250 data rows** until capacity is measured and the owner approves expansion. | Tighter resource bound for small staging capacity. | More legitimate uploads may need splitting; split files are separate transactions and can change row-order/atomicity expectations. |

**Recommended MVP-safe choice — PROPOSED, NOT APPROVED: Option A.** The following are proposed owner choices, **not** approved numeric or parsing rules. “KiB” means 1,024 bytes; data-row count excludes the header and counts logical CSV records. File size counts raw uploaded bytes, including header and line endings, before decoding. The caps are modest engineering candidates for a small MVP, **not measured performance or hosting-capacity results**; G-08/G-10 still require workload and zero-cost staging evidence.

| Decision point | Proposed Option A contract | Trade-off / alternative to select explicitly |
|---|---|---|
| Encoding and BOM | Decode strict UTF-8; reject malformed sequences and a UTF-8 BOM. | Accept BOM under Option B for spreadsheet compatibility; byte identity still includes BOM. |
| Header and line endings | First record is exactly `sku,change` with lowercase spelling, no surrounding spaces or extra columns. Accept LF or CRLF record endings; no additional header or leading blank record. | Tolerating header spaces/case creates more equivalent input forms; BR-004 still requires the named two columns. |
| Row shape and whitespace | Exactly two CSV fields per data record. Use normal CSV quoting for a field containing a comma or quote; reject embedded record newlines and blank records. Trim leading/trailing spaces in SKU for lookup, consistent with BR-001; reject empty-after-trim SKU. Do not trim `change` or allow spaces around its integer text. | Strict change syntax is easy to test; accepting surrounding whitespace or blank rows would require a separately bounded rule. G-16 still controls which SKU characters are valid. |
| Change syntax | Require nonzero base-10 whole units matching `[+-]?[0-9]+` and within the approved whole-unit domain; `+5`, `5` and `-5` are syntactically valid, `0`, `-0`, `1.5`, `1e3` and ` 5` fail. Reject values whose magnitude cannot be represented safely before mutation. | Explicit sign and leading zeros are accepted; a numeric maximum/representation bound beyond whole-unit safety needs Design test data or owner disposition under G-12. |
| File and row limits | **Candidate maximum: 256 KiB raw bytes and 1,000 data rows, inclusive.** File at 256 KiB or 1,000 rows may pass other checks; one byte or one row over fails wholly. | 64 KiB/250 rows is smaller but more restrictive; 1 MiB/5,000 rows is more accommodating but needs stronger performance/memory evidence. No limit is owner-approved yet. |
| Empty/header-only | Reject an empty upload, no header, or exact header with zero data records; reject blank records rather than silently ignoring them. | Follows BR-004; blank-line tolerance is an optional new rule. |
| Duplicate SKU rows | Permit repeated SKUs; apply valid rows sequentially in file order within one atomic import. Each positive row under G-03 Option A is a distinct receipt; each negative row allocates against eligible stock after earlier rows. | A later invalid/insufficient row rolls back all earlier rows. Aggregating duplicate rows would lose order-dependent allocation semantics. |
| Product and authorization checks | Reject missing/blank, unknown, inactive, other-business or otherwise unauthorised SKU for the selected inventory; also reject an unauthorised or unselected target inventory and Staff import. Do not leak whether a cross-business SKU exists. | The shared catalogue/inventory relationship and assignment-change timing need G-13 Design disposition; do not infer product creation from CSV. |
| Validation feedback | Reject the entire file with one predictable response identifying at least the first failing logical data-row number (header is row 1), field/category and safe correction cue; file-level errors identify category. No committed stock, batch, demand, import-success marker or audit movement remains. | Reporting every error is friendlier but requires a policy for dependent rows. Exact wording/UI and G-19 usability rubric remain open. |
| Exact-byte duplicate | After prior successful import of raw bytes F into inventory I, re-uploading exactly F into I is rejected without mutation. A failed prior upload or success in inventory J does not match; different bytes are not a BR-041 duplicate even if rows mean the same thing. | Preserves the approved rule; hash/storage, retention and race-safe claim mechanism are Design details. BOM, whitespace and line-ending differences change bytes. |
| Concurrent imports | For the same bytes and inventory, at most one competing import succeeds; the other has no stock/batch/demand/committed-audit effects. For different files affecting the same stock, committed outcomes must be equivalent to a serial row-by-row application of each whole file, with no oversell or partial import. | G-11 determines locking, retries and failure response; no manual retry-idempotency policy is inferred. |

The proposed SKU trim applies only to lookup and does **not** canonicalise BR-041 duplicate identity: file bytes, including whitespace, line endings and quoting, are still compared exactly. If the owner prefers a fully strict no-trim SKU field, that is a separate selectable amendment. Validation order across independent errors and first-error priority must be fixed before formal testing; the proposed minimum response does not promise all errors.

| Proposed acceptance example | Expected if Option A is approved |
|---|---|
| A Manager selects authorised inventory I and uploads UTF-8 bytes for `sku,change` followed by `P,+5` and `P,-2`; P is active, non-tracked and initially has no stock. | Import commits atomically: one undated receipt batch of 5, then an eligible issue of 2 from it; physical balance 3, demand 2, linked G-09 row movements sharing one import identity. The exact row grammar and G-03 receipt choice both require owner approval. |
| Same file has `P,-2` before `P,+5` with no prior eligible stock. | Row 2 is insufficient when evaluated; reject the entire file. Later receipt cannot rescue an earlier issue. No stock, batch, demand, success marker or committed audit event survives. |
| File has correct header and 1,001 data rows, or exceeds 256 KiB by one byte. | Reject wholly under proposed limits; exactly 1,000 rows and exactly 256 KiB pass the limit check but must still pass all other validations. |
| Header is ` sku,change`, or file starts with a UTF-8 BOM, or row contains `P,0`, `P,1.5`, blank SKU, a third field or a blank record. | Reject the entire file with a safe file/row/field category; no partial mutation. The BOM and whitespace policies are proposed, not approved. |
| A valid row is followed by unknown SKU, inactive product, cross-business SKU or positive row for expiry-tracked product. | Reject the whole selected-inventory import; earlier rows leave no stock, batch, demand or committed audit change. Cross-business feedback does not disclose product existence. |
| Bytes F import successfully into inventory I. Upload F again into I, upload F into authorised inventory J, and upload byte-different but semantically equivalent F2 into I. | Second F/I upload is rejected as duplicate. F/J is not rejected **solely** because of F/I. F2/I is not a BR-041 duplicate; it is validated against current stock/rules and may apply if otherwise valid. |
| Two Managers upload identical valid bytes F concurrently to the same authorised inventory I. | At most one import commits, with one set of stock, batch, demand and committed audit effects. The loser does not partially apply; exact response and PostgreSQL mechanism remain Design TBD. |

**G-04 status: PENDING OWNER DECISION — BLOCKING.** The owner must choose the observable encoding/BOM, whitespace/record syntax, repeat-SKU, feedback and limit policy or explicitly bound a deferral. The 256 KiB/1,000-row and alternative numeric values above are candidates only. Parser library, byte-identity persistence, transaction/locking, row-level audit representation and performance evidence may follow in Design once behaviour is approved. G-03 Option A is a dependency for the positive-row examples; choosing G-03 Option B requires adjusting those examples without changing BR-004/BR-036.

## 5. Owner decision record and stage boundary

| Gap | Select one option or record amendment/deferral | Responsible role / target stage / evidence if deferred | Status |
|---|---|---|---|
| G-03 | A / B / C / amended: **TBD** | TBD | **PENDING OWNER DECISION — BLOCKING** |
| G-04 | A / B / C / amended, including explicit numeric caps and each contract row: **TBD** | TBD | **PENDING OWNER DECISION — BLOCKING** |

Approval of a recommendation would require a dated owner record, corresponding SRS/business-rule/traceability updates and a gap disposition. This package makes no such approval. G-02/G-09 remain blocking on their separate parameters; G-11/G-13/G-16/G-19 and the other open gaps retain their existing status. No Requirements exit or Design entry is authorised.
