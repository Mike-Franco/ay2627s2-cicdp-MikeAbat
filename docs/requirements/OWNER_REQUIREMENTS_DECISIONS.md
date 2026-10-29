# Tory Owner Requirements Decisions

**Decision date:** 29 October 2026  
**Authority:** Project owner, as supplied in the project instructions  
**Status:** BR-001–BR-011 approved individually. Complete SRS and Requirements exit **PENDING OWNER APPROVAL**. No signature is claimed.

| ID | Approved rule | Related stable requirements | Still unresolved |
|---|---|---|---|
| BR-001 | Require SKU; trim leading/trailing spaces; enforce case-insensitive uniqueness among active products. | FR-001 | SKU reuse/renaming, allowed characters, length and display form. |
| BR-002 | Reject stock-out that would make on-hand negative without partial mutation. | FR-004, FR-006, NFR-003 | Quantity precision and other input validation. |
| BR-003 | Manager only: enter absolute physical count, require reason, record resulting difference. | FR-005, FR-007, NFR-003 | Reason format, count precision, retention. |
| BR-004 | CSV stock transactions use `sku,change`; entire batch applies or none; reject empty/header-only uploads. | FR-006, NFR-003 | Encoding, whitespace, row limits and other parsing details. |
| BR-005 | Reject identical CSV re-upload after a prior successful import. | FR-006, NFR-003 | Duplicate identity, hashing, retention, concurrency safeguards. |
| BR-006 | All manual and committed negative-CSV stock-outs count as demand; stock-in/adjustments excluded. Demand is a proxy, not validated sales. | FR-004, FR-006, FR-009, FR-010 | Trustworthy history and coverage mechanism. |
| BR-007 | Use previous seven complete calendar days in Asia/Singapore; exclude current day. | FR-009, FR-010, NFR-004 | Clock/source timestamp quality and historical retention. |
| BR-008 | Require seven complete, reliably observed days; verified zero-demand day counts as zero; missing/incomplete day makes forecast unavailable. Absence of records does not prove coverage. | FR-009, FR-010, FR-011, NFR-004 | How coverage is established and retained. |
| BR-009 | Display average daily demand to two decimals; retain full calculation precision, with no intermediate rounding. | FR-010, FR-011, NFR-004 | Presentation details beyond two decimals. |
| BR-010 | Per-product supplier lead time is a positive whole number of calendar days. | FR-008, FR-011 | Other supplier/reorder settings and edit permission. |
| BR-011 | Reorder point = average daily demand × lead-time days + safety stock. Suggested quantity = `max(0, ceil(reorder point − current on-hand))`. Show inputs/calculation; advice only, no purchase order. | FR-010, FR-011, NFR-004 | Inventory on order, trigger semantics, safety-stock constraints, minimum/pack size. |

These approvals do not select a data schema, architecture, frontend or hosting provider. Earlier draft labels RD-01–RD-03 referred to BR-001–BR-003. Proposed acceptance examples are verification plans, not executed tests.
