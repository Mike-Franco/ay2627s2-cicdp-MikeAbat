# Tory: Django and PostgreSQL technical feasibility

Singapore Polytechnic ST0529 CA1 | Planning stage | 29 October 2026

## 1. Purpose and scope of the proof of concept

Tory's proposed system needs dependable inventory movements before its technology stack can be approved. This disposable PoC tests whether Django can use PostgreSQL to store a minimal product, apply safe stock changes, import stock transactions atomically, and prevent overselling during concurrent updates. It is separate from the eventual Tory application. It does not implement a frontend, API, roles, forecasting, supplier settings, or deployment. A passing PoC is evidence for feasibility, not a framework selection.

## 2. Technology stack and reasons for evaluating it

The environment used Python 3.13.3, Django 5.2.18, psycopg 3.3.6, and PostgreSQL 18.3. Django's model, migration, and transaction features were evaluated for readable inventory code. PostgreSQL was required to test database constraints and real row locking; SQLite is not configured. These are evaluation reasons, not comparative findings against other frameworks. The PoC-only `requirements.txt` and `config/settings.py` were not transferred; see the recorded environment checks in [POC_RESULTS.md](POC_RESULTS.md) and [source provenance](SOURCE_PROVENANCE.md).

## 3. Technical feasibility experiments and methodology

- Apply the PoC-only `inventory/migrations/0001_initial.py` to a disposable PostgreSQL database. Test unique SKU and reject a negative quantity through raw SQL.
- Call the PoC-only `inventory/services.py` stock service for valid and invalid signed integer changes. It validates input, locks the product with `select_for_update()`, checks the balance, and saves inside `transaction.atomic()`.
- Feed the PoC-only `inventory/csv_import.py` importer `sku,change` transaction rows. Put a bad row after a valid row and confirm the original quantity remains, proving rollback of the whole import.
- Under a proposed PoC assumption, reject a header-only file; also verify that a 5000-digit integer becomes `InventoryError` rather than leaking a conversion exception.
- Run the PoC-only `inventory/tests.py` concurrency test using `TransactionTestCase`, two threads, two distinct PostgreSQL backend connections, and a barrier before both request stock-out of 8 from an initial quantity of 10. Assert one success, one rejection, and a final quantity of 2.
- Run the complete suite, run it in shuffled order, and repeat the concurrency test five times. The commands and observed summaries are recorded in [POC_RESULTS.md](POC_RESULTS.md).

## 4. Test results

| Experiment | Expected outcome | Actual observed outcome | Status | Evidence |
| --- | --- | --- | --- | --- |
| PostgreSQL connection and migration | Use PostgreSQL; create Product table | Backend reported `postgresql`, server 18.3; migrations applied `OK` | Pass | PoC-only `config/settings.py`; [command log](POC_RESULTS.md) |
| Product integrity | Unique SKU; quantity cannot be negative in DB | Duplicate SKU and raw negative SQL update raised `IntegrityError` | Pass | PoC-only `inventory/tests.py`; [command log](POC_RESULTS.md) |
| Stock movements | Valid changes update quantity; invalid or excessive changes are rejected | Valid +5 and -4 produced 11 from 10; invalid inputs, unknown SKU, and insufficient stock were rejected | Pass | PoC-only `inventory/tests.py` and `inventory/services.py` |
| CSV transaction import | Exact header and integer rows; any bad row rolls back prior rows | Successful repeated-SKU import; invalid value, broken quoting, blank row, empty or unknown SKU, and insufficient stock all left the original quantity unchanged | Pass | PoC-only `inventory/tests.py` and `inventory/csv_import.py` |
| Header-only and huge integer CSV | Reject empty batch and normalize extreme integer input to `InventoryError` | Both inputs rejected without stock change | Pass | PoC-only `inventory/tests.py` |
| Concurrent stock-out | No lost update or overselling | Exactly one of two concurrent -8 requests succeeded; final quantity was 2. The case passed five additional runs | Pass | PoC-only `inventory/tests.py`; [command log](POC_RESULTS.md) |
| Suite and ordering | Tests pass independently | Full suite: 14 passed, 0 failed; shuffled suite with seed 24680: 14 passed, 0 failed | Pass | [Command log](POC_RESULTS.md) |

## 5. Risks, limitations and unresolved issues

- The concurrency case covers one competing stock-out pattern on local PostgreSQL. It does not measure performance, lock wait times, or larger workloads.
- Tests used a PostgreSQL administrator account. A later implementation should use a restricted application role. PostgreSQL 18.3 was not upgraded during this PoC.
- The explicit nonnegative check duplicated the database check created by `PositiveIntegerField`; it was removed in migration `0002`, leaving the field constraint.
- The local settings include a development-only fallback secret key and `DEBUG=True`; they must not be used for deployment. Git history contains commit `cb304cd`. At the start of this review, `docs/POC_HANDOVER.md` was untracked; check current status before committing changes.
- No HTTP flow, authentication, Manager/Staff permissions, 7-day forecast, supplier settings, staging hosting, CI, or CD was tested. These remain separate requirements and delivery risks.

## 6. Preliminary evaluation of Django + PostgreSQL

**Strengths demonstrated:** Django migrations worked with PostgreSQL; model and database constraints protected Product data; the service and CSV importer used transactions; row locking prevented overselling in the tested concurrent case. The implementation used only Django and psycopg beyond Python's standard library.

**Tradeoffs and uncertainty:** The PoC requires PostgreSQL setup and test-database permissions. Correct stock behavior depends on routing every movement through the locked service. The tests do not show how the stack performs with the full Tory feature set or in hosted staging. The project owner has approved Django 5.2 LTS + PostgreSQL for the Planning baseline in [ADR-001](decisions/ADR-001-backend-and-database.md); this report supports only narrow technical feasibility and does not establish full-product suitability or production readiness.

## 7. Recommendations and next steps before formal Waterfall Requirements/Design approval

1. Record the complete functional and nonfunctional requirements, including CSV format, roles, forecasting explanation, audit needs, and concurrency expectations.
2. Carry the approved Django + PostgreSQL stack into Requirements and Design; resolve staging hosting, CI setup, team capacity (solo developer) and expected workload as applicable. Any stack change requires formal change control.
3. Design a movement ledger, permission boundaries, error handling at the application boundary, and least-privilege database access before implementation.
4. Re-run the PoC tests in the chosen CI environment using PostgreSQL. Do not count SQLite-based runs as concurrency evidence.

### Manual evidence capture

No screenshots were generated for this report. If screenshots are required for submission, run the commands in the separate Tory-PoC workspace, set the PostgreSQL environment variables as described in its PoC README, and capture: (a) `manage.py migrate` showing applied migrations or `No migrations to apply`; (b) `manage.py test inventory -v 2` showing `Ran 14 tests` and `OK`; and (c) `manage.py test inventory.tests.ConcurrentStockTests -v 2` showing its test name and `OK`. Include the command and visible outcome in each image. Crop or redact any password, environment-variable value, or unrelated personal information before submission. Re-run commands when capturing; the historical output recorded here is not a screenshot. The PoC README and source are not included in this repository.
