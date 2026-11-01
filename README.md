# Tory — Inventory Management & Demand Forecasting System

*Inventory made simple.*

Tory is a Singapore Polytechnic ST0529 CA1 project to manage inventory and provide explainable demand forecasts. This project is developed by one person with Codex assistance and follows six Waterfall stages: Planning, Requirements, Design, Implementation, Testing, and Deployment.

## Approved baseline

- **Backend:** Django 5.2 LTS
- **Database:** PostgreSQL
- **Budget:** SGD 0
- **Available project time:** 10–15 hours per week
- **Deadline:** 27 November 2026
- **Status:** Planning exit (P1) was approved with conditions on 29 October 2026. Entry to Requirements is authorised; Requirements exit and approval of the detailed requirements are still pending.

The backend decision is recorded in [accepted ADR-001](docs/decisions/ADR-001-backend-and-database.md). Frontend, application architecture, hosting, deployment topology, and detailed CI/CD choices have not been approved. Candidate services in the planning documents are research candidates only.

## Repository and Tory-PoC

The main GitHub repository is [`Mike-Franco/ay2627s2-cicdp-MikeAbat`](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat), also used as the course workspace `ay2627s2-cicdp-MikeAbat`. It contains the Tory project records and planning evidence. `Tory-PoC` remains a separate, isolated feasibility experiment. No PoC application source, database, virtual environment, or Git history is included here. PoC reports are retained as historical evidence and must not be read as proof that the Tory product is implemented or production-ready. Their scope and evidence limitations are documented in the reports and [source provenance note](docs/SOURCE_PROVENANCE.md).

## Documentation

- [Planning](docs/planning/): approved charter, schedule, risk register, feasibility assessment, review, owner decisions, and P1 gate record.
- [Requirements](docs/requirements/): draft business rules, role permissions, traceability, review, and SRS materials. Requirements exit has not been approved.
- [Decisions](docs/decisions/): accepted architecture and technology decision records; ADR-001 accepts Django 5.2 LTS and PostgreSQL as the Planning backend baseline.
- [Technology evaluation](docs/TECHNOLOGY_EVALUATION.md): comparative assessment and remaining evidence caveats.
- [PoC evidence](docs/POC_RESULTS.md), [technical feasibility](docs/TECHNICAL_FEASIBILITY.md), and [PoC handover](docs/POC_HANDOVER.md): historical experiment reports and limitations.
- [Documentation provenance](docs/SOURCE_PROVENANCE.md): source workspace, transfer scope, and evidence boundary.

## Assignment context

The repository retains its course-workspace name, `ay2627s2-cicdp-MikeAbat`; Tory is the project documented within it. Course: Singapore Polytechnic ST0529 CA1.

## Documentation CI

The [documentation workflow](.github/workflows/docs-ci.yml) runs on pushes and pull requests targeting `main`. It uses a read-only GitHub token, a pinned checkout action, a five-minute job timeout and no paid tools. The [checker](scripts/check_docs.py) uses only Python's standard library. Its small ruleset requires UTF-8 Markdown, one level-one heading at the start of each document, a final newline, no tab characters, no merge-conflict markers in checked text files, and the listed key project documents. It permits existing two-space Markdown line breaks and does not reformat approved Planning records. It is not a secrets scan or proof that the documents contain no secrets.

Run locally with `python scripts/check_docs.py` (or `python3 scripts/check_docs.py`). After a push or pull request to `main`, open the repository's **Actions** tab, select **Documentation CI**, and check that **Check documentation** passes for the intended commit. Django/PostgreSQL application checks are planned for a later stage when Tory application code exists; this documentation workflow does not approve a CI provider for the final application pipeline.
