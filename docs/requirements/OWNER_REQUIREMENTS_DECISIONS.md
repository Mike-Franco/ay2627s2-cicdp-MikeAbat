# Tory Owner Requirements Decisions

**Decision evidence:** BR-001–BR-011: owner decisions dated 29 October 2026; BR-012–BR-025: supplementary owner-provided ChatGPT Requirements review approvals, documented/reconciled 1 November 2026 (original approval timestamp not supplied); BR-026–BR-033: owner decisions dated 1 November 2026.
**Authority:** Project owner, as supplied in the project instructions and supplementary owner-provided decision record.
**Status:** BR-001–BR-033 approved individually. BR-034 onward have no approval recorded. Complete SRS and Requirements exit **PENDING OWNER APPROVAL**. No signature is claimed.

| ID | Approved rule | Related stable requirements | Still unresolved |
|---|---|---|---|
| BR-001 | Require SKU; trim leading/trailing spaces; enforce case-insensitive uniqueness among active products. | FR-001 | SKU reuse/renaming, allowed characters, length and display form. |
| BR-002 | Reject stock-out that would make on-hand negative without partial mutation. | FR-004, FR-006, NFR-003 | Whole-base-unit precision fixed by BR-020; other input validation TBD. |
| BR-003 | Manager only: enter absolute physical count, require reason, record resulting difference. | FR-005, FR-007, NFR-003 | Whole-base-unit precision fixed by BR-020; reason format and retention TBD. |
| BR-004 | CSV stock transactions use `sku,change`; entire batch applies or none; reject empty/header-only uploads. | FR-006, NFR-003 | Target-inventory selection with BR-016/BR-022, encoding, whitespace, row limits and other parsing details. |
| BR-005 | Reject identical CSV re-upload after a prior successful import. | FR-006, NFR-003 | Duplicate identity, hashing, retention, concurrency safeguards. |
| BR-006 | All manual and committed negative-CSV stock-outs count as demand; stock-in/adjustments excluded. BR-031 later excludes quarantine and disposal. Demand is a proxy, not validated sales. | FR-004, FR-006, FR-009, FR-010 | Movement classification, trustworthy history and coverage mechanism. |
| BR-007 | Use previous seven complete calendar days in Asia/Singapore; exclude current day. | FR-009, FR-010, NFR-004 | Clock/source timestamp quality and historical retention. |
| BR-008 | Require seven complete, reliably observed days; verified zero-demand day counts as zero; missing/incomplete day makes forecast unavailable. Absence of records does not prove coverage. | FR-009, FR-010, FR-011, NFR-004 | How coverage is established and retained. |
| BR-009 | Display average daily demand to two decimals; retain full calculation precision, with no intermediate rounding. | FR-010, FR-011, NFR-004 | Presentation details beyond two decimals. |
| BR-010 | Per-product supplier lead time is a positive whole number of calendar days. | FR-008, FR-011 | Exact calendar boundary and edit mechanics; BR-025 fixes edit permission. |
| BR-011 | Reorder point = average daily demand × lead-time days + safety stock. Suggested quantity = `max(0, ceil(reorder point − current on-hand))`. Show inputs/calculation; advice only, no purchase order. BR-030 later specifies available-to-issue quantity for this stock input. | FR-010, FR-011, NFR-004 | BR-012–BR-015 fix trigger, pending deliveries, settings scope and safety-stock constraints; presentation details TBD. |
| BR-012 | Trigger a reorder recommendation when available-to-issue stock is at or below the reorder point. Distinguish the alert from suggested quantity, which may be zero at the threshold. | FR-011, NFR-004 | Alert presentation and behavior when forecast/settings unavailable. |
| BR-013 | Ignore incoming/pending supplier deliveries for MVP reorder calculations; use available stock only. | FR-011, NFR-004 | Future handling outside MVP. |
| BR-014 | Reorder settings comprise supplier lead time and safety stock only; minimum order quantities, supplier pack sizes and other advanced settings are outside MVP. | FR-008, FR-011 | No advanced settings in MVP; later change control if needed. |
| BR-015 | Safety stock is a nonnegative whole number; zero is valid. | FR-008, FR-011 | Maximum and editing validation detail. |
| BR-016 | One shared product catalogue per business, with separate inventory records. | FR-001, FR-002, NFR-001 | Inventory identity/relationship, product lifecycle propagation and CSV target-inventory selection. |
| BR-017 | SKUs are unique within a business, case-insensitive as already defined. | FR-001 | Interaction with BR-001's active-product qualifier, SKU reuse/renaming and business reassignment. |
| BR-018 | Selling prices are inventory-specific. | FR-001, FR-002 | Price format, maintenance rights and whether price appears in MVP views. |
| BR-019 | Soft-deactivate products and preserve transaction history; this rule does not specify the deactivation actor. | FR-001, FR-007, NFR-003 | BR-021 assigns Manager deactivation; BR-028 assigns Manager reactivation. Remaining-stock resolution workflow TBD. |
| BR-020 | Stock quantities use whole-number base units; packaging conversion details remain TBD. | FR-003–FR-006, NFR-003 | Packaging conversion, limits and handling of previously fractional data. |
| BR-021 | Manager and Staff may view authorised inventory, record ordinary stock-in/out and view forecasts/reorder suggestions. Managers additionally create/edit/deactivate products, adjust physical stock, import transaction CSV and edit supplier/reorder settings. Staff may view those settings. | FR-001–FR-008, FR-010–FR-011, NFR-001 | Access remains limited by BR-022/BR-027; exact action mechanics and inactive-product behavior follow other rules. |
| BR-022 | Users may access only assigned inventories within their own business. | FR-002–FR-007, FR-010–FR-011, NFR-001 | Assignment lifecycle, initial Manager assignments and enforcement under concurrent changes. |
| BR-023 | Initial Manager is provisioned during setup; Managers invite/create Staff accounts. | FR-007, NFR-001 | Exact invitation, authentication and setup mechanics TBD. |
| BR-024 | Both roles may view transaction history for authorised inventories. | FR-002, FR-007, NFR-001 | History view fields, retention, correction and pagination TBD. |
| BR-025 | Managers edit supplier lead time and safety stock; Staff may view settings but not edit. | FR-008, FR-007, NFR-001 | Editing workflow and validation feedback TBD. |
| BR-026 | Managers may deactivate Staff accounts, revoking access while retaining attributable history. | FR-007, NFR-001 | Account provisioning, reactivation, session revocation timing and history retention. |
| BR-027 | Managers assign Staff only to inventories they themselves are authorised to manage within the same business. | FR-007, NFR-001 | Business/inventory ownership model, assignment lifecycle and authorization concurrency; inventory viewing scope is separate. |
| BR-028 | No ordinary transactions against deactivated products. Remaining stock must be resolved before deactivation. Managers can reactivate products. | FR-001, FR-003–FR-006, NFR-003 | Exact remaining-stock resolution workflow, transaction classification and CSV handling. |
| BR-029 | Expired batches are quarantined and unavailable for ordinary issue. | FR-004, FR-006, NFR-003 | Expiration boundary, quarantine implementation and CSV-versus-batch behavior. |
| BR-030 | Reorder calculations use available-to-issue quantity, excluding quarantined stock. | FR-011, NFR-004 | Available-to-issue definition across other holds; consistency under concurrent changes. |
| BR-031 | Quarantine and disposal are excluded from stock-out demand forecasts. | FR-009, FR-010, NFR-004 | Movement classification and treatment of CSV changes that represent disposal. |
| BR-032 | Expiry is recorded per receiving batch; it is optional for products not tracked for expiry. | FR-003, FR-006, NFR-003 | Non-expiry batch ordering, expiry-tracking changes and CSV `sku,change` compatibility. |
| BR-033 | Automatic FEFO allocation consumes eligible batches in earliest-expiry order. | FR-004, FR-006, NFR-003 | Ties, no-expiry ordering, expiry boundary, CSV allocation and concurrency. |

These approvals do not select a data schema, architecture, frontend or hosting provider. BR-012–BR-025 were supplied as supplementary owner approvals and are recorded with a documentation date, not an invented original approval timestamp. BR-034 onward remain unapproved. Earlier draft labels RD-01–RD-03 referred to BR-001–BR-003. Proposed acceptance examples are verification plans, not executed tests.
