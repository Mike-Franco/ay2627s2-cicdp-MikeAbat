# Tory CSV receiving and contract owner decision package

**Status:** **G-03 Option A and G-04 Option A APPROVED by the owner on 1 November 2026.** Their observable Requirements behaviour is resolved; Design verification and dependencies remain open. These are new owner-provided approvals, not new BR IDs or approval of the complete SRS. Requirements exit and Design entry remain **NOT APPROVED**. The examples are acceptance-test plans, not executed results or capacity evidence.

## 1. Executive summary

| Gap | Owner-approved selection, 1 November 2026 | Remaining work |
|---|---|---|
| **G-03 — non-expiry receiving and positive CSV** | **Option A:** one eligible undated receiving batch per valid positive row, with stable identity and committed receipt sequence; process repeated SKU rows in file order. | Design batch/sequence representation and concurrent ordering; verify FEFO/FIFO and atomic rollback. |
| **G-04 — CSV contract and limits** | **Option A:** strict UTF-8, no BOM, exact `sku,change` header and bounded two-field records; **262,144 raw bytes and 1,000 data rows, inclusive**. | Design parser, byte-duplicate storage and concurrency mechanism; verify limit boundaries and performance without claiming tests have run. |

The option tables retain alternatives considered before approval. [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md) records the dated evidence; the [gap analysis](REQUIREMENTS_GAP_ANALYSIS.md) records G-03/G-04 as requirements-behaviour-resolved with Design verification open. Other open gaps and the [Requirements review gate](REQUIREMENTS_REVIEW.md#5-requirements-gate-readiness-checklist) remain unchanged in authority.

## 2. Approved baseline and decision boundary

| Existing approval | Consequence for these decisions |
|---|---|
| BR-004/BR-005/BR-041; FR-006, NFR-003 | Transaction CSV uses the exact named columns `sku,change`; empty/header-only files fail; the whole import commits or none. A byte-identical file is rejected after a **successful** import in the **same selected inventory**. Semantically equivalent but byte-different files are not BR-041 duplicates. |
| BR-020/BR-021/BR-022/BR-028/BR-039; FR-003/FR-006/FR-007, NFR-001/NFR-003 | Quantities use whole-number base units. Only an authorised Manager imports into an explicitly selected assigned, same-business inventory. Ordinary transactions on deactivated products are barred. |
| BR-032/BR-036; FR-003/FR-006 | Expiry is per receiving batch and optional for products **not** tracked for expiry. Positive CSV rows for expiry-tracked products are rejected; they must be received manually with batch/expiry details. Negative CSV rows may issue eligible batches without adding columns. |
| BR-002/BR-006/BR-029–BR-035; FR-004/FR-006/FR-009, NFR-003/NFR-004 | No negative stock or partial mutation. Committed negative CSV issues count as demand; receipts do not. Eligible dated batches precede undated batches. Expired units are unavailable at the Singapore midnight boundary. |
| Owner-approved G-01/G-02/G-09 Options A, 1 November 2026; NFR-003/NFR-011 | Tied allocations use committed receiving sequence and stable batch ID. Expiry eligibility does not wait for a stored transition. Each committed mutation has linked audit evidence; stock and committed evidence succeed or roll back together. |

**Decision boundary:** G-03 positive-row batch and receipt-order semantics and G-04 byte/record syntax, BOM, whitespace, limits, repeat-SKU processing and minimum rejection feedback are now approved below. BR-041 does **not** make semantically equivalent files idempotent. G-11 still needs concurrent import and allocation mechanisms; G-12 a safe maximum integer representation, G-13 assignment-change timing, G-16 SKU character/length policy and G-19 a general usability rubric. These approvals specify observable behaviour, not a Django parser, PostgreSQL schema or locking design.

## 3. G-03 — non-expiry receiving and positive CSV

### Practical options and trade-offs

| Option | Behaviour | Advantage | Cost or risk |
|---|---|---|---|
| **A. One undated batch per positive row — approved** | Each accepted positive row for a non-expiry-tracked product creates one eligible undated receiving batch with committed receiving sequence and stable batch ID. Repeat rows remain distinct receipts in file order. | Preserves receipt provenance and G-01 FIFO order; consistent with manual undated receipts; no new CSV column. | More batch records; committed ordering must be defined across rows, files and manual receipts under concurrency. |
| **B. Reject all positive CSV rows** | Any positive row rejects the whole file; all receiving is manual. | Simple CSV issue-only path; manual entry can capture optional expiry. | Narrows the currently contemplated stock-transaction import workflow and adds manual effort; owner must explicitly accept that restriction. |
| **C. Add to one existing undated pool batch** | Positive rows for a non-tracked product increase a designated undated pool, while separate row-level audit evidence records each receipt. | Fewer batches and simpler aggregate balance. | Blends distinct receipt ages and may make approved undated FIFO untestable unless a separate receipt-order subledger is maintained; not recommended for MVP. |

**Owner-approved Option A — 1 November 2026.** Every valid positive CSV row for a non-expiry-tracked product creates **its own eligible undated receiving batch** with stable identity and a sequence reflecting committed receipt order. Multiple rows for the same SKU are separate receipts processed sequentially in file order without aggregation. Manual and CSV undated batches share the same receiving-order semantics. Eligible dated batches remain first under approved FEFO/FIFO; negative rows allocate available eligible stock in that order. Positive CSV rows for expiry-tracked products remain prohibited by BR-036. No expiry or batch column is added to `sku,change`.

Evaluate rows in file order against the resulting prior-row state. An earlier positive row may supply a later negative row; a negative row cannot borrow from a later positive row. All rows, their batches, demand and G-09 committed audit evidence become visible **only if the entire import succeeds**. Any failed row rolls back the whole import, including newly created batches and audit records. The selected inventory and authorization apply to every row.

| Acceptance example (planned; not executed) | Expected under approved Option A |
|---|---|
| Product P does not track expiry. One authorised import contains `P,+5` then `P,+3`; a subsequent `P,-6` issue is submitted. | Two eligible undated batches are committed in row order, quantities 5 and 3 with stable identities and distinct committed sequences. `P,-6` allocates 5 from the first batch and 1 from the second, leaving 2 physical units. Receipt rows do not count as demand. |
| Non-tracked P has an eligible manually received dated batch D (2 units), then a manual undated batch U (1 unit), then a CSV positive row (3 units). Issue 4. | Consume D's 2 first, U's 1 next, then 1 from the CSV batch. The CSV batch retains 2. G-01 dated-before-undated and common committed receipt order apply. |
| A valid `P,+5` row is followed by an invalid row in one file. | No new batch, sequence reservation visible as a receipt, physical balance, demand or committed audit movement from the file survives. A later successful receipt receives its own committed order. |
| P has no initial stock. One file has `P,+5` then `P,-2`; another has `P,-2` then `P,+5`. | The first file commits with 3 units remaining and linked row audit; the second fails at its first issue and rolls back entirely. Later receipt cannot make the earlier issue valid. |
| A product is expiry-tracked; the file contains a positive row for it after a valid negative row. | Reject the whole file under BR-036/BR-004; neither row changes stock, allocation, demand or committed audit. Manual receiving with batch/expiry details remains the approved route. |

**G-03 status: OWNER-APPROVED OPTION A; REQUIREMENTS BEHAVIOUR RESOLVED, DESIGN VERIFICATION OPEN.** Design must determine batch identity/sequence storage, concurrent sequence assignment and transaction mechanics without changing the approved order. G-11 covers concurrency; G-16's SKU syntax must not silently change receipt eligibility. No import has been implemented or tested by this record.

## 4. G-04 — CSV contract and validation limits

### Contract options

| Option | Behaviour | Advantage | Cost or risk |
|---|---|---|---|
| **A. Strict bounded contract — approved** | Use the strict choices in the table below, including the 262,144-byte and 1,000-data-row inclusive limits. | Small, predictable validation surface and reproducible acceptance cases. | Rejects BOMs, whitespace variants and files beyond the approved caps. |
| **B. Tolerant bounded contract** | Accept an optional UTF-8 BOM, trim surrounding header/field whitespace and allow blank lines; retain the same two columns, whole-number changes and atomicity. Choose explicit size/row caps. | Friendlier to common spreadsheet exports. | More parsing equivalences; harder error precedence and testing. Byte-different variants remain separate under BR-041 and can be applied again. |
| **C. Smaller strict pilot cap** | Keep Option A syntax but cap at **64 KiB and 250 data rows** until capacity is measured and the owner approves expansion. | Tighter resource bound for small staging capacity. | More legitimate uploads may need splitting; split files are separate transactions and can change row-order/atomicity expectations. |

**Owner-approved Option A — strict contract, 1 November 2026.** The following observable parsing and limit choices are approved. “KiB” means 1,024 bytes; data-row count excludes the header and counts logical CSV records. File size counts raw uploaded bytes, including header and line endings, before decoding. **256 KiB = 262,144 bytes.** These are approved *acceptance limits*, **not measured performance or hosting-capacity results**; G-08/G-10 still require workload and zero-cost staging evidence.

| Decision point | Owner-approved Option A contract | Earlier trade-off / Design detail |
|---|---|---|
| Encoding and BOM | Decode strict UTF-8; reject malformed sequences and a UTF-8 BOM. | Option B would have accepted BOM. Raw-byte duplicate identity still includes any bytes; malformed/BOM files cannot succeed under Option A. |
| Header and line endings | First record is exactly `sku,change` with lowercase spelling, no surrounding spaces or extra columns. Accept LF or CRLF record endings; no additional header or leading blank record. | Parsing implementation is Design; the accepted header and line endings are fixed. |
| Row shape and whitespace | Exactly two CSV fields per data record. Allow standard CSV quoting for a field containing a comma or quote; reject embedded record newlines and blank records. Trim leading/trailing spaces in SKU for lookup, consistent with BR-001; reject empty-after-trim SKU. Do not trim `change` or allow spaces around its integer text. | G-16 still controls which SKU characters are valid; parser choice remains Design. |
| Change syntax | Require nonzero base-10 whole units matching `[+-]?[0-9]+`; `+5`, `5` and `-5` are syntactically valid, `0`, `-0`, `1.5`, `1e3` and ` 5` fail. Reject values whose magnitude cannot be represented safely before mutation. | Numeric magnitude/storage bound beyond whole-unit syntax remains G-12/Design detail; no extra numeric maximum is inferred. |
| File and row limits | **Maximum: 262,144 raw bytes and 1,000 data rows, inclusive.** A file at either limit passes that limit check if the other limit and all content rules pass; 262,145 bytes or 1,001 data rows fails wholly. | Earlier alternatives were 64 KiB/250 and 1 MiB/5,000. Capacity/performance evidence remains pending; the approved limits must not be silently raised. |
| Empty/header-only | Reject an empty upload, no header, or exact header with zero data records; reject blank records rather than silently ignoring them. | BR-004 already rejected empty/header-only uploads; Option A now fixes blank-record handling. |
| Duplicate SKU rows | Permit repeated SKUs; apply valid rows sequentially in file order within one atomic import. Each positive row under approved G-03 Option A is a distinct receipt; each negative row allocates against eligible stock after earlier rows. | A later invalid/insufficient row rolls back all earlier rows. Aggregation would violate the approved sequence. |
| Product and authorization checks | Reject missing/blank, unknown, inactive, other-business or otherwise unauthorised SKU for the selected inventory; also reject an unauthorised or unselected target inventory and Staff import. Do not leak whether a cross-business SKU exists. | The shared catalogue/inventory relationship and assignment-change timing need G-13 Design disposition; do not infer product creation from CSV. |
| Validation feedback | Reject the entire file with a response identifying at least the first failing logical data-row number (header is row 1) and field when applicable, or an appropriate file-level error category. No committed stock, batch, demand, successful-import marker or inventory-mutation audit movement remains. | Exact wording/UI, additional errors and G-19 usability rubric remain open. The minimum failure information is approved. |
| Exact-byte duplicate | After prior successful import of raw bytes F into inventory I, re-uploading exactly F into I is rejected without mutation. A failed prior upload or success in inventory J does not match; different bytes are not a BR-041 duplicate even if rows mean the same thing. | Preserves the approved rule; hash/storage, retention and race-safe claim mechanism are Design details. BOM, whitespace and line-ending differences change bytes. |
| Concurrent imports | For the same bytes and inventory, at most one competing import succeeds; the other has no stock/batch/demand/committed-audit effects. For different files affecting the same stock, committed outcomes must be equivalent to a serial row-by-row application of each whole file, with no oversell or partial import. | G-11 determines locking, retries and failure response; no manual retry-idempotency policy is inferred. |

The approved SKU trim applies only to lookup and does **not** canonicalise BR-041 duplicate identity: file bytes, including whitespace, line endings and quoting, are still compared exactly. Validation order across independent file-level errors and presentation of additional errors remain Design/G-19 details; at least the first failing row and field when applicable, or a file-level category, is required. The approved contract does not promise all errors in one response.

| Acceptance example (planned; not executed) | Expected under approved Option A |
|---|---|
| A Manager selects authorised inventory I and uploads UTF-8 bytes for `sku,change` followed by `P,+5` and `P,-2`; P is active, non-tracked and initially has no stock. | Import commits atomically: one undated receipt batch of 5, then an eligible issue of 2 from it; physical balance 3, demand 2, linked G-09 row movements sharing one import identity. |
| Same file has `P,-2` before `P,+5` with no prior eligible stock. | Row 2 is insufficient when evaluated; reject the entire file. Later receipt cannot rescue an earlier issue. No stock, batch, demand, success marker or committed audit event survives. |
| A valid UTF-8 file with correct header has exactly 262,144 raw bytes and no more than 1,000 data rows; another has 262,145 bytes. | The first is within the size limit and may commit if all other checks pass. The second is rejected wholly even when its row count is valid. This is a byte-limit test, not a capacity benchmark. |
| A valid UTF-8 file has exactly 1,000 data rows and no more than 262,144 bytes; another has 1,001 data rows. | The first is within the row limit and may commit if all other checks pass. The second is rejected wholly even when its byte size is valid. |
| Header is ` sku,change`, or file starts with a UTF-8 BOM, or row contains `P,0`, `P,1.5`, blank SKU, a third field or a blank record. | Reject the entire file with the required row/field or file-level category; no partial mutation. |
| A valid row is followed by unknown SKU, inactive product, cross-business SKU or positive row for expiry-tracked product. | Reject the whole selected-inventory import; earlier rows leave no stock, batch, demand or committed audit change. Cross-business feedback does not disclose product existence. |
| Bytes F import successfully into inventory I. Upload F again into I, upload F into authorised inventory J, and upload byte-different but semantically equivalent F2 into I. | Second F/I upload is rejected as duplicate. F/J is not rejected **solely** because of F/I. F2/I is not a BR-041 duplicate; it is validated against current stock/rules and may apply if otherwise valid. |
| Two Managers upload identical valid bytes F concurrently to the same authorised inventory I. | At most one import commits, with one set of stock, batch, demand and committed audit effects. The loser does not partially apply; exact response and PostgreSQL mechanism remain Design TBD. |

**G-04 status: OWNER-APPROVED OPTION A; REQUIREMENTS BEHAVIOUR RESOLVED, DESIGN VERIFICATION OPEN.** Strict UTF-8, BOM rejection, header/row grammar, sequential repeats, minimum error reporting and the 262,144-byte/1,000-row limits are approved. Parser library, byte-identity persistence, transaction/locking, exact audit representation and capacity/performance evidence belong to Design and later verification. G-11 concurrency, G-12 numeric magnitude, G-13 assignment timing, G-16 SKU characters and G-19 broader feedback remain open. No implementation or limit-capacity test is claimed.

## 5. Owner decision record and stage boundary

| Gap | Owner selection and evidence date | Design/verification dependencies | Status |
|---|---|---|---|
| G-03 | **Option A approved, owner-provided 1 November 2026** | Batch identity/sequence storage, concurrent order and atomic PostgreSQL tests | **REQUIREMENTS BEHAVIOUR RESOLVED; DESIGN OPEN** |
| G-04 | **Option A strict contract approved, owner-provided 1 November 2026** | Parser/byte identity, G-11 concurrency, boundary and capacity verification | **REQUIREMENTS BEHAVIOUR RESOLVED; DESIGN OPEN** |

These dated owner-provided approvals settle G-03/G-04 observable behaviour, without creating new BR IDs or claiming executable tests. G-02/G-09 remain blocking on separate parameters; G-11/G-12/G-13/G-16/G-19 and the other open gaps retain their existing status. The complete SRS, Requirements exit and Design entry remain pending owner approval.
