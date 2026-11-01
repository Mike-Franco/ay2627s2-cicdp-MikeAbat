# Tory Project Charter

**Course:** Singapore Polytechnic ST0529 CA1  
**Product:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*  
**Lifecycle:** Waterfall: Planning, Requirements, Design, Implementation, Testing, Deployment  
**Planning baseline:** 29 October 2026  
**Status:** Approved by project owner on 29 October 2026.

## Business problem

The project is intended to provide a simple way to record inventory movements and use recent demand to support replenishment decisions. The problem statement is a project framing based on the confirmed system requirements; customer research, current business-process evidence, and measured losses or service issues have not been provided and must not be inferred.

## Objectives

- Record manual stock-in, stock-out and stock adjustments.
- Import stock transactions from CSV as an all-or-nothing batch; product catalog import is excluded.
- Maintain product supplier lead time, safety stock and reorder settings.
- Apply Manager and Staff permissions to system operations.
- Provide an explainable seven-day moving-average demand forecast and reorder recommendations.
- Provide a hosted staging demonstration and automated CI. Automated CD is optional.

The above are the fixed Planning baseline. Detailed behavior and acceptance conditions are for the Requirements stage and formal approval.

## Proposed stakeholders

These are proposed project roles, not evidence of interviews or confirmed appointments.

| Stakeholder | Proposed interest / responsibility | Status |
| --- | --- | --- |
| Project owner / sponsor and solo student developer | Approves scope, stage gates, priorities and formal changes; performs analysis, design, implementation, testing, documentation and demonstration | Confirmed as one person; identity/signature format TBD |
| Manager user | Manages permitted inventory and replenishment activities | Role confirmed; user representative and exact permissions TBD |
| Staff user | Performs permitted operational activities | Role confirmed; user representative and exact permissions TBD |
| Course assessor / supervisor | Reviews CA1 deliverables against course expectations | Proposed; individual and review process TBD |

## Project justification

The owner has approved Django 5.2 LTS + PostgreSQL for the backend. The framework evaluation scored Django 4.10/5, FastAPI 3.60/5 and Express 3.55/5. Django offers integrated ORM, migrations, authentication/permissions and admin capabilities that suit an inventory system developed by one person. The isolated PoC supplies narrow PostgreSQL feasibility evidence for stock updates and atomic transaction CSV import. It does not demonstrate the full product, and selection is recorded in [ADR-001](../decisions/ADR-001-backend-and-database.md).

No validated market research, customer interviews, quantified benefits or cost-benefit figures are available. Business value is therefore a project rationale, not a validated market case.

## Measurable success criteria (proposed for Requirements approval)

The following criteria make the fixed baseline verifiable. Exact acceptance wording, test data and edge-case rules require approval in the formal SRS.

1. **Manual movements:** each authorized stock-in, stock-out and adjustment request produces the expected quantity change; invalid requests are rejected without an unintended quantity change.
2. **Atomic CSV:** a fully valid stock-transaction file applies all rows; any invalid row causes the batch to apply zero row changes. Product catalog rows are not accepted by this workflow.
3. **PostgreSQL:** the implemented application and formal automated tests use PostgreSQL; SQLite-only evidence is not accepted for database-concurrency claims.
4. **Permissions:** tests demonstrate allowed and denied actions for both Manager and Staff against the approved permission matrix.
5. **Supplier/reorder settings:** each product can hold the approved supplier lead time, safety stock and reorder settings, with agreed validation rules.
6. **Forecast:** for agreed eligible demand history, the system shows a seven-day moving-average value and enough inputs/steps for a user to understand the result; missing-data, rounding and insufficient-history rules are approved in Requirements.
7. **Staging and CI:** a hosted staging demonstration is reachable for the approved demonstration workflow, and automated CI runs the approved checks against PostgreSQL with a recorded passing result.
8. **Formal Testing exit:** all approved acceptance tests have recorded outcomes; unresolved critical/high defects meet an owner-approved exit rule. Numeric quality thresholds are TBD pending Requirements approval.

No throughput, response-time, uptime, accuracy, adoption or financial target is asserted at Planning; these are TBD if required.

## High-level scope

### Included

- Manual inventory stock-in, stock-out and adjustment operations.
- Atomic CSV import of stock transactions only.
- PostgreSQL persistence.
- Manager and Staff permissions.
- Per-product supplier lead time, safety stock and reorder settings.
- Explainable seven-day moving-average forecast and reorder recommendations.
- Hosted staging demonstration and automated CI; CD optional.

### Exclusions

- Product catalog import.
- Treating the isolated PoC as production application code.
- Any unapproved frontend, hosting provider, system architecture, or deployment pipeline choice.
- Forecasting methods beyond the confirmed seven-day moving average unless approved through change control.
- Unconfirmed integrations, multi-warehouse workflows, barcode scanning, purchasing automation, notifications, mobile applications, analytics beyond the stated forecast, and production operations. These are not included unless formally approved.

## Key deliverables

- Planning package: this charter, feasibility assessment, risk register, project schedule, technology evaluation and accepted ADR.
- Approved Requirements-stage SRS and acceptance criteria.
- Approved Design-stage architecture, data model, interface/security design and test strategy.
- Implemented Tory application and source documentation (Implementation stage).
- Formal test plan, test evidence, defect disposition and test-stage approval.
- Hosted staging demonstration, deployment notes and deployment-stage approval.

Detailed deliverable formats and assessor requirements: TBD.

## Assumptions

- The owner-approved backend is Django 5.2 LTS + PostgreSQL; exact patch/runtime/database deployment versions are chosen later.
- The product is developed by one student, with Codex used for guided assistance and generated code independently reviewed and tested.
- Available project time is 10–15 hours per week through the owner-confirmed deadline of 27 November 2026; actual hours may be reduced by coursework conflicts.
- Cash budget ceiling is SGD 0; only zero-cost services may be used.
- The existing PoC remains isolated feasibility material and is not production code.
- Manager and Staff are the required role labels; their permissions remain to be specified.
- Demand data will be available in a form sufficient for the agreed moving-average calculation; source, availability and quality are TBD.
- Hosted staging and automated CI are required; CD is optional.

## Dependencies and constraints

- Deadline: 27 November 2026; available project capacity: 10–15 hours/week. Interim dates, weekly distribution and coursework conflicts remain to be confirmed.
- PostgreSQL installation/access, test database permissions and a reproducible development environment.
- Staging provider/service, developer eligibility, account access, quota and network/security requirements: TBD; zero-cost provider viability is not yet verified.
- Automated CI provider, runner eligibility/quota, PostgreSQL service setup and secrets handling: TBD; zero-cost operation must be verified.
- Course interim submission/review dates and assessor-specific deliverable rules: TBD; the official project deadline is 27 November 2026.
- Waterfall stage approval and formal change control apply; later-stage implementation cannot silently alter approved requirements or the selected stack.
- Cash ceiling: SGD 0; free-tier eligibility and account/payment restrictions remain TBD.

## Approval record

The project owner approved this charter on **29 October 2026**, including its high-level scope, exclusions, deliverables and proposed success-criteria framing. The success criteria remain proposals for elaboration and formal acceptance in the Requirements-stage SRS. Stakeholder identities, cost/service feasibility, schedule estimates and other items marked TBD remain unresolved; charter approval does not constitute full Planning-stage sign-off or approval to transition stages. The accepted backend decision is recorded separately in [ADR-001](../decisions/ADR-001-backend-and-database.md).
