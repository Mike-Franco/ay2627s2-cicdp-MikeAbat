# Planning Gate P1 — Exit Decision

**Project:** Tory — Inventory Management & Demand Forecasting System  
**Course:** Singapore Polytechnic ST0529 CA1  
**Gate:** Planning exit (P1)  
**Decision date:** 29 October 2026  
**Decision authority:** Project owner  
**Status:** **APPROVED WITH CONDITIONS**

## Gate decision

The project owner approved exit from Planning and explicitly authorized entry to the Requirements stage on **29 October 2026**. The approved Planning Charter and backend decision remain in force. This approval is conditional on carrying forward the risks and open actions below; it does not certify that they are resolved or authorize changes to the approved scope.

## Conditions and tracked actions

1. **Deadline and capacity risk:** deadline remains 27 November 2026, capacity 10–15 hours/week, and cash budget SGD 0. The current remaining-work estimate is 44–54 hours including contingency against approximately 43–64 hours of theoretical capacity. Track effort at each gate. If the forecast exceeds capacity, request formal schedule change control; do not silently remove fixed scope.
2. **Zero-cost CI and staging:** GitHub Actions, Render and Supabase are candidates only. Verify account eligibility, payment/overage conditions, quotas, PostgreSQL connectivity/support and no-charge operation before Design exit. No provider is selected or approved by P1.
3. **Risk treatment:** risk likelihood/impact scores and mitigations remain Planning estimates. Owner acceptance of risk tolerance, contingency authority and individual response choices is not implied by P1; review at the next gate.
4. **PoC evidence:** preserve the reported 14/14 result, current 15 test methods and owner-reported but unverified 16/16 run as distinct evidence. Obtain the original artifact or leave 16/16 unverified. PoC tests are not formal Testing evidence.
5. **Requirements approval:** the Requirements stage must baseline detailed permissions, CSV contract, stock rules, forecast/reorder rules, data assumptions and testable acceptance criteria. Owner approval of the Charter does not approve these detailed requirements.
6. **Later-stage decisions:** frontend, application architecture, hosting provider, exact deployment versions and detailed pipeline remain undecided for their appropriate stages.

## Authorization and boundaries

- **Requirements entry:** authorized from 31 October 2026, subject to the target window recorded in [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md) and ongoing schedule-risk tracking.
- **Requirements exit:** not approved by this decision; requires a separately recorded owner review and approval of the SRS.
- **Scope:** the approved Charter scope and exclusions remain unchanged. Any change requires a formal change request and owner approval.
- **Technology:** Django 5.2 LTS + PostgreSQL remains the accepted Planning backend under [ADR-001](../decisions/ADR-001-backend-and-database.md).

## Record

| Role | Decision | Date | Evidence |
|---|---|---|---|
| Project owner | Planning exit approved with conditions; Requirements entry explicitly authorized | 29 October 2026 | Owner's official project decision; this record memorializes it |

## Related records

- [Owner Decisions](OWNER_DECISIONS.md)
- [Planning Review](PLANNING_REVIEW.md)
- [Approved Project Charter](PROJECT_CHARTER.md)
- [Feasibility Assessment](FEASIBILITY_ASSESSMENT.md)
- [Project Schedule](PROJECT_SCHEDULE.md)
- [Risk Register](RISK_REGISTER.md)
- [Accepted ADR-001](../decisions/ADR-001-backend-and-database.md)
