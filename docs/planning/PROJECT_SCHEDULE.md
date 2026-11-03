# Tory Project Schedule — Current Kanban Plan and Original Baseline

**Course:** Singapore Polytechnic ST0529 CA1  
**Current delivery method:** Lightweight Agile Kanban, owner-approved 3 November 2026 in [ADR-002](../decisions/ADR-002-agile-kanban-delivery.md)
**Deadline:** 27 November 2026 at **17:00 Asia/Singapore**
**Capacity:** 10–15 hours/week; solo developer; SGD 0 cash ceiling
**Status:** Forward plan is an estimate, not an approved scope reduction or delivery guarantee. The original Waterfall schedule is retained below as dated history.

## Remaining incremental plan from 3 November 2026

The interval from 3 November through 27 November is about 3.6 weeks, giving roughly **36–54 theoretical hours** at the approved weekly capacity. Actual available hours, coursework and service setup are unverified. The historical 44–54-hour estimate below was made before all later security, performance and feasibility detail was resolved; it is **not** a current proof of fit. The low-capacity case is unlikely to complete all approved work. Track actual hours and remaining effort after every reviewed increment; escalate a forecast miss to the owner for explicit schedule/scope change control. Do not silently omit security, PostgreSQL tests, backup/restore, hosted staging or assessment evidence.

| Working window (Singapore time) | Capacity guide | Priority and reviewable outcome |
|---|---:|---|
| 3–9 November | 10–15 h | Triage unresolved gaps against dependent work; choose a narrow stock-correctness increment with PostgreSQL-backed transaction and permission tests. Check G-10 account/HTTPS/email/backup feasibility early. Record decisions and evidence; do not infer approvals. |
| 10–16 November | 10–15 h | Continue stock/batch, adjustment and atomic CSV increments with rejection and concurrency evidence. Review pull requests and update traceability. Advance authentication only after its dependent G-09/G-10/G-13 questions are addressed or explicitly bounded. |
| 17–23 November | 10–15 h | Integrate seven-day demand, reorder and role-scoped workflows; run regression and approved security cases. Establish real PostgreSQL pull-request CI and hosted staging/backup/restore evidence if feasible; expose unresolved provider or benchmark blockers immediately. |
| 24–27 November, ending 17:00 on the 27th | Approximately 6–9 h at the weekly rate | Complete acceptance/regression evidence, assessment and report material, deployment/demo rehearsal, hosted staging demonstration and handover. Reserve time for defect correction and final review; do not claim formal results before execution. |

**Capacity accounting:** the four windows provide approximately **36–54 hours** if availability holds. Protect **3–4 hours of that total as contingency** for defects, integration or service delays, leaving about **32–51 hours for planned work**. Within the final window, explicitly allow **4–5 hours for assessment evidence, report, demo rehearsal and presentation**; this is part of planned work, not extra capacity. These allocations are provisional and overlap in calendar time because Kanban work is incremental, not sequential stage gates. At 10 hours/week the available planned-work range is too tight for the historical estimate, even before later requirements detail; prompt owner change control may be necessary.

Use **To do → In progress → Review/Test → Done**, with one item in progress. Each Jira issue should carry requirement/gap references, acceptance criteria, implementation PR and automated test evidence when applicable; no Jira issue creation is claimed. Pull by stock correctness and dependency. Resolve an open gap before its dependent feature; unrelated gaps do not block all implementation. Preserve the [requirements review](../requirements/REQUIREMENTS_REVIEW.md), [gap analysis](../requirements/REQUIREMENTS_GAP_ANALYSIS.md) and [traceability matrix](../requirements/REQUIREMENTS_TRACEABILITY_MATRIX.md) as living evidence. Their historical pending SRS/stage decisions remain pending; an issue reaching Done does not approve them.

## Original Waterfall schedule — historical 29 October Planning baseline

**Original lifecycle order:** Planning → Requirements → Design → Implementation → Testing → Deployment
**Original owner-confirmed deadline:** 27 November 2026 (later clarified as 17:00 Asia/Singapore)
**Original available capacity:** 10–15 hours per week
**Historical schedule status:** P1 approved with conditions on 29 October 2026. All subsequent stage windows and gates below are the original plan, **not the current delivery sequence**.

### Estimation basis

The owner approved the Charter and backend decision and approved Planning exit with conditions, explicitly authorizing Requirements entry on 29 October 2026; see [PLANNING_GATE_P1.md](PLANNING_GATE_P1.md). Requirements is targeted for 31 October–5 November. The calendar windows below are consecutive target windows with no overlap between formal stages. Work-hour values are **ESTIMATES**, separate from elapsed dates. The owner-confirmed 10–15 hours/week over 30 calendar days (29 October–27 November inclusive) yields approximately **43–64 available hours**, assuming project capacity is sustained through the period. Actual course conflicts, stage-gate turnaround and provider setup time may reduce this capacity.

| Stage (fixed order) | Target calendar window | Remaining work hours — ESTIMATE |
|---|---|---:|
| 1. Planning close-out | 29–30 October | 1–2 |
| 2. Requirements | 31 October–5 November | 6–8 |
| 3. Design | 6–12 November | 6–8 |
| 4. Implementation | 13–20 November | 16–17 |
| 5. Testing | 21–25 November | 8–10 |
| 6. Deployment | 26–27 November | 3–4 |
| **Stage work subtotal** | **29 October–27 November** | **40–49** |
| Cross-stage contingency reserve | Within the same deadline window | **4–5** |
| **Total remaining effort — ESTIMATE** |  | **44–54 hours** |

The remaining stage-work estimate (midpoint-based) is approximately 3% Planning, 16% Requirements, 16% Design, 37% Implementation, 20% Testing and 8% Deployment, before contingency. The previous schedule allocated 9%, 14%, 14%, 27%, 18% and 8% respectively, with a separate 10% reserve; normalized to its stage-work subtotal, that is approximately 10%, 15.6%, 15.6%, 30%, 20% and 8.9%. The revised mix reduces Planning because most Planning work is complete and increases Implementation because the remaining build/integration burden was previously underweighted. Both distributions are planning estimates, not measured actuals.

Reserve approximately **10% of stage work (4–5 hours) as contingency**, inside the total remaining effort estimate. Use it for rework, learning, integration, service access delays or stage-gate slippage. The total estimate of 44–54 hours is close to the 43–64 hour capacity range; at 10 hours/week there is effectively no buffer, while the estimate fits more credibly only with sustained capacity nearer the middle or upper end and work near the estimate. If estimates or capacity indicate a miss, seek schedule change control; do not compress formal Testing or silently reduce approved scope.

### Stage plan and gates

| Order / stage | Target window and dependency | Main work and milestone | Deliverables | Exit criteria / gate |
|---|---|---|---|---|
| 1. Planning | 29–30 Oct; P1 approved with conditions on 29 Oct. | Record conditional exit and carry open actions forward. **P1:** approved with conditions 29 Oct. | Approved charter, feasibility assessment, risk register, schedule, technology evaluation, accepted ADR, Planning review, P1 decision record | Planning exit and Requirements entry are authorized; conditions remain tracked and do not imply SRS approval. |
| 2. Requirements | 31 Oct–5 Nov; only after P1 approval | Define and baseline functional/nonfunctional requirements, role matrix, CSV contract, inventory rules, supplier settings, forecast/reorder formula, edge cases and acceptance criteria. **R1:** SRS review by 5 Nov. | SRS, traceability matrix, acceptance criteria, approved changes | Owner approves SRS and explicitly authorizes Design; unresolved items accepted/deferred with owners. |
| 3. Design | 6–12 Nov; only after R1 | Define application/data/security architecture, audit/movement approach, interfaces, error handling, tests, PostgreSQL environment and candidate staging/CI design. **D1:** design review by 12 Nov. | Design specification, data model, interface/security design, test plan, environment/deployment design | Owner approves design, confirms zero-cost service feasibility/account checks, and authorizes Implementation. |
| 4. Implementation | 13–20 Nov; only after D1 | Implement approved scope, migrations, permissions, transaction import, supplier settings, forecast, PostgreSQL CI and staging integration as designed. **I1:** test candidate by 20 Nov. | Application, migrations, CI workflow, configuration and implementation notes | Requirements-to-build review passed; changes reviewed; candidate and test environment ready for formal Testing. |
| 5. Testing | 21–25 Nov; only after I1 | Run approved integration, security/permission, database, CSV atomicity, forecast, regression and acceptance tests; fix/retest and record defects. **T1:** test exit review by 25 Nov. | Test evidence, defect log/disposition, traceability and test-stage decision | Owner accepts test results/residual defects under approved exit rule. PoC tests do not count as formal Testing. |
| 6. Deployment | 26–27 Nov; only after T1 | Deploy/configure hosted staging, verify smoke/demo flow, access controls, data handling and handover. **DEP1:** demonstration/acceptance by 27 Nov deadline. | Hosted staging demonstration, deployment notes, configuration/handover evidence | Owner accepts the staging demonstration and required artifacts by the deadline; production deployment is not implied. |

### Dependencies, checkpoints and schedule controls

- The stage order is fixed. Work may be prepared in advance, but a later stage does not formally begin before the preceding exit review is approved.
- The owner-confirmed deadline is 27 November 2026 and weekly capacity is 10–15 hours. These do not imply the schedule is feasible at every point in that range.
- Confirm PostgreSQL service access, CI provider, staging provider, credentials/secrets handling, account eligibility, quotas and zero-cost operation before Design exit.
- Hold a brief owner review at each stage gate. Record approval, deferred items and change requests.
- Track estimates against actual effort at each gate; adjust remaining stage allocations and contingency by owner approval.
- Escalate when a high-risk item threatens an exit criterion or the contingency reserve is materially consumed.
- Automated CD is optional and is not a schedule commitment. Automated CI and hosted staging demonstration are in the fixed baseline.

### Open schedule questions

1. What interim submission/review dates and owner/assessor turnaround apply? **TBD.**
2. Can the developer sustain 10–15 project hours every week through the deadline, including coursework conflicts? **Confirm at each gate.**
3. Which no-cost staging and CI accounts are eligible, support PostgreSQL, and remain within quota? **TBD.**
4. Is the estimated 44–54 remaining hours and 4–5-hour buffer acceptable against the deadline? **Owner decision required.**
5. If effort or capacity tracking predicts a miss, should the owner request a schedule change or formally revise scope? Do not make this change silently.

### References

- [Project Charter](PROJECT_CHARTER.md)
- [Feasibility Assessment](FEASIBILITY_ASSESSMENT.md)
- [Risk Register](RISK_REGISTER.md)
- [Accepted backend ADR](../decisions/ADR-001-backend-and-database.md)
- [Current delivery-method ADR](../decisions/ADR-002-agile-kanban-delivery.md)
- [PoC evidence](../POC_RESULTS.md) and [Technology Evaluation](../TECHNOLOGY_EVALUATION.md)
