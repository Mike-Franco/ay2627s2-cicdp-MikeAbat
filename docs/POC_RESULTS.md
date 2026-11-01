# Tory PoC technical feasibility results

Date: 2026-10-29. Stage: Planning / Technical Feasibility. This is an isolated experiment, not the Tory application or production application code. The project owner approved Django 5.2 LTS + PostgreSQL for the Planning baseline; see [ADR-001](decisions/ADR-001-backend-and-database.md). This report records narrow PoC evidence and does not itself make that selection.

## Environment and commands

| Check | Command | Observed outcome |
| --- | --- | --- |
| Python | `python --version` | Python 3.13.3 |
| PostgreSQL | `Get-Service -Name 'postgresql*'`; `pg_isready`; `psql -h localhost -U postgres -d postgres -w -tAc 'SELECT current_user, current_setting(''server_version'')'` | Service running, port 5432 accepting connections, `postgres|18.3` |
| Python dependencies | `.\\.venv\\Scripts\\python.exe -m pip show Django psycopg psycopg-binary` | Django 5.2.18; psycopg and psycopg-binary 3.3.6 |
| Django checks | `.\\.venv\\Scripts\\python.exe manage.py check` | `System check identified no issues (0 silenced)` |
| Migration consistency | `.\\.venv\\Scripts\\python.exe manage.py makemigrations --check --dry-run` | `No changes detected` |
| Database migration | `.\\.venv\\Scripts\\python.exe manage.py migrate` | contenttypes and inventory initial migrations applied, all `OK` |
| Full QA suite | `.\\.venv\\Scripts\\python.exe manage.py test inventory -v 2` | `Found 14 test(s)`; `Ran 14 tests in 0.630s`; `OK` — **14 passed, 0 failed** |
| Shuffled order | `.\\.venv\\Scripts\\python.exe manage.py test inventory --shuffle=24680 -v 1` | `Ran 14 tests in 0.506s`; `OK` — **14 passed, 0 failed** |
| Concurrency repetition | `.\\.venv\\Scripts\\python.exe manage.py test inventory.tests.ConcurrentStockTests -v 0` repeated five times | Each run: `Ran 1 test`, `OK`; **5 passed, 0 failed** |

Database commands used `PGUSER=postgres` and the user-supplied password through the process environment. The password is not stored in project files. The disposable `tory_poc` database was created and the test runner created and destroyed `test_tory_poc`.

## Experiment outcomes

| Experiment | Evidence | Outcome |
| --- | --- | --- |
| Product model and migration | Initial migration and unique-SKU test | Passed |
| Nonnegative quantity in database | Raw negative SQL `UPDATE` raised `IntegrityError` | Passed |
| Stock-in and stock-out | Service tests for +5 and -4 | Passed |
| Invalid movement, unknown SKU, insufficient stock | Rejection tests; quantity unchanged | Passed |
| Atomic CSV import | Successful and repeated-SKU tests; malformed row, broken quoting, blank row, empty SKU, unknown SKU, and insufficient-stock rollback tests | Passed |
| CSV shape validation | Missing/duplicate/invalid headers, zero change, missing/extra columns rejected | Passed |
| Header-only CSV | Rejected under the proposed PoC assumption that imports contain at least one transaction | Passed |
| Extremely large CSV integer | 5000-digit quantity returns `InventoryError`; no stock change | Passed |
| Concurrent stock-out | `TransactionTestCase`; two threads, separate PostgreSQL backend PIDs, simultaneous -8 attempts from 10 | Passed: one success, one rejection, final quantity exactly 2; passed five additional runs |

## Limitations and conclusion

- PostgreSQL 18.3 is older than the currently published 18.6 maintenance release. No system-level upgrade was attempted.
- Tests used a local PostgreSQL administrator account for convenience. A final system should use a least-privilege application role.
- Django's `PositiveIntegerField` creates a database nonnegative check. The duplicate explicit check was removed in migration `0002`; subsequent migration and test runs verify the remaining field constraint.
- Git history contains `cb304cd` (`poc: validate Django PostgreSQL inventory operations`) as its only commit. At the start of this review, `docs/POC_HANDOVER.md` was untracked. `.gitignore` excludes `.env`, `.env.*` except `.env.example`, `.venv`, and Python caches. Check live Git status before committing these review changes.
- This PoC does not test HTTP endpoints, RBAC, forecasting, deployment, a transaction ledger, or operational load. Those are outside the agreed scope.
- The concurrency test verifies this specific competing stock-out scenario on local PostgreSQL. It is not a load or performance benchmark.

**Conclusion:** Django 5.2 with PostgreSQL is technically feasible for the isolated inventory transactions tested here. The final backend selection is recorded in [ADR-001](decisions/ADR-001-backend-and-database.md). Continue to define and verify the full requirements, architecture, operations and delivery constraints at the appropriate Waterfall gates; this PoC does not establish full-product readiness.
