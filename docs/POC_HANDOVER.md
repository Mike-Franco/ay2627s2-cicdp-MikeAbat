# Tory PoC engineering handover

Prepared: 29 October 2026 | Singapore Polytechnic ST0529 CA1

## 1. Implemented

This isolated feasibility PoC contains a PostgreSQL-only Django project, one Product model (unique SKU, name, nonnegative integer quantity), a stock service, and an atomic CSV importer for stock transactions. The service rejects invalid Python inputs, zero changes, unknown SKUs, insufficient stock, and integer overflow; it uses `transaction.atomic()` and `select_for_update()`. CSV requires the exact `sku,change` header and signed nonzero integer changes. Any tested bad row rolls back earlier rows. A migration creates the product table and database constraints.

Included automated tests cover migration/table setup, SKU uniqueness, direct database rejection of negative quantity, stock-in/out, invalid inputs, insufficient stock, CSV success and repeated SKUs, CSV validation and rollback, and concurrent stock-out. There is no frontend, API, authentication/RBAC, forecast, movement ledger, staging deployment, cloud setup, CI pipeline, or CD pipeline.

## 2. Verified environment and PostgreSQL use

| Component | Observed version or configuration | Evidence |
| --- | --- | --- |
| Python | 3.13.3 | `python --version` |
| Django | 5.2.18 | `.venv\Scripts\python.exe -m pip show Django` |
| PostgreSQL driver | psycopg 3.3.6 | `.venv\Scripts\python.exe -m pip show psycopg` |
| Database server | PostgreSQL 18.3 | Django connection reports server version `18.3` |
| Django database backend | `postgresql` (`django.db.backends.postgresql`) | `manage.py shell` inspected `connection.vendor` and configured engine |
| Database name | `tory_poc` | Live Django connection |

The database is genuinely PostgreSQL. The test suite was run with the PostgreSQL settings and created a temporary PostgreSQL test database named `test_tory_poc`; the migration and all test output completed successfully. No SQLite backend or fallback is present in `config/settings.py`.

## 3. Fresh automated test execution

Command executed from the project directory:

```powershell
.\.venv\Scripts\python.exe manage.py test inventory -v 2
```

PostgreSQL credentials were provided to the process through environment variables; they are omitted here. Exact final summary from this run:

```text
Found 14 test(s).
...
Ran 14 tests in 0.539s

OK
Destroying test database for alias 'default' ('test_tory_poc')...
 OK
System check identified no issues (0 silenced).
```

**Result: 14 passed, 0 failed, 0 skipped, 0 blocked.** Every test was discovered and executed. The complete per-test output is in the terminal history; test names were defined in the PoC-only `inventory/tests.py`, which was not transferred (see [source provenance](SOURCE_PROVENANCE.md)).

### Explicit operation results

| Behavior | Test evidence | Observed result |
| --- | --- | --- |
| Stock-in | `test_stock_in_and_out` | Starting quantity 10; +5 returned 15 |
| Stock-out | `test_stock_in_and_out` | Following -4 returned 11 |
| Insufficient stock | `test_unknown_sku_and_insufficient_stock` | -11 from 10 rejected; quantity remained 10 |
| CSV all-or-nothing | `test_csv_rolls_back_for_malformed_row`, `test_csv_rolls_back_for_broken_quoting`, `test_csv_rolls_back_for_empty_sku_or_blank_row`, `test_csv_rolls_back_for_unknown_sku`, `test_csv_rolls_back_for_insufficient_stock` | Each test applied a valid earlier row followed by an invalid row; each import raised `InventoryError` and the original quantity remained 10 |
| Concurrent stock-out | `test_two_concurrent_stock_outs_only_one_succeeds` | Two PostgreSQL worker connections attempted -8 from 10; one succeeded, one was rejected, final quantity was exactly 2 |

The concurrency test also passed five additional consecutive runs in the prior verified QA session. The fresh complete run above passed it once.

## 4. Remaining incomplete work

The implementation is limited to the PoC requirements. Product catalog workflows, transaction history, UI/API integration, validation at a web boundary, manager/staff permissions, demand forecasting, hosted staging, CI, CD, deployment security, operational monitoring, and production data migration are not implemented or tested. Automated CSV tests use in-memory text streams; no user interface or uploaded-file endpoint exists.

## 5. Security and Git inspection

- `config/settings.py` hardcodes no database password. Database settings are read from environment variables.
- The development secret key has an explicitly insecure fallback (`insecure-local-poc-only`) and `DEBUG=True`. Those settings are suitable only for this local experiment and must be replaced/disabled before any deployed service.
- `.gitignore` excludes `.venv/`, Python bytecode/cache directories, `.env`, `.env.*`, coverage output, and pytest cache; `.env.example` is deliberately allowed.
- `git ls-files` showed `.env.example` but no `.env`, SQLite/database file, credential file, virtual environment, or cache file. A scan of project files found no copy of the supplied PostgreSQL password.
- Git status was `## master` with no changed or untracked files at inspection time. HEAD was `cb304cd poc: validate Django PostgreSQL inventory operations`. No commit or push was performed during this handover task.
- This check verifies the current tracked tree and workspace. It does not prove credentials were never exposed outside these files or in any external backup/log.

## 6. Limitations, assumptions, and technical risks

- Tests used a local PostgreSQL administrator account. A real application should use a dedicated least-privilege database role.
- PostgreSQL was 18.3; system software was not upgraded.
- The Product field and explicit named check create duplicate nonnegative checks in PostgreSQL. This is redundant but passed integrity tests.
- Row locking protects changes only when all stock changes use the service. Future code must not update `quantity` through an unlocked path.
- CSV encoding is expected to be a decoded text stream. The interface is not an HTTP upload handler.
- The concurrency test covers two simultaneous stock-out requests for one product. It does not benchmark load, deadlocks involving many products, retries, multiple hosts, or failure recovery.
- The development settings use `DEBUG=True` and an insecure fallback secret. No production-readiness claim is made.
- The owner-approved framework selection is Django 5.2 LTS + PostgreSQL, recorded in [ADR-001](decisions/ADR-001-backend-and-database.md). CI implementation, staging deployment, and out-of-scope Tory behavior remain unresolved.

## 7. Feasibility conclusion and recommendation

The verified evidence demonstrates that Django 5.2.18 can run migrations and perform the tested inventory operations against PostgreSQL 18.3. Database constraints rejected negative quantity, CSV batches rolled back on tested errors, and concurrent stock-outs did not oversell in the tested scenario. This supports Django + PostgreSQL as technically feasible for this narrow PoC.

The PoC does not prove the selected Tory stack is production-ready, secure for deployment, performant at expected scale, or suitable for untested requirements. The owner-approved selection is recorded in [ADR-001](decisions/ADR-001-backend-and-database.md). Proceed through Requirements and Design, use least-privilege database access and secure deployment settings as explicit criteria, and investigate broader load and operational behavior if those requirements affect the design.

## 8. Files in the committed PoC

- `.env.example`
- `.gitignore`
- `README.md`
- `requirements.txt`
- `manage.py`
- `config/__init__.py`
- `config/settings.py`
- `config/urls.py`
- `config/wsgi.py`
- `inventory/__init__.py`
- `inventory/apps.py`
- `inventory/models.py`
- `inventory/services.py`
- `inventory/csv_import.py`
- `inventory/tests.py`
- `inventory/migrations/__init__.py`
- `inventory/migrations/0001_initial.py`
- `docs/POC_RESULTS.md`
- `docs/TECHNICAL_FEASIBILITY.md`
- `docs/POC_HANDOVER.md` (this report; newly added and not part of the earlier commit)
