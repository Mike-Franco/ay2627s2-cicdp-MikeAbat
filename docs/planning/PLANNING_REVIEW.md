# Tory Planning Deliverables — Independent Review

**Course:** Singapore Polytechnic ST0529 CA1  
**Product:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*  
**Review date:** 29 October 2026  
**Reviewer role:** Independent software engineering review  
**P1 status:** **Planning exit approved with conditions; Requirements entry authorized on 29 October 2026.**  
**Requirements status:** Entry is authorized for the target window; **Requirements exit remains pending owner approval**.

## 1. Review scope and basis

At the source PoC review, the PoC README, model/service/CSV importer/tests and migrations were examined alongside the PoC reports, technology evaluation, accepted ADR-001, and Planning records. The PoC source remains in its separate workspace. No tests were run as part of this documentation review. No application code was changed.

The owner-approved baseline is Django 5.2 LTS + PostgreSQL. The owner also confirmed a 27 November 2026 deadline, one solo developer, 10–15 hours/week, SGD 0 cash ceiling, and Charter approval dated 29 October 2026. These decisions are recorded in [OWNER_DECISIONS.md](OWNER_DECISIONS.md). The fixed functional baseline is manual stock-in/out/adjustments; atomic CSV import for stock transactions only; Manager and Staff permissions; per-product supplier lead times and safety stock/reorder settings; explainable seven-day moving-average forecasting; and hosted staging with automated CI (CD optional).

## 2. Deliverable checklist and status

Status reflects document quality and readiness for owner sign-off. **Pass** does not mean project implementation or formal Testing is complete. **Needs revision** means approval or an identified update is required. **Blocked** is not assigned; no document is blocked by an external dependency at this review.

| Deliverable | Status | Review result / reference |
|---|---|---|
| PoC README | **Pass at source review** | The separate Tory-PoC README described its isolated scope and pointed to ADR-001. It was not transferred into this repository; see [source provenance](../SOURCE_PROVENANCE.md). |
| PoC Results | **Pass** | Historical 14-test claims and narrow evidence are preserved; accepted stack selection is distinguished from PoC findings. See [POC_RESULTS.md](../POC_RESULTS.md), opening paragraph and “Limitations and conclusion.” |
| Technical Feasibility report | **Pass** | Narrow PoC feasibility and later-stage decisions remain separated; current conclusion points to ADR-001. See [TECHNICAL_FEASIBILITY.md](../TECHNICAL_FEASIBILITY.md), §§1, 6–7. |
| PoC Handover | **Pass** | Implementation boundary, untested features and test discrepancy are explicit; selected stack points to ADR-001. See [POC_HANDOVER.md](../POC_HANDOVER.md), §§1, 3–7. |
| Technology Evaluation | **Pass** | Scores and formulas are correct; decision status reflects owner approval. See [TECHNOLOGY_EVALUATION.md](../TECHNOLOGY_EVALUATION.md), §§2, 4, 6–7. |
| ADR-001 | **Pass** | Accepted 29 October 2026; stack, scope boundaries, caveats and change control are recorded. See [ADR-001](../decisions/ADR-001-backend-and-database.md), §§1–12. |
| Project Charter | **Pass** | Owner approval dated 29 October 2026 is recorded, including scope, exclusions, deliverables and success framing. Detailed acceptance remains for Requirements. See [PROJECT_CHARTER.md](PROJECT_CHARTER.md), “Approval record.” |
| Feasibility Assessment | **Pass** | Uses the confirmed zero-cash ceiling, deadline and capacity; estimates 44–54 remaining hours against 43–64 hours available. Eligibility/quota/provider checks remain open; conclusion is marginal feasibility. See [FEASIBILITY_ASSESSMENT.md](FEASIBILITY_ASSESSMENT.md), §§1–5. |
| Risk Register | **Pass** | Existing risks retained; schedule, single-developer and zero-cost risks elevated and added. Scores are reviewer estimates, not owner-accepted risk tolerance. See [RISK_REGISTER.md](RISK_REGISTER.md), “Scoring scale,” R01–R17. |
| Project Schedule | **Pass with conditions** | P1 authorized the target Requirements window 31 October–5 November subject to tracked schedule risk. Dates and effort remain estimates; account checks and weekly capacity monitoring remain conditions. See [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md), “Estimation basis” and “Open schedule questions.” |
| Owner Decisions | **Pass** | Six confirmed decisions and remaining open items are separated. See [OWNER_DECISIONS.md](OWNER_DECISIONS.md), §§1–4. |
| Planning Gate P1 | **Pass** | Owner-approved conditional Planning exit and explicit Requirements authorization dated 29 October 2026 are recorded. Conditions remain open and tracked. See [PLANNING_GATE_P1.md](PLANNING_GATE_P1.md). |
| Planning Review | **Pass** | This report records status, evidence, gate criteria and Requirements exit pending approval. |

## 3. Verification findings

### Identity, lifecycle, scope and stage boundaries

- **Pass:** The reviewed documents consistently identify Tory and do not use a conflicting product name or tagline. The tagline is explicitly shown in the charter, ADR and technology evaluation; the PoC-specific reports focus on their experiment and do not repeat all product metadata. No contradictory tagline was found.
- **Pass:** Where the full lifecycle is stated, its order is Planning → Requirements → Design → Implementation → Testing → Deployment. The charter, ADR and schedule use this order; the PoC reports are scoped to Planning/technical feasibility and do not claim another lifecycle.
- **Pass:** The accepted Django/PostgreSQL decision is consistent in the README, PoC report conclusions, technology evaluation and ADR. Stale pre-approval wording was aligned to the owner decision without changing historical test claims.
- **Pass:** Product catalog CSV import is excluded; CSV import is limited to stock transactions and whole-batch rejection. CD remains optional. No frontend framework, hosting provider, absolute deadline or budget number is selected as final.
- **Pass:** Charter deliverables distinguish Planning artifacts from the future SRS, Design specification, implementation, formal Testing evidence and Deployment demonstration. The schedule likewise uses stage entry/exit gates and explicitly states PoC tests do not complete formal Testing.

### Technical feasibility and evidence

- **Pass with evidence limits:** The PoC source supports the described narrow Django/PostgreSQL implementation: a Product model and migration, transactional stock-change service with row locking, an outer-transaction CSV importer, and a PostgreSQL concurrency test. Reports document historical constraint, movement, rollback and one competing stock-out case. These do not establish production readiness, load/performance, RBAC, forecasting, staging or CI.
- **Open evidence gap:** `docs/POC_RESULTS.md` and `docs/POC_HANDOVER.md` report `Found 14` / `Ran 14` and 14 passing. At the source PoC review, its `inventory/tests.py` contained 15 test methods (14 in `InventoryTests`, one concurrency test); that file was not transferred here. The owner-reported later 16/16 run has no matching output/source revision in the reviewed workspace. It remains unverified; no test run was performed for this review. Keep these facts distinct and do not cite 16/16 as verified until artifacts are supplied or a fresh run is captured against verified disposable PostgreSQL.
- **Pass with high schedule risk:** The feasibility assessment uses confirmed SGD 0, the fixed deadline and 10–15 hours/week. The estimate is 44–54 hours including contingency, compared with roughly 43–64 hours available. It does not assume a zero-cost service works without eligibility/quota checks.
- **Provider research:** Official documentation checked 29 October 2026 supports a plausible candidate architecture: GitHub Actions with a PostgreSQL service container; Render Free Python web service; and Supabase Free PostgreSQL. Candidates have material limits (private-repo CI minutes plan-dependent; Render idle spin-down/ephemeral filesystem and external-traffic suspension risk; Supabase 500 MB/5 GB quotas, inactivity pause and no included Free backups). Account eligibility, payment conditions, quotas, actual connectivity and zero-charge operation remain unverified. No provider is approved or selected.
- **Pass with owner confirmation needed:** The Risk Register identifies R04 recovery via an owner-approved process rather than presuming an audit ledger already exists. The ledger is a Design question, not a current PoC capability.

### Arithmetic verification

The framework scores in the evaluation and ADR were recalculated from the listed weights and scores:

| Candidate | Verified total |
|---|---:|
| Django 5.2 + PostgreSQL | `0.25×5 + 0.20×4 + 0.15×4 + 0.15×4 + 0.10×3 + 0.10×4 + 0.05×3 = 4.10 / 5` |
| FastAPI + PostgreSQL | `0.25×4 + 0.20×3 + 0.15×3 + 0.15×4 + 0.10×3 + 0.10×5 + 0.05×3 = 3.60 / 5` |
| Node.js/Express + PostgreSQL | `0.25×4 + 0.20×3 + 0.15×3 + 0.15×3 + 0.10×5 + 0.10×4 + 0.05×3 = 3.55 / 5` |

The framework totals remain 4.10, 3.60 and 3.55; all verify from the listed weights and scores. Risk calculations were checked as `Likelihood × Impact`. R01–R17 scores are respectively **16, 15, 15, 15, 12, 15, 16, 16, 15, 20, 20, 25, 20, 16, 9, 25, 20**; each matches the listed factors and risk band. The bands are arithmetically consistent: 1–4 Low, 5–9 Moderate, 10–16 High, 17–25 Very high. The revised schedule effort estimates sum to 40–49 hours plus 4–5 hours contingency (44–54 total). These are planning estimates, not measured actuals; weekly capacity and stage-gate availability still require monitoring.

## 4. Findings by severity

Severity: **High** threatens correctness, security, stage acceptance or project viability; **Medium** needs owner resolution before a downstream gate; **Low** is a documentation or planning improvement that does not contradict the approved baseline.

| ID | Severity | Finding and exact reference | Disposition |
|---|---|---|---|
| F01 | Medium | Test evidence discrepancy: [POC_RESULTS.md](../POC_RESULTS.md), “Environment and commands”; [POC_HANDOVER.md](../POC_HANDOVER.md), §3; [ADR-001](../decisions/ADR-001-backend-and-database.md), §5; PoC-only `inventory/tests.py` as reviewed at source. Reports say 14 passed, source had 15 test methods, and reported 16/16 output is absent. | Preserved as unresolved. Obtain original output with source revision or capture a verified PostgreSQL run before representing 16/16 as independently verified. |
| F02 | High | Deadline/capacity margin is narrow: [FEASIBILITY_ASSESSMENT.md](FEASIBILITY_ASSESSMENT.md), Executive assessment and §5; [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md), effort table and estimate basis. Work + contingency is 44–54h against 43–64h theoretical availability. | Charter scope is approved and must not be silently reduced. Track hours at gates; owner to request formal schedule change or approve a formal scope change if forecast exceeds capacity. |
| F03 | High | Zero-cost CI/staging is not yet verified: [FEASIBILITY_ASSESSMENT.md](FEASIBILITY_ASSESSMENT.md), “Zero-cost service candidates”; [OWNER_DECISIONS.md](OWNER_DECISIONS.md), unresolved items. | Candidate providers only; verify account eligibility, no-payment/overage conditions, quotas, PostgreSQL connectivity and demo suitability before Design exit. No paid fallback without explicit change approval. |
| F04 | Medium | Interim review dates, stakeholder availability and service-account access timing remain unknown: [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md), “Open schedule questions”; [PROJECT_CHARTER.md](PROJECT_CHARTER.md), “Dependencies and constraints.” | Track these under P1 conditions and confirm availability as work proceeds; escalate if the target Requirements exit is threatened. |
| F05 | Medium | R04 recovery process is not yet designed: [RISK_REGISTER.md](RISK_REGISTER.md), R04; [ADR-001](../decisions/ADR-001-backend-and-database.md), §8. | Keep recovery procedure owner-approved; do not assume an audit ledger, backup service or restore feature exists. Resolve in Requirements/Design. |
| F06 | Low | Stakeholder/user access and permission ownership are not confirmed: [PROJECT_CHARTER.md](PROJECT_CHARTER.md), “Proposed stakeholders”; [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md), Requirements dependencies. | Confirm whether Manager/Staff representatives or sample data are available; otherwise define an owner-approved elicitation method in Requirements. |
| F07 | Low | Technology and risk scores are judgment-based, not measured: [TECHNOLOGY_EVALUATION.md](../TECHNOLOGY_EVALUATION.md), §4; [RISK_REGISTER.md](RISK_REGISTER.md), “Scoring scale.” | No arithmetic corrections needed. Do not treat scores as empirical measurements or owner-accepted risk tolerance. |

No remaining substantive contradiction was found between the fixed functional scope, the approved Charter and ADR-001. The main concerns are feasibility and open decisions, not scope ambiguity.

## 5. Outstanding owner decisions

1. During Requirements, resolve the proposed business rules and requirement decisions listed in the SRS review; Charter approval did not approve detailed requirement behavior.
2. Confirm permitted CI/staging accounts and verify eligibility, quotas, PostgreSQL support/connectivity and no-charge safeguards before Design exit; provider candidates are not selected.
3. Confirm interim review turnaround, weekly capacity (including any weekend availability) and stakeholder/requirements-elicitation access; escalate if the target Requirements exit is threatened.
4. Review risk responses and explicitly accept/revise owners, risk tolerance and contingency authority; P1 did not accept risk scores or specific contingency decisions.
5. Decide whether to obtain artifacts for the reported 16/16 run or keep it unverified; either choice does not replace formal Testing.
6. Record an explicit Requirements exit decision after SRS review; P1 authorized entry only.

The approved backend decision is not outstanding: Django 5.2 LTS + PostgreSQL is final for the Planning baseline under [ADR-001](../decisions/ADR-001-backend-and-database.md), unless formally changed.

## 6. Planning acceptance criteria

P1 has been approved with conditions and Requirements entry explicitly authorized. Conditions carried forward are:

- The project owner approval of the Charter (29 October 2026) remains recorded; the Charter itself is approved.
- ADR-001 remains the accepted backend decision and the pre-approval wording corrected during this review stays reconciled.
- Track effort against the 44–54 hour estimate and 43–64 hour theoretical capacity; use formal schedule or scope change control if feasibility degrades. Approved scope remains unchanged absent an approved change.
- Verify an eligible zero-cost PostgreSQL CI/staging path for quota, connectivity and no-charge operation before Design exit.
- Review risk response owners, risk tolerance and contingency authority; P1 did not accept the estimated scores or specific treatments.
- Continue to use the sequential schedule and target Requirements window 31 October–5 November, subject to schedule-risk escalation.
- The 14/15/16 test evidence discrepancy remains accurately documented: reports record 14 passing, current source has 15 methods, and 16/16 remains owner-reported without a matching artifact. Resolving it is not misrepresented as completion of formal Testing.
- Requirements, Design, Implementation and formal Testing remain future work; P1 did not approve Requirements exit.

## 7. Proposed sign-off record

| Role | Name | Decision | Date | Signature / record |
|---|---|---|---|---|
| Project owner | Tory project owner | **Planning exit approved with conditions; Requirements entry authorized** | 29 Oct 2026 | [PLANNING_GATE_P1.md](PLANNING_GATE_P1.md) memorializes the official owner decision |
| Solo developer | Same person as owner | Acknowledged / comments | TBD | TBD |
| Course assessor / supervisor (if required) | TBD | Review / comments | TBD | TBD |

The conditional P1 approval authorizes Requirements entry only. It does **not** imply Requirements exit approval or resolve the tracked conditions.

## 8. Final recommendation

**Planning exit approved with conditions; Requirements entry authorized.** The 29 October owner decision is recorded in P1. The 44–54 estimated remaining hours remain close to or above capacity at the lower end, and zero-cost CI/staging eligibility is unverified; these remain tracked conditions and schedule risks. Requirements may proceed in its target window, but Requirements exit requires owner approval of the SRS and disposition of open questions. The 14/15/16 test discrepancy remains unresolved and is not formal Testing evidence.

## 9. Changes made during this review

- Updated the Charter with explicit owner approval dated 29 October 2026.
- Updated feasibility and schedule with the deadline, capacity and SGD 0 ceiling; researched official provider terms and listed candidates only.
- Elevated schedule, free-tier and solo-availability risks; added capacity/zero-cost risks. No risk acceptance is recorded.
- Added [OWNER_DECISIONS.md](OWNER_DECISIONS.md) and updated this independent Planning review.
- Recorded conditional Planning exit and explicit Requirements authorization in [PLANNING_GATE_P1.md](PLANNING_GATE_P1.md); Requirements exit remains pending.
- Preserved the 14/15/16 test evidence discrepancy. No test was run.
- No application code, tests, migrations or database were changed. No commit, push or deployment was performed.
