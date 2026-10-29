# ADR-001: Backend Framework and Database

**Date:** 29 October 2026  
**Status:** Accepted  
**Decision owner:** Tory project owner  
**Project:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*  
**Course:** Singapore Polytechnic ST0529 CA1

## 1. Decision context and scope

Tory is a solo-developed inventory management and demand forecasting system following a strict Waterfall lifecycle: Planning, Requirements, Design, Implementation, Testing, and Deployment. The project owner has formally approved the backend stack recorded below as the final Planning baseline on 29 October 2026. This ADR records that decision; the decision is not pending further approval.

The confirmed product needs include manual stock-in, stock-out and adjustments; atomic CSV import of stock transactions only, rejecting the entire batch if any row is invalid; Manager and Staff roles; per-product supplier lead time, safety stock and reorder settings; explainable seven-day moving-average demand forecasts and reorder recommendations; and hosted staging with automated CI (CD optional).

The existing Django/PostgreSQL proof of concept is an isolated feasibility experiment. It is not the Tory application and is not approved for production reuse as application code. This ADR selects only the backend framework and relational database. It does not baseline requirements that have not passed the Requirements stage or make the additional decisions listed in section 8.

## 2. Accepted decision

**Use Django 5.2 LTS with PostgreSQL as Tory's backend technology stack.**

The PoC package pin is Django 5.2.18 and the recorded local database was PostgreSQL 18.3. These are observed PoC environment versions; this ADR's framework decision is the Django 5.2 LTS line and PostgreSQL. The exact supported patch versions and deployment database version must be confirmed and pinned for the implementation environment at the appropriate later stage.

This decision is final for the Planning baseline. Any proposed replacement or material change requires the formal change-control procedure in section 10 and an approved change request.

## 3. Alternatives considered

| Alternative | Summary |
| --- | --- |
| FastAPI + PostgreSQL | Python API framework with database/ORM, migration, identity and admin choices left to application integration. Considered credible for an API-first design and Python-based forecasting work. |
| Node.js/Express + PostgreSQL | Familiar JavaScript/Node stack for the solo developer, with a minimal routing/middleware framework and supporting persistence, identity and application conventions to select and maintain. |

PostgreSQL was held constant across all three candidates because it is a confirmed project requirement. The alternatives were evaluated as framework stacks, not as proof that their underlying database capabilities differ.

## 4. Weighted evaluation evidence

The Planning evaluation used a 1–5 scale and these weights: transaction correctness/data integrity 25%; development speed/complexity 20%; security/roles 15%; maintainability/testing 15%; solo-developer familiarity/learning curve 10%; forecasting/data processing 10%; and staging/CI compatibility 5%. Weighted total is `Σ(weight × score)`, with percentage weights represented as fractions.

| Criterion | Weight | Django 5.2 + PostgreSQL | FastAPI + PostgreSQL | Node.js/Express + PostgreSQL |
| --- | ---: | ---: | ---: | ---: |
| Transaction correctness and data integrity | 25% | 5 | 4 | 4 |
| Development speed and complexity | 20% | 4 | 3 | 3 |
| Security and role management | 15% | 4 | 3 | 3 |
| Maintainability and testing | 15% | 4 | 4 | 3 |
| Solo-developer familiarity and learning curve | 10% | 3 | 3 | 5 |
| Forecasting and data processing integration | 10% | 4 | 5 | 4 |
| Staging deployment and CI compatibility | 5% | 3 | 3 | 3 |
| **Weighted total** | **100%** | **4.10 / 5** | **3.60 / 5** | **3.55 / 5** |

Calculation verification:

- **Django:** `0.25×5 + 0.20×4 + 0.15×4 + 0.15×4 + 0.10×3 + 0.10×4 + 0.05×3 = 4.10`
- **FastAPI:** `0.25×4 + 0.20×3 + 0.15×3 + 0.15×4 + 0.10×3 + 0.10×5 + 0.05×3 = 3.60`
- **Express:** `0.25×4 + 0.20×3 + 0.15×3 + 0.15×3 + 0.10×5 + 0.10×4 + 0.05×3 = 3.55`

The solo-developer familiarity scores reflect the owner's supplied background: stronger practical experience with JavaScript, Node.js/Express, APIs and PostgreSQL; working experience with Python; and relative newness to Django after completing an AI-assisted Django/PostgreSQL PoC. The scores (Django 3, FastAPI 3, Express 5) are informed judgments, not independently assessed proficiency. Codex is intended as guided assistance, with generated code independently reviewed and tested.

The matrix is comparative decision evidence, not a benchmark. Django's higher total is not caused by the familiarity criterion: Express receives the highest familiarity score. Django leads on integrated functionality and has the only observed candidate-specific PoC evidence for the highest-weight integrity criterion. Many framework capability scores are documentation-backed or reasoned assumptions. FastAPI and Express were not implemented or tested in this PoC.

## 5. Relevant PoC findings and evidence limits

The PoC demonstrates narrow technical feasibility for Django 5.2.18 with PostgreSQL. Reviewed source includes a Product model with unique SKU and nonnegative integer quantity; a stock service using `transaction.atomic()` and `select_for_update()`; and an outer-transaction CSV importer for stock transactions. The test source covers database constraints, stock changes and validation, CSV success/rollback cases, and a two-connection competing stock-out scenario.

The checked-in `docs/POC_RESULTS.md` and `docs/POC_HANDOVER.md` report 14 discovered and passing tests. The results report also records a shuffled 14-test pass and five additional successful repetitions of the concurrency test. These are historical reported outcomes, not tests run while preparing this ADR.

The project owner has reported a later 16/16 test run. No matching output or report is available in the reviewed workspace, so that result remains **reported but independently unverified**. The current `inventory/tests.py` contains 15 test methods (14 in `InventoryTests` and one concurrency test); method count does not prove what a particular run discovered. The 16-test result may correspond to another source revision, but there is no artifact here to establish that. The discrepancy must remain open until the original run output/source revision is supplied or a fresh run is captured in a verified disposable PostgreSQL environment.

The PoC does **not** demonstrate Manager/Staff authentication or authorization, forecast/reorder logic, supplier settings, a movement ledger, HTTP/UI workflows, hosted staging, CI/CD, production security, or workload performance. The PoC is evidence of feasibility for the narrow tested paths, not evidence that the final system is complete, production-ready, or proven best by comparative implementation.

## 6. Rationale for a solo-developed inventory system

Django is selected because its integrated ORM, schema migrations, authentication and permissions, admin, and security conventions align with Tory's data-centric inventory workflows. For a solo developer, a coherent built-in set can reduce the number of components to choose, connect, document and maintain, especially when implementing Manager/Staff roles and inventory CRUD. Django also pairs naturally with Python code for an explainable moving average.

The developer is relatively new to Django, so there is a real learning and review cost. The completed PoC shows that a narrow Django/PostgreSQL experiment was completed with AI assistance; it does not prove independent Django mastery or full-product delivery speed. Codex can help explain patterns and draft implementation, but generated code may be wrong, insecure, or inconsistent with transaction boundaries. The developer's independent review and testing remain necessary. This risk is addressed through staged learning, official documentation, focused tests, and Waterfall reviews; AI assistance is not treated as a substitute for those controls.

Express is most familiar to the developer and remains technically viable, but its minimal core would leave more supporting framework, authentication/authorization, persistence and project conventions to assemble. The project judged Django's integrated functions and the limited direct integrity evidence more valuable for this system than Express's familiarity advantage. FastAPI remains credible but similarly requires decisions and ownership around persistence, migrations, identity and admin capabilities.

## 7. Consequences

### Positive consequences

- The Planning baseline has a clear backend and database direction for Requirements and Design.
- Django provides established ORM, migrations, authentication/permissions, admin and security features that can reduce solo integration work when correctly learned and applied.
- PostgreSQL is consistent with the confirmed requirement and the database used in the PoC.
- The PoC gives a starting reference for safe stock updates and atomic transaction imports, while keeping production implementation decisions open to later stages.
- Python supports readable and explainable implementation of the specified basic moving-average calculation.

### Negative consequences and trade-offs

- The developer must learn Django conventions and avoid relying on unreviewed AI-generated code.
- Built-in authentication and permissions still require careful role design, route/view enforcement, configuration and security testing.
- Existing Express expertise is not the selected backend path; that familiarity advantage is not used directly for server implementation.
- Django's integrated capabilities do not remove the need to define application architecture, audit history, error handling, deployment security, testing strategy or operations.
- The PoC is disposable feasibility code and must not be mistaken for a production-ready foundation.
- Solo ownership concentrates implementation, review, testing and maintenance responsibilities in one person.

## 8. Decisions explicitly not made

This ADR does **not** select or baseline:

- frontend language, framework, rendering model, or client architecture;
- hosting provider, cloud platform, or production/staging topology;
- Tory's application architecture, module boundaries, API contract, or UI design;
- deployment pipeline details, CI provider, CD process, or release strategy;
- exact production database/server patch, hosting configuration, or infrastructure sizing;
- requirements not yet formally baselined at the Requirements stage, including detailed role permissions, audit/history behavior, forecast edge cases, reorder formula, nonfunctional targets and operational controls.

The confirmed Planning baseline already states PostgreSQL, atomic transaction CSV import, Manager/Staff roles, per-product supplier/reorder settings, explainable seven-day moving average, and hosted staging with automated CI (CD optional). Formal acceptance and detailed specification of those needs remain subject to the Requirements stage and its Waterfall approval.

## 9. Risks, mitigations, and later-stage implications

| Risk / implication | Mitigation or later-stage action |
| --- | --- |
| Django learning curve and solo-maintainer knowledge concentration | Build familiarity incrementally; use official Django documentation; independently inspect AI-generated changes; document decisions and important data flows. |
| Incorrect inventory updates or CSV partial application | At Design, define a single authoritative stock mutation path and ledger/audit model; at Implementation and Testing, verify database constraints, atomic rollback, authorization and concurrent updates using PostgreSQL. |
| Roles implemented incompletely or insecurely | Define Manager/Staff permission matrix in Requirements; design authorization boundaries in Design; test both allowed and denied operations in Testing. |
| AI-generated defects, unsafe patterns or misunderstood framework behavior | Treat generated code as a proposal; require developer review, focused tests, security checks and stage reviews. Keep evidence of test results and source revision. |
| PoC results overgeneralized to full Tory | Keep PoC scope and limitations visible; do not claim that RBAC, forecasting, staging, CI/CD or production behavior was validated. |
| Test-count evidence remains inconsistent | Retain the 14/14 checked-in historical reports and unresolved owner-reported 16/16 claim distinctly. Obtain original output and source revision, or capture a fresh PostgreSQL run in a verified disposable environment before citing 16/16 as verified. |
| Version drift or unsupported package patch | Freeze supported Django 5.2 patch, Python, PostgreSQL and driver versions in Design/Implementation; verify support and security updates at that time. |
| Staging and CI remain unproven | Select hosting and pipeline details in Design; implement and verify automated CI against PostgreSQL before relying on the staging demonstration. CD remains optional unless formally adopted. |

Stage implications: Planning records this accepted stack; Requirements specifies behavior and quality constraints without silently expanding this decision; Design defines application/data/security/deployment architecture; Implementation builds only approved designs; Testing verifies requirements and integrity against PostgreSQL; Deployment addresses secure configuration and the separately selected hosting/release plan.

## 10. Review triggers and change control

This decision remains in force unless changed through a formal change request. A review may be triggered by evidence that Django 5.2 LTS cannot meet a baselined requirement, a material support/security or compatibility issue, a change in project constraints that makes the stack infeasible, or verified comparative evidence that materially changes the decision basis.

A proposed change must document the reason, affected requirements and artifacts, security/data-integrity implications, alternatives, revised weighted evaluation where relevant, migration and schedule impact, and test/deployment consequences. The project owner must approve the change before implementation. If approved, record the new decision in a superseding ADR, mark this ADR superseded with a link, and update affected Planning/Requirements/Design records under the Waterfall change-control process. Until approval, Django 5.2 LTS + PostgreSQL remains the final Planning baseline.

## 11. References

- [Technology Evaluation & Selection](../TECHNOLOGY_EVALUATION.md) — weighted matrix, score rationale, solo-developer context, and remaining evidence caveats.
- [PoC Results](../POC_RESULTS.md) — recorded test outcomes and limitations.
- [Technical Feasibility](../TECHNICAL_FEASIBILITY.md) — PoC scope, methodology and feasibility findings.
- [PoC Handover](../POC_HANDOVER.md) — implementation boundary, recorded 14-test run, limitations and unresolved features.
- [Tory repository README](../../README.md) — current product and repository status.
- PoC-only source reviewed as evidence: `inventory/models.py`, `inventory/services.py`, `inventory/csv_import.py`, `inventory/tests.py`, and `inventory/migrations/`. These files remain in the separate PoC workspace and were not transferred; see [source provenance](../SOURCE_PROVENANCE.md).
- [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) — official LTS series documentation.

## 12. Conflicts and records to reconcile

Earlier versions of the README, PoC reports, feasibility report and technology evaluation contained pre-decision wording about the backend selection. A subsequent documentation review updated those statements to point to this accepted ADR while preserving the distinction between a selected stack and an isolated PoC that is not production application code.

The test evidence also differs across records and current source: checked-in reports state 14 tests passed, current source contains 15 test methods, and the owner reports a later 16/16 run without a matching artifact in this workspace. This ADR preserves that uncertainty rather than treating the reported result as verified. The 16-test claim should be reconciled when its output and corresponding source revision are available.
