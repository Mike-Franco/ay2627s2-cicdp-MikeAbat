# CR-002: Scope additions TORY-52 to TORY-61

**Date:** 23 November 2026
**Status:** Raised by the project owner as Jira TORY-52 to TORY-61 on 22 November 2026, after owner feedback on the staging demo, and approved for implementation the same day
**Change control basis:** [SRS section 10](../requirements/SOFTWARE_REQUIREMENTS_SPECIFICATION.md#10-requirements-verification-and-change-control), item 5
**Previous change request:** [CR-001](../requirements/CHANGE_REQUEST_CR-001_SCOPE_ADDITIONS.md)
**Traceability:** [Requirements Traceability Matrix](../requirements/REQUIREMENTS_TRACEABILITY_MATRIX.md#23-november-2026-update-cr-002)

## Purpose

The owner's walkthrough of the deployed demo raised usability and presentation gaps: finding the way back to the dashboard, recognising inventories and people, reading the dashboard and Insights, and understanding how features work. TORY-52 to TORY-61 address them. Several go beyond the SRS section 2.1 scope or extend CR-001 (dashboard and Insights), so SRS section 10 requires this record. None of them changes an approved business rule (BR-001 to BR-045), the seven-day forecasting method, or the reorder calculation, and none adds a cost.

## Approved additions

| Addition | Ticket / PRs | Relation to approved scope | Rationale |
| --- | --- | --- | --- |
| Safe image uploads: validated, re-encoded WebP pictures, media volume served by Caddy, media in backups and restore tests | TORY-53 (#92) | Infrastructure for the two picture features below; extends NFR-002 and NFR-008 controls to uploaded files | Pictures are untrusted input. Re-encoding strips embedded payloads and location data, and backups must cover them. |
| Navigation: Dashboard link for every role, logo to dashboard, per-inventory group, breadcrumbs from Dashboard | TORY-52 (#93) | Usability of existing pages (NFR-005) | Staff could not find their way back to the dashboard, and the Insights link appeared and disappeared. |
| Product categories, Manager-managed, with filters | TORY-56 (#94, #95 adds migration 0012) | Extends product identity (FR-001) within the business model (BR-016) | Lets the catalogue, dashboard and Insights group and filter products. A category can never cross businesses (database-enforced). |
| Tables with search, filters, sorting and pagination for the catalogue, Staff, invitations and inventories | TORY-57 (#95) | Presentation of FR-001, FR-002 and FR-007 data | Lists had grown past what one unsorted page can show. Scope rules are unchanged and query counts stay constant. |
| User profile: display name, job title, phone, avatar colour and photo, merged with the password page | TORY-55 (#96) | Extends FR-007 accounts; the user edits only their own record | People are shown by name and avatar instead of email. Email, role and assignments remain read-only. |
| Dashboard v2: inventory filter, explained KPI cards, urgency-ordered reorder table, expiring and activity panels | TORY-58 (#97, restored by #100) | Extends the CR-001 dashboard. Presents FR-002, FR-010 and FR-011 results | Answers "what needs reordering or attention" first. New read-only metrics (days of supply, stock-to-sales, 30-day unit turnover, retail value at current selling price) use the stock ledger and verified demand only. |
| Inventory icon, colour and optional picture | TORY-54 (#98) | Presentation of inventories (BR-016 to BR-022); Manager-only, audited | Makes each inventory recognisable at a glance. Icons are a self-hosted Lucide subset (ISC licence); only the icon key is stored. |
| Insights v2: explained charts for stock vs reorder point, intake vs outtake, days-of-supply ranking and value breakdown | TORY-59 (#99) | Extends the CR-001 Insights exception, still read-only and fixed | Each chart states what it shows, how to read it and what to do, with a data table and empty state. No new forecasting method and no money figures beyond retail value at selling price. |
| Manager activity log across all inventories, with filters and CSV export | TORY-61 (#101) | Read-only view of existing audit records (FR-002, NFR-003); Manager-only | Shows who did what in one place instead of per product. Exports are escaped like the other exports. |
| Public landing page and in-app Help per feature | TORY-60 (#102) | Explains existing behaviour (NFR-005); no new data or permissions | Gives visitors a description of Tory and gives users a reference written against the final behaviour of every feature. |

## Impact assessment

- **Schedule:** delivered on 22 and 23 November 2026, before the 27 November 2026 deadline, as one pull request per ticket. All new migrations merged by then: `accounts` 0004, `catalogue` 0011–0012, `inventory_access` 0004.
- **Cost:** SGD 0. Pillow and the Lucide icons are free and open source, and the icons are self-hosted, so no new service is used.
- **Security and data:**
  - Every new page and action reuses the existing authorization helpers. Manager-only features (categories, inventory editing, activity log) and assigned-inventory scope are tested, including Staff and cross-business denial (NFR-001).
  - Uploaded pictures are accepted only as JPEG, PNG or WebP of at most 2 MB that decode correctly. They are re-encoded to WebP of at most 512 px under a random name and served with `nosniff` and a sandboxing CSP. The page CSP is unchanged (`img-src 'self' data:`).
  - Inventory and product changes keep their audit events (NFR-003). The activity log only reads them.
  - Colours are preset keys enforced by database constraints. No inline styles are introduced, so the strict CSP stands.
- **Verification:** each addition has automated PostgreSQL tests (listed in the traceability matrix) and passed all CI gates: lint, coverage, security scans, the Docker image build with in-container tests, and the browser smoke test.
- **Incident during delivery:** the TORY-54 merge (#98) accidentally reverted TORY-58 on `develop`. It was restored exactly by #100 before any release; see the PR descriptions.

## Still excluded

SRS section 2.2 and the CR-001 exclusions stand unchanged. In particular this change adds no catalogue import, barcode scanning, purchasing automation, notifications, mobile app, other forecasting methods, cost or margin figures, or production-readiness claim. Dependency upgrades raised by Dependabot (including Django 6.1) are deferred until after submission.
