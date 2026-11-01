# Tory Owner Requirements Decisions

**Decision dates:** BR-001–BR-011: 29 October 2026; BR-026–BR-033: 1 November 2026
**Authority:** Project owner, as supplied in the project instructions  
**Status:** BR-001–BR-011 and BR-026–BR-033 approved individually. BR-012–BR-025 have no approval recorded here; BR-034 onward have no approval recorded. Complete SRS and Requirements exit **PENDING OWNER APPROVAL**. No signature is claimed.

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
| BR-011 | Reorder point = average daily demand × lead-time days + safety stock. Suggested quantity = `max(0, ceil(reorder point − current on-hand))`. Show inputs/calculation; advice only, no purchase order. BR-030 later specifies available-to-issue quantity for this stock input. | FR-010, FR-011, NFR-004 | Inventory on order, trigger semantics, safety-stock constraints, minimum/pack size. |
| BR-026 | Managers may deactivate Staff accounts, revoking access while retaining attributable history. | FR-007, NFR-001 | Account provisioning, reactivation, session revocation timing and history retention. |
| BR-027 | Managers assign Staff only to inventories they themselves are authorised to manage within the same business. | FR-002, FR-007, NFR-001 | Business/inventory ownership model, assignment lifecycle and authorization concurrency. |
| BR-028 | No ordinary transactions against deactivated products. Remaining stock must be resolved before deactivation. Managers can reactivate products. | FR-001, FR-003–FR-006, NFR-003 | Exact remaining-stock resolution workflow, transaction classification and CSV handling. |
| BR-029 | Expired batches are quarantined and unavailable for ordinary issue. | FR-004, FR-006, NFR-003 | Expiration boundary, quarantine implementation and CSV-versus-batch behavior. |
| BR-030 | Reorder calculations use available-to-issue quantity, excluding quarantined stock. | FR-011, NFR-004 | Available-to-issue definition across other holds; consistency under concurrent changes. |
| BR-031 | Quarantine and disposal are excluded from stock-out demand forecasts. | FR-009, FR-010, NFR-004 | Movement classification and treatment of CSV changes that represent disposal. |
| BR-032 | Expiry is recorded per receiving batch; it is optional for products not tracked for expiry. | FR-003, FR-006, NFR-003 | Non-expiry batch ordering, expiry-tracking changes and CSV `sku,change` compatibility. |
| BR-033 | Automatic FEFO allocation consumes eligible batches in earliest-expiry order. | FR-004, FR-006, NFR-003 | Ties, no-expiry ordering, expiry boundary, CSV allocation and concurrency. |

These approvals do not select a data schema, architecture, frontend or hosting provider. BR-026–BR-033 are a separate 1 November decision set; the numbering gap does not imply approval of BR-012–BR-025 or BR-034 onward. Earlier draft labels RD-01–RD-03 referred to BR-001–BR-003. Proposed acceptance examples are verification plans, not executed tests.
