# Tory — Inventory Management & Demand Forecasting System

*Inventory made simple.*

Tory is a Singapore Polytechnic ST0529 CA1 project to manage inventory and provide explainable demand forecasts. One developer works with Codex assistance. The project owner adopted [lightweight Agile Kanban](docs/decisions/ADR-002-agile-kanban-delivery.md) for remaining delivery on **3 November 2026** and added prospective sprint-style, timeboxed cycles on **12 November 2026**. Work before that change remains Kanban delivery, including PRs #34–#37; it is not assigned retrospectively to Sprint 1. Earlier Planning and Requirements records retain their dated Waterfall context.

## Approved baseline

- **Backend:** Django 5.2 LTS
- **Frontend:** Django Templates + Bootstrap, with small amounts of JavaScript where useful ([ADR-003](docs/decisions/ADR-003-frontend-architecture.md))
- **Database:** PostgreSQL
- **Budget:** SGD 0
- **Available project time:** 10–15 hours per week
- **Deadline:** 27 November 2026 at **17:00 Asia/Singapore**
- **Status:** P1 was approved with conditions on 29 October. BR-001–BR-045 and recorded owner decisions remain authoritative; the complete SRS, Requirements exit and Design entry have **not** been approved. Stock movements, CSV import, stock history and TORY-23 demand forecasting are implemented on this branch; hosted staging verification remains open.

The backend decision is recorded in [accepted ADR-001](docs/decisions/ADR-001-backend-and-database.md); the frontend choice is recorded in [ADR-003](docs/decisions/ADR-003-frontend-architecture.md). The [Django/PostgreSQL CI workflow](.github/workflows/django-ci.yml) runs on pull requests to `develop` and `main`. The controlled failure and correction commits (`d92d838`, `e0a5b0f`) were merged in PR #20; their hosted run URLs are not recorded in this repository. Detailed application architecture, hosting provider and deployment topology remain undecided. Candidate services in the planning documents are research candidates only.

## Repository and Tory-PoC

The main GitHub repository is [`Mike-Franco/ay2627s2-cicdp-MikeAbat`](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat), also used as the course workspace `ay2627s2-cicdp-MikeAbat`. It contains the Tory project records and planning evidence. `Tory-PoC` remains a separate, isolated feasibility experiment. No PoC application source, database, virtual environment, or Git history is included here. PoC reports are retained as historical evidence and must not be read as proof that the Tory product is implemented or production-ready. Their scope and evidence limitations are documented in the reports and [source provenance note](docs/SOURCE_PROVENANCE.md).

## Documentation

- [Planning](docs/planning/): original approved charter/P1 evidence, feasibility and risks, the [current schedule with original baseline retained](docs/planning/PROJECT_SCHEDULE.md), and the [prospective iteration log](docs/planning/AGILE_ITERATION_LOG.md).
- [Requirements](docs/requirements/): owner-approved individual rules and decisions, living gap analysis, role permissions and traceability, plus the complete SRS awaiting approval. A pending gap is addressed before its dependent feature; unrelated gaps do not block all implementation.
- [Decisions](docs/decisions/): ADR-001 preserves the backend choice; ADR-002 records the 3 November Kanban adoption and the later prospective sprint-style cadence from 12 November.
- [Technology evaluation](docs/TECHNOLOGY_EVALUATION.md): comparative assessment and remaining evidence caveats.
- [PoC evidence](docs/POC_RESULTS.md), [technical feasibility](docs/TECHNICAL_FEASIBILITY.md), and [PoC handover](docs/POC_HANDOVER.md): historical experiment reports and limitations.
- [Documentation provenance](docs/SOURCE_PROVENANCE.md): source workspace, transfer scope, and evidence boundary.

## Assignment context

The repository retains its course-workspace name, `ay2627s2-cicdp-MikeAbat`; Tory is the project documented within it. Course: Singapore Polytechnic ST0529 CA1.

## Development workflow

Use the TORY board: **To Do → In Progress → Review/Test → Done**, with a **work-in-progress limit of one item in In Progress**. Prioritize stock correctness, then dependent security and delivery risks. Each Jira issue should cite relevant BR/FR/NFR and G-gap references, state acceptance criteria, and link its implementation pull request and automated test evidence when available. From 12 November, use the [iteration log](docs/planning/AGILE_ITERATION_LOG.md) for timeboxed goals, dates, reviews and retrospectives. The current simple Jira board does not expose native sprint assignment or reporting; Jira remains authoritative for issue states and linked PR/test evidence. Review changes in small pull requests and update living requirements/traceability evidence without rewriting historical approvals. See [ADR-002](docs/decisions/ADR-002-agile-kanban-delivery.md) and the [schedule](docs/planning/PROJECT_SCHEDULE.md).

## Documentation CI

The [documentation workflow](.github/workflows/docs-ci.yml) runs on pushes to `main` and `develop` and pull requests targeting either branch. It uses a read-only GitHub token, a pinned checkout action, a five-minute job timeout and no paid tools. The [checker](scripts/check_docs.py) uses only Python's standard library. Its small ruleset requires UTF-8 Markdown, one level-one heading at the start of each document, a final newline, no tab characters, no merge-conflict markers in checked text files, and the listed key project documents. It permits existing two-space Markdown line breaks and does not reformat approved Planning records. It is not a secrets scan or proof that the documents contain no secrets.

Run locally with `python scripts/check_docs.py` (or `python3 scripts/check_docs.py`). After a push or pull request to `main` or `develop`, check **Actions → Documentation CI → Check documentation** for the intended commit. The Django/PostgreSQL workflow is separate; PR #20 contains its controlled failing and restored passing test commits. Record the corresponding hosted run URLs when available.

## Local Django smoke checks

Create a virtual environment and install the pinned dependencies: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt` on Windows (use `.venv/bin/python` on Unix). Set the variables shown in [.env.example](.env.example) in your shell; Django does **not** load that file automatically. Create a local PostgreSQL database and role with permission to create a test database. A PostgreSQL server is required for every Django command here; there is **no SQLite fallback**.

Run `.venv\Scripts\python manage.py check`, `.venv\Scripts\python manage.py migrate --noinput`, then `.venv\Scripts\python manage.py test --verbosity 2` (substitute the Unix interpreter path where needed). The smoke tests exercise the custom email user model through Django's ORM and inspect migrations on a newly created PostgreSQL test database. They are framework checks, not stock-feature acceptance tests. Use unique secrets and reviewed TLS, host and proxy settings for staging/production; local or CI-only values must never be deployed. The CI PostgreSQL service uses disposable test credentials only.

## Local sign-in increment

Run the same migrations and tests above against PostgreSQL, then start `python manage.py runserver`. The sign-in page is at `/login/`; successful sign-in opens the authenticated home page at `/`. Sign-out is a CSRF-protected POST from that page. Email identity is unique and case-insensitive under the 3 November TORY-10 owner clarification. This increment has no account-creation route or Manager/Staff/inventory assignment; initial Manager provisioning remains an owner decision. Use only disposable test accounts in local development. The login tests cover PostgreSQL-backed throttling and server-checked session expiry; they do not establish hosted security, email delivery or stock-feature acceptance. Review TLS termination and proxy IP handling before staging.

## Inventory access foundation

TORY-12 adds business-scoped Manager/Staff memberships and explicit inventory assignments. After signing in, `/inventories/` lists only active assigned inventories; `/inventories/<id>/` returns 404 for an unassigned or other-business inventory. Roles alone grant no inventory access. There is no business, membership or assignment setup UI; initial Manager provisioning and assignment lifecycle/timing remain open under G-13, and concurrent assignment changes remain a G-11 Design dependency.

The implemented authorization and catalogue relationships and PostgreSQL same-business integrity guards are shown in the [Tory ERD](docs/design/ERD.md). It covers the current auth/business/inventory/product foundation; stock and forecast tables remain future work.

## Product catalogue foundation

TORY-13 adds a shared business-owned product catalogue and an inventory-product association. `/catalogue/` and `/inventories/<id>/products/` are read-only and show only products linked to inventories the signed-in user may access. Lead time and safety stock are stored per shared product; the optional inventory-specific selling-price slot has provisional numeric storage only and is not displayed as a currency. General catalogue creation/edit/deactivation UI remains deferred while G-13/G-16 questions remain unresolved.

## Manual receiving increment

TORY-16 adds a protected POST + CSRF manual receiving form from an authorized inventory's product list. Manager and Staff can receive an active, linked product only into an active inventory to which they have an active same-business assignment. A product must first have explicit receiving setup; an operator may initialize an unconfigured product with `.venv\Scripts\python manage.py configure_receiving PRODUCT_ID --base-unit-label each --expiry-tracking-required false` (use the equivalent Unix virtual-environment path). Existing products migrate active and unconfigured. The command is not a catalogue UI or a business-role privilege.

The receipt, request token, per-inventory physical balance, committed sequence and one non-demand audit event are atomic in PostgreSQL. Same-token retries return the original receipt only after current authorization is rechecked. The [ERD](docs/design/ERD.md) documents implemented receipt entities and PostgreSQL guards. Hosted staging verification remains open.

## Stock CSV import

An assigned Manager selects an inventory and opens `/inventories/<inventory_id>/import/`. The upload accepts the approved strict UTF-8 `sku,change` contract, up to 262,144 raw bytes and 1,000 data rows. Each non-tracked positive row creates a separate undated receiving batch; negative rows use eligible FEFO/FIFO stock. Rows apply sequentially in one PostgreSQL transaction. A successful import retains the exact raw bytes for same-inventory duplicate checking and links each receipt or issue to its import and row number. Invalid or duplicate files leave no successful import, stock or audit mutation. The Stock history page shows the import identity and row for CSV movements. This does not add historical correction or daily demand verification; those remain TORY-23 scope.

## Stock balances and history

The assigned inventory product page shows physical units, quarantined units and available-to-issue units. Quarantine is derived from each batch's Singapore expiry date, so availability changes at midnight even when the expiry audit event is still pending. The Stock history link opens `/inventories/<inventory_id>/products/<product_id>/history/` for an active assigned Manager or Staff account. It lists committed receipt, issue, adjustment, expiry quarantine and disposal audit events for that inventory and product, including attribution, quantities and applicable reasons. Expiry entries show both the effective boundary and the recording time. History remains visible for inactive products and deactivated past actors; the view does not provide export or mutation controls.

## Demand observation and forecast

TORY-23 calculates average daily demand from seven explicitly verified complete Asia/Singapore dates for one product in one assigned inventory. An assigned Manager verifies a complete date or marks a previously verified date incomplete with a reason on the product's Demand forecast page. No historical correction or reverification path is provided in the CA1 MVP. Missing, incomplete, late-changed, or unresolved-attribution dates suppress the numeric forecast and dependent recommendation. Manual issues use their action time; CSV issues use a separately finalized actual PostgreSQL commit time. The earlier `StockImport.committed_at` field remains a pre-commit completion sample and is never used for forecast attribution.

An operator activates coverage for an environment with `python manage.py activate_demand_observation YYYY-MM-DD`, choosing a future Singapore date. Earlier and partial dates are never counted. This requires PostgreSQL `track_commit_timestamp=on` at server start; the local Tory database now reports `on`. CSV stock imports continue with tracking off, but forecasts stay unavailable. `python manage.py finalize_commit_times` retries pending import and activation finalization after a crash. The command should be scheduled and monitored; PostgreSQL may remove old commit timestamp data during vacuum, so unresolved records must not be silently assigned a date. The local PostgreSQL suite passed 133 tests with no skips on commit `b2e4222`, and [Django PostgreSQL CI](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/runs/42554980980) and [Documentation CI](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/runs/42554980773) passed for that commit. These runs did not hold a real transaction across 00:00 Asia/Singapore; hosted staging remains unverified.

## Reorder settings and recommendation

The product's Demand forecast page shows its business-shared lead time and safety stock, expiry-aware available-to-issue units, and the reorder calculation when all inputs are available. A Manager assigned to every active inventory containing the product may edit or clear either setting; assigned Staff can view the advice. Lead time accepts 1–365 calendar days and safety stock accepts 0–2,147,483,647 units. Unset settings and an unavailable seven-day forecast suppress numeric advice. The reorder point uses the exact forecast average, alerts when available units are at or below that point, and shows the suggested whole-unit quantity separately. Pending deliveries are excluded; the advice creates no purchase order.
