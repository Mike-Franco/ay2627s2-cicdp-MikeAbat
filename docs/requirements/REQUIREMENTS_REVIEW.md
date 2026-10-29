# Tory Requirements Review

**Review status:** Draft review complete; SRS **PENDING OWNER APPROVAL**.  
**Requirements exit:** **NOT APPROVED**.  
**Target window:** 31 October–5 November 2026, subject to tracked schedule risk.  
**P1:** Planning exit approved with conditions; Requirements entry authorized 29 October 2026.

## 1. Review summary

The draft SRS is aligned to the approved Charter, P1 conditions and ADR-001. It covers all fixed baseline capabilities and keeps proposed detail separate from approved scope. It does not select a frontend, hosting provider, application architecture or CI vendor. No implementation, test completion, stakeholder interview, market study, or zero-cost provider eligibility is claimed.

Jira and a separate `tory-inventory` GitHub repository are desired work-management changes. Neither is verified as configured or required to approve a product behavior in this SRS; repository migration, if pursued, needs a separate recorded decision.

Completeness is **partial pending owner decisions**. The largest ambiguity is how demand is derived from stock movements: stock-out does not necessarily mean demand, and the PoC has no ledger or demand history. Role permissions, product maintenance fields, adjustment semantics, CSV contract specifics and reorder formula also require approval. These decisions directly affect data design and testability.

## 2. Completeness, consistency and testability review

| Review area | Status | Finding |
|---|---|---|
| Fixed scope coverage | Pass | Manual stock movements, atomic stock-transaction CSV, PostgreSQL, distinct roles, per-product settings, seven-day average, recommendation, staging and CI are represented. Product catalog import and unapproved features remain excluded. |
| Approved decisions | Pass | Django 5.2 LTS + PostgreSQL follows ADR-001; exact deployment versions/providers remain TBD. P1 authorized Requirements entry with conditions only. |
| Functional completeness | Needs owner decisions | FRs cover all baselines, but role actions, product CRUD/identity, movement history and demand-source rules are not approved. |
| Correctness / data integrity | Needs owner decisions | Negative-stock, adjustment, duplicate request, CSV ordering/idempotency and movement-history semantics are proposed, not approved. |
| Forecast testability | Needs owner decisions | Window, timezone, eligible demand source, zero vs missing days, insufficient history, rounding and recommendation formula need a decision before deterministic acceptance cases can be baselined. |
| Security / RBAC | Needs owner decisions | Role distinction is confirmed; all action permissions and account lifecycle are proposed/TBD in the matrix. |
| Nonfunctional testability | Partial | Numeric response targets are proposed, but dataset and concurrency profile are TBD. Availability, recovery objectives, browser/accessibility criteria and retention have no approved targets. |
| Zero-cost feasibility | Open risk | GitHub Actions, Render and Supabase remain candidates. Eligibility, quotas, payment/overage safeguards, PostgreSQL connectivity, external egress and recovery limits are unverified. |
| Test evidence | Open evidence gap | Source PoC reports record 14/14 passing; PoC source reviewed there had 15 test methods; the later 16/16 result is owner-reported and lacks a matching artifact/source revision. None is formal Tory Testing. |
| Schedule/capacity | High risk | Deadline is 27 November 2026; capacity 10–15 hours/week. Planning estimates 44–54 remaining hours including contingency versus 43–64 theoretical hours. Target Requirements window is compressed and all downstream stages must follow sequentially. |
| Stage boundaries | Pass | SRS and proposed criteria are Requirements work; architecture and schema details are deferred to Design; no implementation or formal Testing is claimed. |

## 3. Owner decisions required for SRS approval

These eight decision packages capture all material open business choices in the draft. A decision may approve the proposed rule, replace it, or defer it with an owner and target stage. No interview or external stakeholder validation is assumed.

1. **Product and inventory identity:** required product fields, SKU normalization/case rules, product create/edit/deactivate rights, and behavior for products with movement history.
2. **Role and account policy:** approve each Manager/Staff cell in [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md), especially stock adjustment, CSV import, configuration read/write, user provisioning and any administrator role.
3. **Stock movement semantics:** quantity units, zero/negative handling, negative stock policy, adjustment as absolute count vs signed delta, reason requirement, movement history/retention, duplicate request/retry handling and concurrency expectations.
4. **CSV contract:** header/encoding/BOM, strictness, row shape, repeated SKU order, header-only file, max bytes/rows, repeated whole-file handling, error reporting and Manager/Staff permission.
5. **Demand source:** identify where eligible daily demand comes from and approve whether a manual stock-out can be treated as demand; distinguish demand from adjustment, shrinkage, transfer or correction if applicable.
6. **Forecast and reorder rules:** seven calendar days vs other boundary, timezone, missing/zero/insufficient history, rounding/display precision, lead-time units, safety-stock units, formula, inbound stock treatment, reorder trigger and any MOQ/pack-size settings.
7. **Nonfunctional targets:** approve/revise proposed 2s/3s p95 warm-response targets and test dataset/load; decide staging availability expectation, backup/restore/retention and security/accessibility expectations. Numeric values not approved remain TBD.
8. **Scope and feasibility response:** confirm that the fixed deadline and scope remain unchanged while tracking the 44–54h estimate; if forecasts exceed available hours, decide whether to request schedule change control or submit a formal scope change. Verify a zero-cost PostgreSQL CI/staging path before Design exit; no provider is selected.

## 4. Planning conditions carried into Requirements

- Keep the approved scope and exclusions intact; no silent reduction to compensate for schedule risk.
- Treat the P1 date, 10–15 hours/week, 27 November deadline and SGD 0 cap as fixed unless formally changed.
- Track actual effort and gate slippage; escalate immediately if projected completion exceeds available hours.
- Do not accept provider candidates as viable until account eligibility, quotas, PostgreSQL connectivity and no-charge safeguards are verified.
- Keep risk scores provisional; P1 did not approve risk tolerances or contingency decisions.
- Preserve the test evidence distinction: 14 recorded, 15 test methods in the reviewed PoC source, 16/16 owner-reported but unverified. Do not claim formal Testing completion.

## 5. Requirements exit checklist

Requirements exit remains pending until all are completed and explicitly approved by the owner:

- [ ] All fixed baseline requirements remain covered with no unapproved scope additions.
- [ ] Owner resolves or explicitly defers the eight decision packages above.
- [ ] Manager/Staff matrix is approved and traced to FR/NFR IDs.
- [ ] Business rules and edge cases are approved or marked deferred with owners/target stage.
- [ ] Each approved Must requirement has deterministic acceptance criteria and a traceability entry.
- [ ] Proposed numeric NFR targets are approved, revised or replaced with justified TBDs.
- [ ] Scope, zero-cost constraint and schedule risk are reconciled; no budget or provider assumption is implicit.
- [ ] Owner approves the SRS revision and records Requirements exit / Design entry separately.

**Current decision: Requirements exit PENDING OWNER APPROVAL.**

## 6. Review and evidence references

- [SRS](SOFTWARE_REQUIREMENTS_SPECIFICATION.md)
- [Role Permission Matrix](ROLE_PERMISSION_MATRIX.md)
- [Business Rules and Edge Cases](BUSINESS_RULES_AND_EDGE_CASES.md)
- [Traceability Matrix](REQUIREMENTS_TRACEABILITY_MATRIX.md)
- [P1 Gate Record](../planning/PLANNING_GATE_P1.md)
- [Owner Decisions](../planning/OWNER_DECISIONS.md)
- [Feasibility Assessment](../planning/FEASIBILITY_ASSESSMENT.md) and [Project Schedule](../planning/PROJECT_SCHEDULE.md)
- [ADR-001](../decisions/ADR-001-backend-and-database.md), [Technology Evaluation](../TECHNOLOGY_EVALUATION.md), and [PoC evidence](../POC_RESULTS.md)
