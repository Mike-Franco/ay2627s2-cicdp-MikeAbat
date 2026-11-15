# ADR-002: Agile Kanban Delivery for Remaining Tory Work

**Decision date:** 3 November 2026
**Status:** Accepted by project owner
**Scope:** Delivery method from this date forward; Singapore Polytechnic ST0529 CA1

## Context and decision

The project owner adopts **lightweight Agile Kanban for all remaining Tory work**, replacing the planned sequential Waterfall delivery approach prospectively. One developer has 10–15 hours per week, an SGD 0 cash ceiling and a deadline of **27 November 2026 at 17:00 Asia/Singapore**. Stock correctness is the highest priority. Short, reviewable increments make integration and feasibility problems visible earlier than waiting for a later stage window. This is an owner methodology decision, not evidence that unfinished requirements or services are approved.

The 29 October [Charter](../planning/PROJECT_CHARTER.md), [P1 gate](../planning/PLANNING_GATE_P1.md), [original schedule](../planning/PROJECT_SCHEDULE.md) and [ADR-001](ADR-001-backend-and-database.md) retain their historical Waterfall meaning and approval dates. This ADR does not backdate Agile selection or retroactively approve the full SRS, Requirements exit, Design entry, risk deferrals or any pending stage review. Historical PoC and traceability evidence also retain their recorded limits.

## Working method

Use one small Kanban board with **To do → In progress → Review/Test → Done** and a **work-in-progress limit of one item in In progress** for the solo developer. Pull the next item by stock-correctness risk, dependency and deadline. A blocked item returns to To do with its blocker and owner visible; do not treat time spent waiting as completion. Keep the SRS, gap register, traceability, risk and schedule records living and versioned; preserve earlier approvals as dated evidence. Record changed requirements or scope through explicit owner decisions before dependent work relies on them.

Each Jira issue should include relevant **BR/FR/NFR and G-gap references**, a narrow outcome and acceptance criteria, the implementation pull request when one exists, and automated test evidence with revision/result. Link security, concurrency, CSV and performance checks where applicable. The TORY Jira project has a board and backlog. Its board tracks **To Do → In Progress → Review/Test → Done**, but the current simple-board setup does not provide native sprint assignment or reporting. The [Agile iteration log](../planning/AGILE_ITERATION_LOG.md) records cycle goals and actual reviews. A pull request receives review and relevant PostgreSQL-backed checks before its item is Done. The repository has separate Django/PostgreSQL application and Documentation GitHub Actions workflows: the application workflow runs Django checks, migrations and tests against PostgreSQL, while Documentation CI checks the repository's documentation rules.

Review each unresolved gap **before its dependent feature**: for example, decide stock movement/concurrency outcomes before relying on them in an issue, and resolve email/hosting feasibility before claiming an invitation or hosted demonstration complete. Unrelated gaps do not freeze every independent implementation increment. Approved BR-001–BR-045, stable FR/NFR IDs, permissions and owner decisions remain binding. A pending question cannot be silently filled by implementation; record an owner decision, a formally accepted bounded deferral or a change request as appropriate.

## Consequences and boundaries

- Plan and reforecast in small increments through the [current schedule](../planning/PROJECT_SCHEDULE.md), including assessment/report/demo work and contingency. Escalate forecast overruns early; no scope reduction or budget increase is implicit.
- Preserve Django 5.2 LTS and PostgreSQL. This methodology decision treated Django templates as a candidate and did not select a frontend; **Django Templates + Bootstrap was selected separately in [ADR-003](ADR-003-frontend-architecture.md), also dated 3 November 2026**. No hosting provider, application architecture, payment method, risk deferral or unfinished acceptance parameter is approved here.
- Keep traceability and evidence by requirement rather than treating a workflow column as approval. A feature is Done only when its applicable approved criteria and review/test evidence are met; unresolved dependencies remain visible.
- The original Waterfall stage and sign-off documents remain historical records. No prior pending SRS/stage review becomes approved because delivery method changed. Any course-specific submission or sign-off obligation still needs explicit verification and completion.

**Decision authority:** Project owner, supplied 3 November 2026. No signature, Jira ticket, implementation, test run or deployment is claimed by this record.

## Prospective cadence amendment — 12 November 2026

The owner adds sprint-style, timeboxed planning and review cycles from **12 November 2026** within the Kanban delivery method. This does not rewrite the 3 November adoption decision, the original Waterfall baseline, or any earlier approval. Completed work before this change remains Kanban delivery; PRs #34–#37 are pre-sprint evidence, not Sprint 1 output, even though PR #37 merged on 12 November. Its manual browser checklist remains pending.

The [iteration log](../planning/AGILE_ITERATION_LOG.md) records cycle goals, dates, actual reviews and retrospectives. Results stay pending until those events occur. The current TORY simple board has To Do, In Progress, Review/Test and Done columns but no native sprint assignment or reporting. Jira remains authoritative for issue states and PR/test links. Keep one-item In Progress WIP, the solo-developer 10–15 hours/week capacity, SGD 0 budget, approved scope and 27 November 2026 17:00 Asia/Singapore deadline. Staging feasibility and performance evidence remain unresolved; a timebox does not approve or waive them.
