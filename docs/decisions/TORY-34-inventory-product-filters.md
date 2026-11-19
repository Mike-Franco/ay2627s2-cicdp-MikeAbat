# TORY-34 inventory product search and reorder-status filters

**Date:** 19 November 2026. **Scope:** A bounded improvement to the existing assigned-inventory Products page, selected as the next feature after PR #54. This records implementation choices and verification evidence; it does not approve the complete SRS or close TORY-27.

## Behavior

- The existing `/inventories/<inventory_id>/products/` route accepts a GET form. No new search endpoint is introduced.
- `q` searches product name or SKU using a case-insensitive literal substring. Outer whitespace is trimmed; the maximum is 200 characters. SQL wildcard characters are treated literally by Django's ORM lookup.
- `reorder` accepts an empty value (all), `attention` (at or below the reorder point), `above`, or `unavailable`. Search and status combine, retaining existing SKU/primary-key ordering.
- Status uses the current `recommendation()` result, including its exact threshold equality and expiry-aware availability. Missing forecast coverage/settings, inactive products, and rejected recommendations stay unavailable; zero physical stock alone does not imply a reorder alert.
- Authorization resolves the selected inventory before validating or applying filters. Only currently assigned same-business inventory products enter the search, result count, or status calculation. Existing Manager/Staff action permissions remain.
- The page shows filtered and total counts, preserves the submitted form, and provides a clear-filters link. An empty inventory and a nonempty inventory with no matches have distinct messages.
- Invalid status values or overlong searches return HTTP 400 with field errors and no product results. The form works without JavaScript, has explicit labels, and stacks its controls on small screens.

## Implementation

`InventoryProductFilterForm` in `catalogue/forms.py` validates the two parameters. `inventory_products` in `catalogue/views.py` narrows the existing authorized queryset before its stock calculations, then optionally filters the existing recommendation states. `templates/catalogue/inventory_products.html` renders the GET controls and result/empty states; `static/tory/pages.css` supplies responsive layout rules. No schema or stock service changes are required.

`tests/test_inventory_product_filters.py` adds PostgreSQL-backed checks for name/SKU matching, literal wildcard handling, real numeric/unavailable recommendation states, combined filters, expired-stock availability, no matches, empty inventories, invalid input, escaped redisplay, selected-inventory isolation, authorization, role actions, and unchanged stock/receipt history.

## Verification

Local verification used an isolated PostgreSQL 18.3 instance with commit-time tracking enabled, Python 3.12.14, Django 5.2.18 and psycopg 3.3.6. It used disposable databases in this execution workspace; no existing Windows database or service was accessed.

- The corrected focused run of `tests.test_inventory_product_filters`, `tests.test_catalogue` and `tests.test_reorder` passed all 34 tests, including the 14 new feature tests, with zero failures/errors/skips and process exit 0. Test-database teardown succeeded.
- The full suite ran 279 tests: 278 passed, one development-only static-route check was skipped under the test environment, and there were zero failures/errors (exit 0). The skip is `ConfigurationSmokeTests.test_local_static_route_is_limited_to_project_assets`; it is conditional on development mode with DEBUG false. Test-database teardown succeeded.
- Migration consistency reported no changes (exit 0). Django system checks, Python syntax compilation, documentation validation for 45 Markdown files, and Git whitespace checks passed.

The initial focused run had one fixture error in 34 tests: PostgreSQL correctly rejected a receipt whose expiry was already today on the real server, despite a Python clock patch. The fixture was corrected to receive valid future-expiry stock and exercise the future Singapore midnight boundary, following the existing reorder tests. A separate intermediate retry ran no tests because its disposable server had ended; the final verification kept server and tests in one controlled process lifetime. No stock or expiry guard was relaxed.

The browser walkthrough remains pending. Browser automation could not launch in this runtime: its bundled headless executable was unavailable, and the installed Chromium launch was blocked by unavailable Unix-domain sockets. No visual, mobile-layout or browser interaction pass is claimed. The manual checklist below remains applicable.

Hosted CI remains pending because the GitHub connection rejected repository-content creation with HTTP 403 and the execution workspace had no Git push credentials. Delivery is a reviewable patch, not a remote branch, commit or pull request. Earlier backup, restore, encryption and performance evidence is not evidence for this feature; no new performance acceptance is claimed.

## Manual review

1. Sign in as an assigned Staff user and open an inventory's Products page.
2. Search for part of a product name, then part of its SKU using different letter case. Confirm only that inventory's matching rows appear.
3. Combine the search with each reorder status. Compare a matching row with its Demand forecast page; unavailable inputs must not produce a numeric alert.
4. Search for a nonexistent value, then clear filters. Confirm the no-match message and complete-list restoration.
5. Repeat as an assigned Manager; check that CSV import and Manager-only stock actions retain their role restrictions. Direct access to an unassigned inventory must still fail.
6. Check the form at a narrow mobile width and with JavaScript disabled.

Formal FR-002 acceptance, broader search requirements, pricing display, hosted performance and deployment remain separate. Existing failed performance measurements and unapproved recovery-policy proposals are unchanged.
