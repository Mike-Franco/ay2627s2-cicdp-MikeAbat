# Tory — Inventory Management & Demand Forecasting System

*Inventory made simple.*

Tory is a Singapore Polytechnic ST0529 CA1 project to manage inventory and provide explainable demand forecasts. One developer works with Codex assistance. The project owner adopted [lightweight Agile Kanban](docs/decisions/ADR-002-agile-kanban-delivery.md) for remaining delivery on **3 November 2026**. Earlier Planning and Requirements records retain their dated Waterfall context.

## Approved baseline

- **Backend:** Django 5.2 LTS
- **Database:** PostgreSQL
- **Budget:** SGD 0
- **Available project time:** 10–15 hours per week
- **Deadline:** 27 November 2026 at **17:00 Asia/Singapore**
- **Status:** P1 was approved with conditions on 29 October. BR-001–BR-045 and recorded owner decisions remain authoritative; the complete SRS, Requirements exit and Design entry have **not** been approved. No Tory application implementation is present in this repository.

The backend decision is recorded in [accepted ADR-001](docs/decisions/ADR-001-backend-and-database.md). GitHub Actions is approved for pull-request Django tests against PostgreSQL under NFR-010; the application workflow has not been implemented. Django templates are a **frontend candidate, not selected**. Application architecture, hosting provider and deployment topology remain undecided. Candidate services in the planning documents are research candidates only.

## Repository and Tory-PoC

The main GitHub repository is [`Mike-Franco/ay2627s2-cicdp-MikeAbat`](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat), also used as the course workspace `ay2627s2-cicdp-MikeAbat`. It contains the Tory project records and planning evidence. `Tory-PoC` remains a separate, isolated feasibility experiment. No PoC application source, database, virtual environment, or Git history is included here. PoC reports are retained as historical evidence and must not be read as proof that the Tory product is implemented or production-ready. Their scope and evidence limitations are documented in the reports and [source provenance note](docs/SOURCE_PROVENANCE.md).

## Documentation

- [Planning](docs/planning/): original approved charter/P1 evidence, feasibility and risks, and the [current incremental schedule with original baseline retained](docs/planning/PROJECT_SCHEDULE.md).
- [Requirements](docs/requirements/): owner-approved individual rules and decisions, living gap analysis, role permissions and traceability, plus the complete SRS awaiting approval. A pending gap is addressed before its dependent feature; unrelated gaps do not block all implementation.
- [Decisions](docs/decisions/): ADR-001 preserves the backend choice; ADR-002 records the prospective Agile Kanban methodology decision.
- [Technology evaluation](docs/TECHNOLOGY_EVALUATION.md): comparative assessment and remaining evidence caveats.
- [PoC evidence](docs/POC_RESULTS.md), [technical feasibility](docs/TECHNICAL_FEASIBILITY.md), and [PoC handover](docs/POC_HANDOVER.md): historical experiment reports and limitations.
- [Documentation provenance](docs/SOURCE_PROVENANCE.md): source workspace, transfer scope, and evidence boundary.

## Assignment context

The repository retains its course-workspace name, `ay2627s2-cicdp-MikeAbat`; Tory is the project documented within it. Course: Singapore Polytechnic ST0529 CA1.

## Development workflow

Use a minimal Kanban board: **To do → In progress → Review/Test → Done**, with a **work-in-progress limit of one item in In progress**. Prioritize stock correctness, then dependent security and delivery risks. Each Jira issue should cite relevant BR/FR/NFR and G-gap references, state acceptance criteria, and link its implementation pull request and automated test evidence when available. **No Jira issues or board are claimed to have been created.** Review changes in small pull requests and update living requirements/traceability evidence without rewriting historical approvals. See [ADR-002](docs/decisions/ADR-002-agile-kanban-delivery.md) and the [schedule](docs/planning/PROJECT_SCHEDULE.md).

## Documentation CI

The [documentation workflow](.github/workflows/docs-ci.yml) runs on pushes to `main` and `develop` and pull requests targeting either branch. It uses a read-only GitHub token, a pinned checkout action, a five-minute job timeout and no paid tools. The [checker](scripts/check_docs.py) uses only Python's standard library. Its small ruleset requires UTF-8 Markdown, one level-one heading at the start of each document, a final newline, no tab characters, no merge-conflict markers in checked text files, and the listed key project documents. It permits existing two-space Markdown line breaks and does not reformat approved Planning records. It is not a secrets scan or proof that the documents contain no secrets.

Run locally with `python scripts/check_docs.py` (or `python3 scripts/check_docs.py`). After a push or pull request to `main` or `develop`, check **Actions → Documentation CI → Check documentation** for the intended commit. The approved GitHub Actions Django/PostgreSQL pull-request test gate is separate and remains to be implemented when Tory application code exists.
