# Tory Technology Evaluation & Selection

Singapore Polytechnic ST0529 CA1 | Waterfall stage: Planning | 29 October 2026

**Product:** Tory — *Inventory made simple.*  
**Decision status:** Django 5.2 LTS + PostgreSQL approved by the project owner on 29 October 2026; see [ADR-001](decisions/ADR-001-backend-and-database.md).  
**Evaluation baseline:** Confirmed Tory requirements and the PoC/report files listed below.

## 1. Purpose and scope

This document compares three PostgreSQL-backed server choices for Tory:

| Candidate | Evaluated stack |
| --- | --- |
| A | Django 5.2 LTS + PostgreSQL |
| B | FastAPI + PostgreSQL |
| C | Node.js/Express + PostgreSQL |

The confirmed baseline is manual stock-in, stock-out and adjustments; atomic CSV import for stock transactions only (reject the entire batch if any row is invalid); PostgreSQL; Manager and Staff permissions; per-product supplier lead time, safety stock and reorder settings; explainable 7-day moving-average forecasts and reorder recommendations; and hosted staging with automated CI (CD optional).

Tory is being developed by one person. The developer has stronger practical experience with JavaScript, Node.js/Express, APIs and PostgreSQL; working experience with Python; and is relatively new to Django, having completed this Django/PostgreSQL PoC with AI-assisted coding. The developer intends to use Codex for guided assistance while independently reviewing and testing generated code. These confirmed skills inform the familiarity row; they do not change the distinction between observed PoC evidence and capability assumptions. A/PostgreSQL is the only candidate combination exercised in the PoC. Scores for B and C otherwise remain reasoned estimates from official framework documentation and the amount of application-level assembly implied by the baseline, not benchmark results.

## 2. Evidence reviewed and test-record check

Reviewed `README.md`, `inventory/models.py`, `inventory/services.py`, `inventory/csv_import.py`, `inventory/tests.py`, `docs/POC_RESULTS.md`, `docs/TECHNICAL_FEASIBILITY.md`, and `docs/POC_HANDOVER.md`, along with the present migrations and package pin.

The source currently contains migration `0002_remove_product_product_quantity_nonnegative.py`; `requirements.txt` pins Django 5.2.18. The current `inventory/tests.py` contains 15 test methods (14 `InventoryTests` methods and one concurrency method). Checked-in results and handover reports record 14/14. The project owner reports a later 16/16 run, but no matching test output or report exists in the available workspace, so that result remains **owner-reported and not independently verified**. This review did not execute tests. A fresh run was not safe or available: no PostgreSQL connection variables, including `PGPASSWORD`, are set in the current process, and `pg_isready`/`psql` are unavailable. Thus server availability and whether Django's disposable `test_tory_poc` database is absent or safe to replace could not be checked. The 16-test run could have used source not present in the current workspace; the discrepancy remains unresolved. Test-method count alone does not establish the number discovered in any particular run.

Demonstrated PoC evidence is limited to Django + PostgreSQL: migration and database constraint behavior, signed stock changes, transactional CSV rollback for covered invalid inputs, and one tested two-connection concurrent stock-out scenario. The checked-in handover reports 14 passing tests; the results report 14 passing in full and shuffled runs and five additional passing concurrency runs. The owner reports a later 16/16 run, but supporting output is unavailable here. All are historical reports, not runs performed for this evaluation. Neither RBAC, forecast/reorder behavior, staging, CI/CD, nor operational load is demonstrated.

## 3. Method and weights

Scores use a 1–5 scale: **1 = weak fit/high effort or risk; 3 = adequate/neutral fit; 5 = strong fit/low effort or risk**. Scores assess fit to the confirmed Tory baseline for a small project, not general framework quality. The score rationale below identifies observed PoC evidence separately from documentation-backed capabilities and reasoned assumptions.

| Criterion | Weight | What is assessed |
| --- | ---: | --- |
| Transaction correctness and data integrity | 25% | Safe concurrent stock changes, constraints, transaction boundaries and atomic batch import |
| Development speed and complexity | 20% | Amount of framework and supporting code/configuration needed for the confirmed workflows |
| Security and role management | 15% | Practical support for authenticated Manager/Staff authorization and secure defaults |
| Maintainability and testing | 15% | Clear conventions, schema evolution, test support and ongoing ownership |
| Solo-developer familiarity and learning curve | 10% | Confirmed practical experience and learning burden for the one developer |
| Forecasting and data processing integration | 10% | Fit for transparent moving averages and explainable recommendation logic |
| Staging deployment and CI compatibility | 5% | Compatibility with typical automated build/test and hosted staging workflows |

**Weighted score formula:** `Σ (criterion weight × candidate score)`. Weights are fractions (for example, 25% = 0.25), and totals are reported on a 5-point scale. No rounding is applied before summing.

## 4. Weighted decision matrix

| Criterion | Weight | A: Django 5.2 + PostgreSQL | B: FastAPI + PostgreSQL | C: Node.js/Express + PostgreSQL |
| --- | ---: | ---: | ---: | ---: |
| Transaction correctness and data integrity | 25% | 5 | 4 | 4 |
| Development speed and complexity | 20% | 4 | 3 | 3 |
| Security and role management | 15% | 4 | 3 | 3 |
| Maintainability and testing | 15% | 4 | 4 | 3 |
| Solo-developer familiarity and learning curve | 10% | 3 | 3 | 5 |
| Forecasting and data processing integration | 10% | 4 | 5 | 4 |
| Staging deployment and CI compatibility | 5% | 3 | 3 | 3 |
| **Weighted total** | **100%** | **4.10 / 5** | **3.60 / 5** | **3.55 / 5** |

Calculation check:

- **A:** `0.25×5 + 0.20×4 + 0.15×4 + 0.15×4 + 0.10×3 + 0.10×4 + 0.05×3 = 4.10`
- **B:** `0.25×4 + 0.20×3 + 0.15×3 + 0.15×4 + 0.10×3 + 0.10×5 + 0.05×3 = 3.60`
- **C:** `0.25×4 + 0.20×3 + 0.15×3 + 0.15×3 + 0.10×5 + 0.10×4 + 0.05×3 = 3.55`

The familiarity scores use the developer background confirmed by the project owner: Django **3/5** (working Python experience and a completed AI-assisted PoC, offset by being relatively new to Django), FastAPI **3/5** (working Python experience, with no FastAPI project experience reported), and Express **5/5** (stronger practical experience with JavaScript, Node.js/Express, APIs and PostgreSQL). These are informed self-reported fit scores, not independently assessed proficiency. Each point in this 10%-weighted criterion moves a total by 0.10.

## 5. Score rationale and evidence

### A. Django 5.2 LTS + PostgreSQL

| Criterion | Score | Evidence or reasoned basis |
| --- | ---: | --- |
| Transaction correctness and data integrity | 5 | **Demonstrated, narrow scope:** `change_stock()` wraps updates in `transaction.atomic()`, obtains `select_for_update()`, validates balances and the current database integer range; the importer uses an outer atomic transaction. The PoC reports rollback tests and a two-connection stock-out test. Django documents transaction management and row locking. This is the strongest evidence in this comparison, but does not cover a movement ledger, all future write paths, or production concurrency/load. |
| Development speed and complexity | 4 | **Reasoned assumption:** Django supplies an integrated ORM, migrations, authentication, permissions and admin conventions, reducing assembly for a data-centric application with roles and CRUD. The PoC confirms migrations and basic model/service implementation, but no UI/API workflows or role implementation; the score is not a claim that full Tory delivery was demonstrated. |
| Security and role management | 4 | **Documentation-backed, untested in PoC:** Django includes authentication and permission facilities and documents security practices. These provide a coherent starting point for Manager/Staff policies. Correct authorization design, least privilege, secure configuration and endpoint-level enforcement remain implementation work. |
| Maintainability and testing | 4 | **Partly demonstrated:** the current PoC has a small separated model, service, importer and automated test suite, plus migrations. Django's documented test framework and migration machinery support maintainable change. Full application module boundaries and solo-maintainer experience are untested. |
| Solo-developer familiarity and learning curve | 3 | **Confirmed background, judgment-based score:** the developer has working Python experience and has completed a Django/PostgreSQL PoC with AI assistance, but is relatively new to Django. This provides a starting point while leaving a framework learning curve. The PoC demonstrates that a narrow experiment was completed, not independent mastery or full-product delivery speed. |
| Forecasting and data processing integration | 4 | **Reasoned/documentation-backed:** Python has a mature data-processing ecosystem and supports straightforward, inspectable calculation code for a 7-day moving average. The exact forecasting feature and its data quality, explainability and evaluation have not been built or tested in this PoC. |
| Staging deployment and CI compatibility | 3 | **Reasoned assumption:** Django can be deployed in common Python hosting/container workflows and tested in CI, but Tory has no hosted staging, CI, or CD evidence. Hosting provider, pipeline and database service are not selected. |

The project pins Django **5.2.18** in `requirements.txt`; the official release notes identify 5.2 as an LTS series. The precise patch must be checked against supported security maintenance when the implementation baseline is frozen. [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/), [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update), [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/), [Django testing](https://docs.djangoproject.com/en/5.2/topics/testing/).

### B. FastAPI + PostgreSQL

| Criterion | Score | Evidence or reasoned basis |
| --- | ---: | --- |
| Transaction correctness and data integrity | 4 | **Documentation-backed capability, untested here:** PostgreSQL can provide the same transaction and constraint guarantees, while FastAPI allows SQLAlchemy/SQLModel or other database libraries. The application must choose and correctly configure ORM, transaction boundaries, locks and migrations; no FastAPI implementation was reviewed or run. |
| Development speed and complexity | 3 | **Reasoned assumption:** FastAPI offers typed request validation, dependency injection and generated API docs, which suit an API. For this full inventory system the solo developer must also select and integrate ORM/migrations, authentication/authorization, admin or UI, and supporting conventions. It is flexible, but creates more component decisions and maintenance ownership than Django's integrated stack. |
| Security and role management | 3 | **Documentation-backed capability, untested here:** FastAPI's security utilities and dependency injection can enforce authentication and role checks. The framework does not define Tory's role policy or provide a full built-in user/permission administration system, so policy and identity integration must be assembled and tested. |
| Maintainability and testing | 4 | **Documentation-backed capability, untested here:** typed APIs, dependencies and standard Python test tooling can support modular code and tests. Persistence conventions and migration discipline depend on selected packages and project architecture. |
| Solo-developer familiarity and learning curve | 3 | **Confirmed background, judgment-based score:** working Python experience transfers to FastAPI, but no FastAPI-specific experience was reported. |
| Forecasting and data processing integration | 5 | **Reasoned/documentation-backed:** Python directly supports explainable forecasting/data-processing code. FastAPI and Django share this advantage; the 5 indicates a good fit, not an advantage over Django or a tested forecast. |
| Staging deployment and CI compatibility | 3 | **Reasoned assumption:** ASGI applications can be built and hosted with common Python/container CI workflows. No target host, pipeline or Tory deployment has been evaluated. |

FastAPI's official SQL documentation explicitly leaves database library choice to the application and describes SQLModel/SQLAlchemy as one option; its dependency system supports security and role requirements. These capabilities are not transaction-safety proof. [FastAPI SQL databases](https://fastapi.tiangolo.com/tutorial/sql-databases/), [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/), [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/).

### C. Node.js/Express + PostgreSQL

| Criterion | Score | Evidence or reasoned basis |
| --- | ---: | --- |
| Transaction correctness and data integrity | 4 | **Reasoned/documentation-backed:** PostgreSQL provides the same underlying integrity mechanisms, and Node PostgreSQL clients/ORMs can use transactions. Correct client connection pinning, lock handling and rollback must be implemented explicitly. No candidate code or concurrency test exists in the PoC. |
| Development speed and complexity | 3 | **Reasoned assumption informed by confirmed background:** the developer's stronger Node/Express and API experience should reduce basic implementation and debugging friction. Express is still a small routing/middleware framework, so the solo developer must choose, integrate, secure and maintain database access/migrations, validation, authentication/roles and project conventions. The familiarity benefit is partly offset by this assembly burden. |
| Security and role management | 3 | **Reasoned/documentation-backed:** Express documents security best practices and can enforce role checks through middleware, but the minimal framework does not supply Tory's authentication, role/permission system or admin workflow. This is adequate with deliberate package selection and route coverage, while requiring more assembly than Django. This score reflects integration burden, not an inherent inability to secure Express. |
| Maintainability and testing | 3 | **Reasoned assumption:** Node tooling can support tests and structured applications, but Express's middleware flexibility leaves more architectural conventions, error handling and package choices to the project. No Tory implementation was evaluated. |
| Solo-developer familiarity and learning curve | 5 | **Confirmed background, judgment-based score:** JavaScript, Node.js/Express, APIs and PostgreSQL are the developer's strongest practical areas, making this the most familiar option. |
| Forecasting and data processing integration | 4 | **Reasoned assumption:** The specified 7-day moving average and reorder arithmetic are simple, transparent calculations that fit JavaScript well. Python may offer a more direct path if forecasting later expands into a broader data-processing workload; this PoC does not test either implementation. |
| Staging deployment and CI compatibility | 3 | **Reasoned assumption:** Node applications have common hosted deployment and CI workflows. The target host and Tory pipeline are undecided and no deployment has been tested. |

Express describes itself as a minimal routing/middleware framework, which supports the integration-burden assumptions. Its official security guidance offers operational recommendations but not an application-specific RBAC implementation. The official Express site currently documents the 5.x guide; a specific Express or Node.js version was not pinned or verified for this evaluation. [Express middleware](https://expressjs.com/en/guide/using-middleware/), [Express security best practices](https://expressjs.com/en/advanced/best-practice-security/), [Express 5 error handling](https://expressjs.com/en/5x/guide/error-handling/).

## 6. Solo-developer delivery considerations and selection rationale

The confirmed background favors Express for immediate fluency: the developer has stronger practical experience with Node.js/Express, APIs and PostgreSQL. The adjusted weighted matrix reflects that advantage (Express 3.55 versus Django 4.10 and FastAPI 3.60). The 0.55 Django/Express gap is therefore not evidence that Express is unfamiliar or intrinsically slower for this developer. It reflects the other weighted criteria, especially Django's integrated application functions and the direct, though limited, inventory-integrity evidence in the PoC.

Django has a real learning curve because the developer is relatively new to it. Its ORM, migrations, authentication and permissions, admin, forms, and security conventions can reduce solo assembly and integration work for inventory CRUD and Manager/Staff workflows. Those built-in capabilities still require learning and correct application; the PoC validates only a narrow model/service/import path, not the roles, UI/API, forecast or deployment. FastAPI fits the developer's Python experience but leaves more persistence, identity and admin choices to own. Express benefits from the strongest existing skills, while requiring deliberate selection and ongoing maintenance of supporting packages and conventions.

Codex is intended as a guided development aid, not a substitute for engineering judgment. Generated code may be incorrect, insecure, incomplete, or inconsistent with transaction boundaries. The developer plans to review and test it independently. This raises the importance of focused tests for authorization, atomic CSV rollback, concurrent stock changes, forecast calculations, migrations and deployment configuration. AI assistance may speed drafting and explain unfamiliar Django concepts, but it does not remove the learning curve, review burden, test ownership or single-person maintenance risk. The score matrix does not assume AI makes any framework's code correct or eliminates framework-specific learning.

**The project owner approved Django 5.2 LTS + PostgreSQL on 29 October 2026; the decision is recorded in ADR-001.** Its 4.10 weighted score, integrated functions and the only observed PoC evidence for the highest-weight correctness criterion support the decision. The score is decision support, not a measured productivity result. Express (3.55) and FastAPI (3.60) remain considered alternatives; changing the selected stack requires formal change control.

PostgreSQL remains confirmed across all options. Regardless of framework, design and test transaction boundaries, an auditable stock movement record, least-privilege database access and safe role enforcement.

## 7. Waterfall follow-up gates

Before the Planning baseline transitions to Requirements/Design:

1. Preserve the owner-approved Django + PostgreSQL selection in downstream requirements and design baselines; any proposed change follows ADR-001 change control. Familiarity scores reflect the supplied solo-developer background.
2. Reconcile the owner-reported 16/16 test claim with the available records. Checked-in reports show 14/14, migration 0002 exists, and the present test file has 15 test methods. No run was performed for this review because the configured PostgreSQL target could not be verified safely: no connection credentials or PostgreSQL client utilities were available. Preserve the original output (including command, test discovery count, summary, date, and source revision) or run the suite in a verified disposable PostgreSQL environment.
3. Plan a Django learning path around the system's ORM, migrations, authentication/permissions, and secure deployment settings; independently review generated code against official documentation.
4. Specify Manager/Staff permissions and test unauthorized as well as authorized actions at each application boundary.
5. Design an auditable stock movement record and define how imports, manual changes and concurrent requests maintain it atomically.
6. Define supplier-setting validation and the exact 7-day moving-average window, treatment of missing/zero demand, forecast explanation, reorder formula and user-facing assumptions.
7. Select staging host and PostgreSQL service, then demonstrate automated CI against PostgreSQL. Keep CD optional unless the project plan adopts it.
8. Pin the framework/runtime and database-driver versions for the implementation baseline; review current patch/security support at that time.

## 8. Sources and research date

Official framework documentation accessed **29 October 2026**. Framework capabilities are cited inline. Exact version statements are limited to the local Django pin and Django's documented 5.2 LTS series; no FastAPI, Express, Node.js, ORM, or CI provider version is asserted. Confirm versions and active support when the implementation environment is selected.

- [Django 5.2 release notes and LTS designation](https://docs.djangoproject.com/en/5.2/releases/5.2/)
- [Django database transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/) and [queryset row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)
- [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/) and [testing](https://docs.djangoproject.com/en/5.2/topics/testing/)
- [FastAPI SQL databases](https://fastapi.tiangolo.com/tutorial/sql-databases/), [dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) and [security](https://fastapi.tiangolo.com/tutorial/security/)
- [Express middleware](https://expressjs.com/en/guide/using-middleware/), [security best practices](https://expressjs.com/en/advanced/best-practice-security/) and [Express 5 error handling](https://expressjs.com/en/5x/guide/error-handling/)
