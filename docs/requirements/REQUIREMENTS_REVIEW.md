# Tory Requirements Review

**Review status:** Draft review complete; SRS **PENDING OWNER APPROVAL**.  
**Requirements exit:** **NOT APPROVED**.  
**Target window:** 31 October–5 November 2026, subject to tracked schedule risk.  
**P1:** Planning exit approved with conditions; Requirements entry authorized 29 October 2026.

## 1. Review summary

The draft SRS is aligned to the approved Charter, P1 conditions and ADR-001. It covers all fixed baseline capabilities and keeps proposed detail separate from approved scope. It does not select a frontend, hosting provider, application architecture or CI vendor. No implementation, test completion, stakeholder interview, market study, or zero-cost provider eligibility is claimed.

Jira and a separate `tory-inventory` GitHub repository are desired work-management changes. Neither is verified as configured or required to approve a product behavior in this SRS; repository migration, if pursued, needs a separate recorded decision.

Completeness is **partial pending owner decisions**. [BR-001–BR-011 and BR-026–BR-033](OWNER_REQUIREMENTS_DECISIONS.md) were individually approved on 29 October and 1 November 2026, respectively. The new rules cover Staff deactivation/assignment, product lifecycle, expired-batch quarantine, available-to-issue reorder input, demand exclusions, receiving-batch expiry and FEFO. Stock-out demand is not validated customer sales. Trustworthy daily coverage and dated movement evidence remain essential; their mechanism, retention and architecture remain undecided. No approval is inferred for BR-012–BR-025 or BR-034 onward.

## 2. Completeness, consistency and testability review

| Review area | Status | Finding |
|---|---|---|
| Fixed scope coverage | Pass | Manual stock movements, atomic stock-transaction CSV, PostgreSQL, distinct roles, per-product settings, seven-day average, recommendation, staging and CI are represented. Product catalog import and unapproved features remain excluded. |
| Approved decisions | Pass | Django 5.2 LTS + PostgreSQL follows ADR-001; exact deployment versions/providers remain TBD. P1 authorized Requirements entry with conditions only. |
| Functional completeness | Needs owner decisions | BR-001–BR-011 and BR-026–BR-033 approved individually; exact product stock-resolution workflow, other role actions, batch ordering, history/coverage and account provisioning remain open. |
| Correctness / data integrity | Needs owner decisions | No-negative, adjustment, CSV atomicity/duplicate rejection, product deactivation guard, quarantine and FEFO approved. Expiration boundary, CSV-versus-batch conflict, quarantine mechanism, duplicate identity/concurrency, manual retries and retention remain open. |
| Forecast testability | Partial | Prior seven complete Asia/Singapore days, verified zeros, missing-day unavailability, two-decimal display, full precision, available-to-issue reorder input and quarantine/disposal demand exclusion approved. Trustworthy observation coverage and movement classification remain unproven and need a Design solution. |
| Security / RBAC | Needs owner decisions | Manager-only adjustment, Manager Staff deactivation and constrained assignment approved. Other action permissions, session revocation timing and account lifecycle remain TBD. |
| Nonfunctional testability | Partial | Numeric response targets are proposed, but dataset and concurrency profile are TBD. Availability, recovery objectives, browser/accessibility criteria and retention have no approved targets. |
| Zero-cost feasibility | Open risk | GitHub Actions, Render and Supabase remain candidates. Eligibility, quotas, payment/overage safeguards, PostgreSQL connectivity, external egress and recovery limits are unverified. |
| Test evidence | Open evidence gap | Source PoC reports record 14/14 passing; PoC source reviewed there had 15 test methods; the later 16/16 result is owner-reported and lacks a matching artifact/source revision. None is formal Tory Testing. |
| Schedule/capacity | High risk | Deadline is 27 November 2026; capacity 10–15 hours/week. Planning estimates 44–54 remaining hours including contingency versus 43–64 theoretical hours. Target Requirements window is compressed and all downstream stages must follow sequentially. |
| Stage boundaries | Pass | SRS and proposed criteria are Requirements work; architecture and schema details are deferred to Design; no implementation or formal Testing is claimed. |

## 3. Approved rules and remaining owner decisions

The owner approved [BR-001–BR-011](OWNER_REQUIREMENTS_DECISIONS.md) on 29 October 2026 and BR-026–BR-033 on 1 November 2026. These approvals do not approve the complete SRS or Requirements exit. The following choices remain open; the owner may approve, revise or explicitly defer them with a target stage. No stakeholder interview is claimed.

1. **Product identity/lifecycle:** SKU renaming/reuse, other required product fields, character/length/display rules and create/edit rights; BR-001 fixes active-SKU uniqueness. BR-028 approves Manager reactivation and requires remaining stock resolution before deactivation, but the exact resolution workflow and ordinary-transaction boundary are open.
2. **Role and account policy:** remaining [Manager/Staff cells](ROLE_PERMISSION_MATRIX.md), CSV/settings access, account provisioning/reactivation, session revocation timing, assignment lifecycle and any administrator role; BR-003 and BR-026/BR-027 fix the specified actors and assignment limits.
3. **Stock history and validation:** quantity precision, manual duplicate requests, correction/retention policy and reliable dated stock-out records; BR-002/BR-003/BR-006 fix the stated invariants.
4. **CSV details and batch conflict:** encoding/BOM, whitespace, row shape/order/limits, duplicate identity/hashing/retention/concurrent upload safeguards and error format. The approved `sku,change` format cannot directly supply receiving-batch expiry or distinguish ordinary issue from disposal; determine how it coexists with BR-028/BR-029/BR-031–BR-033 without silently changing the format.
5. **Observation coverage:** decide how each day is reliably known complete, including verified zero days, and how evidence is retained. No-record days cannot silently count as zero; no schema/architecture is chosen here.
6. **Expiry and quarantine:** exact expiration boundary and timezone, no-expiry batch ordering and FEFO ties, quarantine implementation/release/disposal workflow, movement classification, and concurrency among receipt, issue, quarantine and deactivation. BR-029–BR-033 fix the stated behavior but not these mechanisms.
7. **Reorder choices:** definition of available-to-issue beyond excluding quarantine, inventory on order, trigger/display semantics, safety-stock constraints, minimum/pack size and other supplier settings. BR-010/BR-011/BR-030 fix lead-time units, formula and quarantined-stock exclusion.
8. **Nonfunctional targets:** approve/revise proposed 2s/3s p95 warm-response targets and test dataset/load; decide staging availability expectation, backup/restore/retention and security/accessibility expectations. Numeric values not approved remain TBD.
9. **Scope and feasibility response:** confirm that the fixed deadline and scope remain unchanged while tracking the 44–54h estimate; if forecasts exceed available hours, decide whether to request schedule change control or submit a formal scope change. Verify a zero-cost PostgreSQL CI/staging path before Design exit; no provider is selected.

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
- [ ] Owner resolves or explicitly defers the remaining decision packages above.
- [ ] Remaining Manager/Staff cells are approved and traced; BR-003 and BR-026–BR-028 approve only their stated actions.
- [ ] Remaining business-rule details are approved or explicitly deferred; BR-001–BR-011 and BR-026–BR-033 are recorded.
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
- [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md)
- [P1 Gate Record](../planning/PLANNING_GATE_P1.md)
- [Owner Decisions](../planning/OWNER_DECISIONS.md)
- [Feasibility Assessment](../planning/FEASIBILITY_ASSESSMENT.md) and [Project Schedule](../planning/PROJECT_SCHEDULE.md)
- [ADR-001](../decisions/ADR-001-backend-and-database.md), [Technology Evaluation](../TECHNOLOGY_EVALUATION.md), and [PoC evidence](../POC_RESULTS.md)
