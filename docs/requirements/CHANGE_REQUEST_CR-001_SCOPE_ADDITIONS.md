# CR-001: Scope additions beyond SRS section 2

**Date:** 22 November 2026
**Status:** Approved by the project owner on 22 November 2026, as instructed in the delivery planning for the staging deployment
**Change control basis:** [SRS section 10](SOFTWARE_REQUIREMENTS_SPECIFICATION.md#10-requirements-verification-and-change-control), item 5
**Traceability:** [Requirements Traceability Matrix](REQUIREMENTS_TRACEABILITY_MATRIX.md#implementation-and-test-evidence-22-november-2026)

## Purpose

During delivery, Tory gained features that the [SRS](SOFTWARE_REQUIREMENTS_SPECIFICATION.md) section 2.1 scope does not list. One of them, the Insights page, touches the section 2.2 exclusion of "expanded analytics". SRS section 10 requires a documented change request with explicit owner approval. This record covers those additions retrospectively. None of them changes an approved business rule (BR-001–BR-045), relaxes a nonfunctional requirement, or adds a cost.

## Approved additions

| Addition | Ticket / PRs | Relation to approved scope | Rationale |
| --- | --- | --- | --- |
| Inventory dashboard: stat tiles, low-stock and expiring lists, recent activity | TORY-40 (#59), TORY-51 (#73) | Presents FR-002, FR-010 and FR-011 results on one page | Managers and Staff need one starting point that shows what needs attention, instead of opening every product. |
| Insights page: demand, stock vs reorder point and expiry charts, with data tables | TORY-49 (#68, #74); stock value at selling price added in #82 | Read-only views of FR-002, FR-009–FR-011 data. Revises the 2.2 "expanded analytics" exclusion **only** for these fixed, read-only charts | Gives the demo and the report visual evidence of the forecasting outcomes. Uses existing data and the approved seven-day method only: no new forecasting method, prediction or data collection. |
| CSV export of current stock and stock history | TORY-43 (#61) | Complements FR-002 history. The exclusion of product catalogue **import** is unchanged | Lets Managers keep or share records without database access. Cells are escaped against spreadsheet formula injection. |
| Operations admin (Django admin for superusers) | TORY-44 (#63) | Operator support for FR-007 setup | Gives the operator a supported, audited way to fix data instead of ad hoc SQL. Ordinary Managers and Staff have no access. |
| Manager inventory management UI: add, rename, deactivate and reactivate | TORY-48 (#67) | Within the approved business and inventory model (BR-016–BR-022) | Before this, inventories could only be created by an operator command. Changes are audited and stock movements stay blocked in inactive inventories. |
| Bulk demand-day verification and a fully verified demo seed | TORY-50 (#72, #74) | Uses the FR-009 / G-06 Option A per-day verification unchanged, for many products at once | Verifying one product-day at a time made forecasts look broken. Every product-day still goes through the same guards and audit record. |
| UX polish: error pages, phone layout, one date format, labels, account page, CSV template, sortable table | TORY-51 (#73), #78, #80, #81 | Usability of existing functions (NFR-005, FR-012) | Found in a browser walkthrough of the demo. No permission or business-behaviour change. |

## Impact assessment

- **Schedule:** delivered within the existing timeboxes before the 27 November 2026 deadline. Each addition was one or two small pull requests.
- **Cost:** SGD 0. No new services, licences or paid tools.
- **Security and data:**
  - The additions reuse the existing authorization helpers. Every page and action enforces the same Manager/Staff and assigned-inventory scope (NFR-001), with tests for Staff and cross-business denial.
  - New writes (inventory management and bulk verification) run in transactions with audit events (NFR-003).
  - Exports are scoped and escaped.
  - The admin is limited to superusers.
- **Verification:** each addition has automated PostgreSQL tests (listed in the traceability matrix) and passed the CI gates from TORY-36: lint, coverage at least 90%, security scans, the Docker image build and, from #79, a browser smoke test.

## Still excluded

The rest of SRS section 2.2 stands unchanged:
- product catalogue import;
- minimum order quantity and pack size;
- microservices, barcode scanning, multi-warehouse operations, purchasing automation, a mobile app and notifications;
- forecasting methods other than the seven-day moving average;
- any production-readiness claim.

Insights shows no monetary forecasts or cost figures. Its only money figure is the current stock value at the inventory's own selling price, which follows from BR-016 and BR-018.
