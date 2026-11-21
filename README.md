# Tory — Inventory Management & Demand Forecasting System

[![Django PostgreSQL CI](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/django-ci.yml/badge.svg?branch=develop)](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/django-ci.yml?query=branch%3Adevelop)
[![Security](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/security.yml/badge.svg?branch=develop)](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/security.yml?query=branch%3Adevelop)
[![Documentation CI](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/docs-ci.yml/badge.svg?branch=develop)](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/actions/workflows/docs-ci.yml?query=branch%3Adevelop)
![Coverage gate: at least 90%](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25-brightgreen)

*Inventory made simple.*

Tory is a Singapore Polytechnic ST0529 CA1 project to manage inventory and provide explainable demand forecasts. One developer works with Codex assistance. The project owner adopted [lightweight Agile Kanban](docs/decisions/ADR-002-agile-kanban-delivery.md) for remaining delivery on **3 November 2026** and added prospective sprint-style, timeboxed cycles on **12 November 2026**. Work before that change remains Kanban delivery, including PRs #34–#37; it is not assigned retrospectively to Sprint 1. Earlier Planning and Requirements records retain their dated Waterfall context.

## Approved baseline

- **Backend:** Django 5.2 LTS
- **Frontend:** Django Templates + Bootstrap, with small amounts of JavaScript where useful ([ADR-003](docs/decisions/ADR-003-frontend-architecture.md))
- **Database:** PostgreSQL
- **Budget:** SGD 0
- **Available project time:** 10–15 hours per week
- **Deadline:** 27 November 2026 at **17:00 Asia/Singapore**
- **Status:** P1 was approved with conditions on 29 October. BR-001–BR-045 and recorded owner decisions remain authoritative; the complete SRS, Requirements exit and Design entry have **not** been approved. Stock movements, CSV import, stock history, TORY-23 demand forecasting and TORY-24 reorder settings/recommendations are implemented on this branch; hosted staging verification remains open.

The backend decision is recorded in [accepted ADR-001](docs/decisions/ADR-001-backend-and-database.md); the frontend choice is recorded in [ADR-003](docs/decisions/ADR-003-frontend-architecture.md). The [Django/PostgreSQL CI workflow](.github/workflows/django-ci.yml) runs on pushes and pull requests to `develop` and `main`; see [CI quality and security gates](#ci-quality-and-security-gates). The controlled failure and correction commits (`d92d838`, `e0a5b0f`) were merged in PR #20; their hosted run URLs are not recorded in this repository. Detailed application architecture, hosting provider and deployment topology remain undecided. Candidate services in the planning documents are research candidates only.

## Repository and Tory-PoC

The main GitHub repository is [`Mike-Franco/ay2627s2-cicdp-MikeAbat`](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat), also used as the course workspace `ay2627s2-cicdp-MikeAbat`. It contains the Tory project records and planning evidence. `Tory-PoC` remains a separate, isolated feasibility experiment. No PoC application source, database, virtual environment, or Git history is included here. PoC reports are retained as historical evidence and must not be read as proof that the Tory product is implemented or production-ready. Their scope and evidence limitations are documented in the reports and [source provenance note](docs/SOURCE_PROVENANCE.md).

## Documentation

- [Planning](docs/planning/): original approved charter/P1 evidence, feasibility and risks, the [current schedule with original baseline retained](docs/planning/PROJECT_SCHEDULE.md), and the [prospective iteration log](docs/planning/AGILE_ITERATION_LOG.md).
- [Requirements](docs/requirements/): owner-approved individual rules and decisions, living gap analysis, role permissions and traceability, plus the complete SRS awaiting approval. A pending gap is addressed before its dependent feature; unrelated gaps do not block all implementation.
- [Architecture and Django framework evidence](docs/design/ARCHITECTURE.md) and [implemented ERD](docs/design/ERD.md).
- [Decisions](docs/decisions/): ADR-001 preserves the backend choice; ADR-002 records the 3 November Kanban adoption and the later prospective sprint-style cadence from 12 November.
- [TORY-27 guarded local backup/restore tool](scripts/tory27_backup_restore.py) and [operator runbook](docs/decisions/TORY-27-local-backup-restore.md); the [off-site backup policy](docs/decisions/TORY-27-offsite-backup-policy.md) is a draft only.
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

## Quick start with Docker

With Docker Desktop (or Docker Engine with the Compose plugin) installed, run from the repository root:

```text
docker compose up --build
```

Then open <http://localhost:8000/login/>. Compose starts PostgreSQL 18 with `track_commit_timestamp=on`, waits for its healthcheck, builds the Tory image, applies migrations on start and serves the app with gunicorn and WhiteNoise. To create the first Manager account:

```text
docker compose exec web python manage.py bootstrap_manager --business-name "Harbour Clinic" --manager-email manager@example.com --inventory "Main Store"
```

Run the full test suite inside the container with:

```text
docker compose run --rm -e DJANGO_ENV=test -e DJANGO_MIGRATE_ON_START=false web python manage.py test --noinput
```

`GET /healthz` returns `200` when the database answers and `503` when it does not. It needs no sign-in and is exempt from the HTTPS redirect so platform probes can call the container directly. Compose runs in `development` mode with local-only default credentials; set `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `POSTGRES_DB`, `DJANGO_ALLOWED_HOSTS` or `TORY_HTTP_PORT` in your shell or a `.env` file to override them. `docker compose down` stops the stack; add `--volumes` to delete the local database.

The image itself defaults to `DJANGO_ENV=production`, runs as an unprivileged `tory` user, and contains no secrets: supply `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and the `POSTGRES_*` variables at run time. Set `WEB_CONCURRENCY` to change the gunicorn worker count, or `DJANGO_MIGRATE_ON_START=false` to run migrations as a separate release step.

## CI quality and security gates

TORY-36 adds these gates. Every push and pull request to `develop` or `main` runs them. A newer push to the same ref cancels the run still in progress.

| Workflow | Job | Fails when |
| --- | --- | --- |
| [Django PostgreSQL CI](.github/workflows/django-ci.yml) | Lint (ruff) | `ruff check` reports a finding |
| | Check, migrate, and test on PostgreSQL | a system check, missing migration or test fails, or line coverage of the app packages is below 90% |
| [Security](.github/workflows/security.yml) | Dependency audit (pip-audit) | a pinned runtime or development requirement has a known vulnerability |
| | CodeQL (python) | analysis fails; alerts appear under **Security → Code scanning** |
| | Secret scan (gitleaks) | a secret pattern is found anywhere in the Git history |
| [Docker image](.github/workflows/docker-ci.yml) | Build image, smoke test and run tests in container | the image fails to build, the stack does not become healthy, `/healthz`, sign-in or static checks fail, the app runs as root, a secret or `.env`/`.git` is in the image, or a test fails in the container |

The Security workflow also runs weekly on Mondays at 02:00 UTC. Each test run uploads the HTML coverage report as the `coverage-html-<sha>` artifact and writes a coverage table to the job summary. [Dependabot](.github/dependabot.yml) opens weekly grouped pull requests into `develop` for pip and GitHub Actions updates. Third-party actions are pinned to full commit SHAs, with the release tag recorded in a comment.

[pyproject.toml](pyproject.toml) holds the ruff and coverage settings. The lint rules target defects: pycodestyle errors and warnings, Pyflakes and bugbear. Findings that existed when the gate was introduced are listed per file, so new files get the full ruleset. Formatting (`ruff format --check`) is not enforced yet, because reformatting the codebase would conflict with open feature branches.

Run the same gates locally from a virtual environment (Windows paths shown):

```text
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\ruff check .
.venv\Scripts\coverage run manage.py test
.venv\Scripts\coverage report
.venv\Scripts\coverage html
.venv\Scripts\pip-audit -r requirements.txt -r requirements-dev.txt
```

A local test run skips the commit-timestamp test unless PostgreSQL has `track_commit_timestamp=on`. CodeQL and gitleaks run only in GitHub Actions.

## Local Django smoke checks

Create a virtual environment and install the pinned dependencies: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt` on Windows (use `.venv/bin/python` on Unix). Set the variables shown in [.env.example](.env.example) in your shell; Django does **not** load that file automatically. Create a local PostgreSQL database and role with permission to create a test database. A PostgreSQL server is required for every Django command here; there is **no SQLite fallback**.

Run `.venv\Scripts\python manage.py check`, `.venv\Scripts\python manage.py migrate --noinput`, then `.venv\Scripts\python manage.py test --verbosity 2` (substitute the Unix interpreter path where needed). The smoke tests exercise the custom email user model through Django's ORM and inspect migrations on a newly created PostgreSQL test database. They are framework checks, not stock-feature acceptance tests. Use unique secrets and reviewed TLS, host and proxy settings for staging/production; local or CI-only values must never be deployed. The CI PostgreSQL service uses disposable test credentials only.

## Local sign-in increment

Run the same migrations and tests above against PostgreSQL, then start `python manage.py runserver`. The sign-in page is at `/login/`; successful sign-in opens the authenticated home page at `/`. Sign-out is a CSRF-protected POST from that page. Email identity is unique and case-insensitive under the 3 November TORY-10 owner clarification. TORY-11 adds an operator-run initial Manager setup command; it does not add public account creation. Use only disposable test accounts in local development. The login tests cover PostgreSQL-backed throttling and server-checked session expiry; they do not establish hosted security, email delivery or stock-feature acceptance. Review TLS termination and proxy IP handling before staging.

## Initial Manager bootstrap

After database migrations, an operator can create a new business, its initial inventories, and an ordinary Manager explicitly assigned to every inventory created by that invocation:

```text
python manage.py bootstrap_manager --business-name "Harbour Clinic" --manager-email manager@example.com --inventory "Main Store" --inventory "Cold Room"
```

The command prompts twice for a hidden Manager password and applies the 16 November 2026 owner-approved policy for newly set passwords: at least 15 characters, not in Django's bundled common-password list, and not too similar to the user's attributes under Django's default check. No uppercase, digit or symbol mixture is required. Validation runs only when setting a password; existing credentials are not revalidated at sign-in. The command does not accept a password argument or environment variable. A case-insensitive email collision or any invalid input aborts before writing; business, Manager membership, inventories and assignments are created atomically. The Manager is not a Django admin staff member or superuser.

## Staff invitation core

**17 November 2026 implementation increment:** An active Manager with a current active inventory assignment can open `/businesses/<business_id>/staff-invitations/`, select one or more authorised inventories, issue an invitation, inspect scoped invitations, and replace or revoke a pending invitation. Mutations use POST and CSRF. Delivery is opt-in through SMTP environment settings in `.env.example`; the public origin is configured separately and must be HTTPS outside local development. The email link uses a fragment, and `/staff/setup/` removes it from the address bar before a CSRF-protected password POST. Delivery failure leaves a pending invitation eligible for a quota-counted replacement. No provider or real inbox delivery has been verified. Focused browser-flow tests were added but **not run** in this implementation step. This is implementation evidence, not a new owner approval or complete TORY-11 acceptance.

**17 November 2026 verification correction:** The initial focused run found two test-fixture failures among 57 tests; 55 passed, and isolated test database teardown succeeded. The wrapper returned 0 despite Django reporting failure. Corrected sender/host fixtures and delivery-retry assertions were added. The focused suite then passed 57 tests with no failures, errors or skips; test-database teardown succeeded (actual Python exit code 0). Documentation and whitespace checks passed. These checks do not establish JavaScript/browser behavior, actual inbox delivery, zero-cost email feasibility, or complete TORY-11 acceptance.

TORY-11 adds reusable services for preparing, replacing/resending, revoking and redeeming a Staff invitation. The core stores only a purpose-bound token digest, enforces a 24-hour latest-only single-use link, and requires at least one currently Manager-authorised inventory in the same business both at issuance and redemption. Redemption creates a new ordinary Staff account, membership and all selected assignments atomically, applying the approved password policy when the invitee sets a password. The focused PostgreSQL suite previously passed 21 tests with no failures, errors or skips, including issuance, redemption and daily-limit races plus lock-delayed expiry and Singapore-midnight regressions. The lock-coordinated regression tests use events and PostgreSQL lock-state observation, not timing sleeps. Migration consistency previously passed with no changes detected. Existing hosted CI applies only to reviewed commit `03ee259ee7421e4be35aaad18d2943800a74eeb0`; hosted CI for this increment remains pending. The first password-policy targeted run completed 50 test bodies but failed during teardown because a worker connection still held `test_tory`. After adding per-worker connection cleanup, the targeted run passed 50 tests with no failures, errors or skips and Django successfully destroyed `test_tory` (exit code 0). This core has no browser routes or forms and sends no email; those follow separately. Real email delivery is unverified, and overall TORY-11 acceptance remains open. Staff deactivation/reactivation and general multi-business account policy remain open.

**17 November 2026 PR #46 retry correction:** The password setup form now sends a CSRF-protected fetch POST and keeps the fragment token only in script memory across recoverable password errors. The server returns nonsecret JSON, and the browser navigates to sign-in only after explicit success. The focused isolated PostgreSQL suite passed 57 tests (0 failures, errors or skips), Python exit 0, and test-database teardown succeeded. Hosted CI for this correction and actual browser behavior remain pending. Manual browser check: open a fresh invitation link, confirm the fragment disappears, submit mismatched passwords, then a policy-rejected password, then a valid password on the same page; confirm the first two show errors without leaving the page and the valid submission opens sign-in. Reopening that link must fail.

## Password reset core

**17 November 2026 implementation choice:** The delivery-neutral TORY-11 reset service records permitted requests for active, inactive and unknown normalized identities, using separate one-hour rolling identity and source-IP limits (3 and 20). PostgreSQL transaction locks serialize quota and link transitions. Eligible active accounts receive a private, repr-hidden token; only its purpose-bound digest and the issuing password-state digest persist. A new eligible link supersedes the prior pending link. Redemption rechecks the account and password state under locks, applies the configured validators, changes the password and consumes the link atomically, including a final 30-minute expiry check. Django session authentication hashes deny old sessions after the password hash changes. The service has no reset route or email adapter. The focused isolated PostgreSQL suite passed 67 tests with no failures, errors or skips (Python exit 0), including reset concurrent identity-quota and issuance/redemption cases; test-database teardown succeeded. Migration consistency passed with no changes detected (exit 0). This is no new owner approval; browser flow, delivery, hosted CI and complete TORY-11 acceptance remain open.

## Inventory access foundation

TORY-12 adds business-scoped Manager/Staff memberships and explicit inventory assignments. After signing in, `/inventories/` lists only active assigned inventories; `/inventories/<id>/` returns 404 for an unassigned or other-business inventory. Roles alone grant no inventory access. There is no business, membership or assignment setup UI; the TORY-11 bootstrap command creates the initial Manager scope. The invitation core creates the selected initial Staff assignments; ongoing assignment lifecycle/timing remains open under G-13, and concurrent assignment changes remain a G-11 Design dependency.

The [Tory ERD](docs/design/ERD.md) groups implemented account, inventory, stock, audit, CSV and demand-coverage models and shows the inputs for computed forecasts and reorder recommendations.

## Product catalogue foundation

TORY-13 adds a shared business-owned product catalogue and an inventory-product association. `/catalogue/` and `/inventories/<id>/products/` are read-only and show only products linked to inventories the signed-in user may access. Lead time and safety stock are stored per shared product; the optional inventory-specific selling-price slot has provisional numeric storage only and is not displayed as a currency. General catalogue creation/edit/deactivation UI remains deferred while G-13/G-16 questions remain unresolved.

## Inventory product search and filters

TORY-34 adds a GET form to the existing assigned inventory Products page. Search product names or SKUs using a case-insensitive literal substring (outer spaces trimmed, maximum 200 characters), then optionally filter by the existing at/below, above, or unavailable reorder status. Search and status combine; unavailable forecasts/settings and inactive products remain unavailable rather than being classified by physical stock. Clear filters restores the full current list. The page distinguishes an empty inventory from no matching products and reports invalid filters inline. Manager/Staff access and stock actions retain their current permissions. See the [implementation and verification note](docs/decisions/TORY-34-inventory-product-filters.md); formal FR-002 acceptance and hosted evidence remain open.

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

## TORY-26 integrated validation

The [TORY-26 validation note](docs/decisions/TORY-26-integrated-validation.md) maps PostgreSQL accuracy/concurrency coverage and the approved Envelope B protocol. The five ordinary HTTP classes use inventory view, Inventory products, receipt, issue and login; one Demand forecast page request measures forecast and reorder together. `scripts/tory26_http_benchmark.py` creates an isolated synthetic PostgreSQL fixture and records real HTTP timings, and `scripts/tory26_analyze.py` checks sample counts and nearest-rank p95. The original `tory` and TORY-25 demo databases are excluded. Actual local results and their representativeness limits are recorded in the validation note; no hosted performance is inferred.

The three existing ordinary p95 failures are retained as diagnostic evidence. Login profiling found shared-IP PostgreSQL throttle locking across full password checks; authentication settings were not weakened. The isolated seed was activated for 10 November, and `scripts/tory26_prepare_coverage.py` can verify the seven complete dates through the Manager service no earlier than 17 November. The runner now requires numeric forecast/reorder output before measuring and records any unexpected rejected response or timeout as an invalid whole run. No three-run passing result is claimed.

**17 November 2026 PR #47 timing correction:** Reset issuance now locks the account row before sampling the clock used for quota evaluation, attempt time and 30-minute link expiry. The focused `tests.test_password_resets tests.test_auth` isolated PostgreSQL run passed 29 tests with no failures, errors or skips (Python exit 0); the test database was destroyed successfully. The lock-wait and both source-IP limit regressions ran. Earlier 67-test evidence remains separate. Hosted CI for this correction is pending.

## Password reset browser flow

**17 November 2026 implementation work:** `/password/reset/` acknowledges every POST with the same public message while a bounded in-process handoff performs reset eligibility, quota and optional delivery work. Two workers and 32 total queued/running slots are used per process; full or failed handoffs return the same acknowledgement. Workers close database connections. The reset mail adapter uses the configured `STAFF_INVITATION_PUBLIC_ORIGIN`, only SMTP or in-memory test mail, and a finite 10-second SMTP timeout. The link places its token in a URL fragment for `/password/reset/setup/`; the local script clears the fragment and submits confirmed passwords with the rendered CSRF field. No reset browser or mail tests were run in this implementation step. In-process work can be lost on process restart or abrupt shutdown, and separate server processes have separate queues. Browser execution, public timing equivalence, real inbox delivery, hosted CI, zero-cost feasibility and complete TORY-11 acceptance remain pending.

**17 November 2026 reset-web verification correction:** The first isolated reset-web/core/auth/invitation-web run found 43 tests with one failure and one error; teardown succeeded. A disabled origin raised at the private worker helper as designed, while its test had not asserted the exception; the cache test expected an exact header although `never_cache` adds directives. Configuration is now checked before reset issuance, so disabled delivery makes no new link, and a synchronous production-boundary test verifies capacity release and later work. The corrected `tests.test_password_reset_web tests.test_password_resets tests.test_auth tests.test_staff_invitation_web` run passed 44 tests with no failures, errors or skips (Python exit 0); isolated test-database teardown succeeded. Browser execution, public timing equivalence, real delivery, queue durability, hosted CI and complete TORY-11 acceptance remain pending.

**18 November 2026 TORY-11 Staff deactivation implementation (unverified):** An active Manager may deactivate an ordinary Staff account only when all of its membership rows identify Staff in that Manager's business and its sole membership is there, and every assignment row, including inactive rows, falls within the Manager's current active inventory scope. The Manager Staff page exposes only eligible accounts and requires a confirmation followed by CSRF-protected POST. A transactional service rechecks authority under PostgreSQL locks and sets `User.is_active=False`, preserving the account, membership, assignment and attribution records. Existing authentication, protected-view and reset checks deny inactive accounts. Focused tests were added but not run; only `git diff --check` was permitted in this pass. Staff reactivation, general multi-business account policy and complete TORY-11 acceptance remain open.

**17 November 2026 PR #48 HTTPS form correction:** The normal reset-request GET and POST acknowledgement now use `Referrer-Policy: same-origin`, allowing an HTTPS form to provide same-origin referer information for CSRF validation. Token/password setup responses retain `no-referrer`; all pages retain no-store. The focused reset-web/core/auth/invitation-web suite passed 45 tests, zero failures/errors/skips, Python exit 0, with successful isolated test-database teardown. The earlier 43-test failure and 44-test passing runs remain separate evidence. Hosted CI and actual browser execution for this correction remain pending.

**18 November 2026 TORY-11 Staff deactivation focused verification:** Migration consistency reported no changes (actual Python exit 0). The requested isolated PostgreSQL suite ran 86 tests with zero failures, zero errors and zero skips (actual Python exit 0), including the queued target-role-change and assignment-revocation deactivation races; the `test_tory` test database was destroyed successfully. Documentation validation passed 41 Markdown files (exit 0), and `git diff --check` passed (exit 0). These results supersede the earlier unverified status for the focused local checks only. Hosted CI, browser execution and complete TORY-11 acceptance remain pending.
