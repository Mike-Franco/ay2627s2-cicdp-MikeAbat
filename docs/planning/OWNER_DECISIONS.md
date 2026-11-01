# Tory Owner Decisions and Open Items

**Decision date:** 29 October 2026  
**Source:** Project owner confirmations for Tory ST0529 CA1  
**Product:** Tory — Inventory Management & Demand Forecasting System  
**Tagline:** *Inventory made simple.*

## Confirmed owner decisions

| ID | Confirmed decision | Planning implication |
|---|---|---|
| OD-01 | **Project deadline is 27 November 2026.** | Schedule all six sequential Waterfall stages to the date; do not invent extension or interim due dates. Any change requires owner change control and course-rule confirmation. |
| OD-02 | **Project owner and developer are one solo developer.** | Plan all analysis, development, review, testing, documentation and demo work against one person's availability; no additional staff capacity is assumed. |
| OD-03 | **Available project time is 10–15 hours per week.** | Approximate capacity from 29 October through 27 November is 43–64 hours if sustained. Stage-gate waits, course conflicts and setup delays may reduce usable time. |
| OD-04 | **Cash budget ceiling is SGD 0; zero-cost services only.** | Do not select a paid tier, incur overage, or add a payment method with possible charges without a formal owner decision. Candidate eligibility and quotas must be checked. |
| OD-05 | **Project Charter is approved on 29 October 2026**, including high-level scope, exclusions, deliverables and proposed success-criteria framing. | Preserve the approved charter scope. Detailed acceptance criteria still belong in the Requirements SRS; charter approval is not Planning stage-exit approval. |
| OD-06 | **Backend is Django 5.2 LTS + PostgreSQL**, already accepted in ADR-001. | This is the final Planning backend baseline unless changed through a formal approved change request. Exact deploy patch/provider remain later decisions. |
| OD-07 | **Planning exit P1 approved with conditions on 29 October 2026; Requirements entry explicitly authorised.** | Carry the P1 conditions into Requirements. This does not approve the SRS, Requirements exit or Design entry. |

## Fixed identity and scope baseline

Product name is Tory; tagline is *Inventory made simple.* Fixed scope remains manual stock-in/out/adjustments; atomic CSV stock-transaction import only (no product catalog import); PostgreSQL; Manager and Staff permissions; per-product supplier lead time and safety stock/reorder settings; explainable seven-day moving-average demand forecasting; hosted staging demonstration and automated CI; automated CD optional. No scope reduction is authorized by these decisions.

## Remaining unresolved items

These are not owner decisions and must not be treated as settled:

- **Requirements exit:** P1 authorized entry to Requirements on 29 October 2026; no approval of the SRS or Requirements exit is recorded. Requirements exit remains pending.
- **Feasibility:** estimated remaining work is 40–49 hours plus a 4–5-hour contingency (44–54 total), versus approximately 43–64 hours of capacity. This is marginal and likely infeasible at 10 hours/week; owner must decide whether to request a schedule change or, if necessary, a formally approved scope change. No fixed requirement may be silently removed.
- **CI and staging services:** GitHub Actions, Render and Supabase are research candidates only. Account eligibility, repository privacy, payment-method requirements, quotas, PostgreSQL connectivity/support, region, egress, inactivity behavior and no-charge safeguards remain to be checked. No provider is selected.
- **Interim dates / review turnaround:** course submission instructions, interim milestones, owner/assessor review turnaround and weekend availability are TBD.
- **Detailed requirements:** exact Manager/Staff permission matrix; CSV encoding/limits/error format; adjustment and audit-history behavior; supplier-setting validation; forecast input source/quality, insufficient-history/missing-day/rounding rules, and reorder formula; acceptance thresholds; nonfunctional expectations.
- **Design/deployment choices:** frontend and application architecture, staging topology/provider, exact Python/Django/PostgreSQL/driver versions for deployment, secrets management, backup/recovery and data retention.
- **PoC test evidence:** existing reports record 14/14 passing, current source has 15 test methods, and a later 16/16 run is owner-reported without a matching output/source revision. Preserve discrepancy until verified artifacts are supplied. PoC results do not complete formal Testing.
- **Risk treatment:** likelihood/impact scores in the risk register are reviewer estimates. Owner acceptance of risk tolerance, contingencies and escalation authority has not been recorded.
- **Work management and repository changes:** Jira and a separate `tory-inventory` GitHub repository are desired, but configuration, repository ownership and any migration are unverified. The current official course repository remains `Mike-Franco/ay2627s2-cicdp-MikeAbat` until an explicit change is made.

## Planning gate P1 record

The owner approved Planning exit **with conditions** and explicitly authorized entry to Requirements on **29 October 2026**. See [PLANNING_GATE_P1.md](PLANNING_GATE_P1.md). The conditions are tracked, not resolved by the authorization. This approval does not authorize Requirements exit, Design entry or any scope reduction.

## Change control

Any change to the deadline, zero-cash ceiling, approved charter scope or accepted backend requires a documented change request with impact on requirements, security, schedule, feasibility and demonstration. Obtain explicit project owner approval before changing the baseline. P1 is approved with conditions, while Requirements exit and later gates remain pending.

## Related records

- [Approved Project Charter](PROJECT_CHARTER.md)
- [Feasibility Assessment](FEASIBILITY_ASSESSMENT.md)
- [Project Schedule](PROJECT_SCHEDULE.md)
- [Risk Register](RISK_REGISTER.md)
- [Planning Gate P1](PLANNING_GATE_P1.md)
- [Accepted ADR-001](../decisions/ADR-001-backend-and-database.md)
- [Planning Review](PLANNING_REVIEW.md)
