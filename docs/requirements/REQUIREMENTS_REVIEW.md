# Tory Requirements Review

**Review status:** Draft review complete; SRS **PENDING OWNER APPROVAL**.  
**Requirements exit:** **NOT APPROVED**.  
**Target window:** 31 October–5 November 2026, subject to tracked schedule risk.  
**P1:** Planning exit approved with conditions; Requirements entry authorized 29 October 2026.

## 1. Review summary

The draft SRS is aligned to the approved Charter, P1 conditions and ADR-001. It covers all fixed baseline capabilities and keeps proposed detail separate from approved scope. It does not select a frontend, hosting provider, application architecture or CI vendor. No implementation, test completion, stakeholder interview, market study, or zero-cost provider eligibility is claimed.

Jira and a separate `tory-inventory` GitHub repository are desired work-management changes. Neither is verified as configured or required to approve a product behavior in this SRS; repository migration, if pursued, needs a separate recorded decision.

Completeness is **partial pending owner decisions**. [BR-001–BR-033](OWNER_REQUIREMENTS_DECISIONS.md) are individually approved: BR-001–BR-011 have the 29 October 2026 decision date, BR-012–BR-025 are supplementary owner-provided ChatGPT Requirements review approvals documented/reconciled 1 November 2026 without a supplied original approval timestamp, and BR-026–BR-033 have the 1 November decision date. BR-034 onward remain unapproved. Stock-out demand is not validated customer sales. Trustworthy daily coverage and dated movement evidence remain essential; their mechanism, retention and architecture remain undecided.

## 2. Completeness, consistency and testability review

| Review area | Status | Finding |
|---|---|---|
| Fixed scope coverage | Pass | Manual stock movements, atomic stock-transaction CSV, PostgreSQL, distinct roles, per-product settings, seven-day average, recommendation, staging and CI are represented. Product catalog import and unapproved features remain excluded. |
| Approved decisions | Pass | Django 5.2 LTS + PostgreSQL follows ADR-001; exact deployment versions/providers remain TBD. P1 authorized Requirements entry with conditions only. |
| Functional completeness | Needs owner decisions | BR-001–BR-033 approved individually. Shared business catalogue/separate inventories, inventory-specific prices, whole-base-unit stock and the listed role actions are fixed. SKU reuse interpretation, exact product stock resolution, batch ordering, history/coverage and account mechanics remain open. |
| Correctness / data integrity | Needs owner decisions | No-negative, adjustment, CSV atomicity/duplicate rejection, product deactivation guard, quarantine and FEFO approved. Expiration boundary, CSV-versus-batch conflict, quarantine mechanism, duplicate identity/concurrency, manual retries and retention remain open. |
| Forecast testability | Partial | Prior seven complete Asia/Singapore days, verified zeros, missing-day unavailability, two-decimal display, full precision, threshold alert distinct from quantity, pending-delivery exclusion, available-to-issue input and quarantine/disposal demand exclusion approved. Trustworthy observation coverage and movement classification remain unproven and need a Design solution. |
| Security / RBAC | Needs mechanics | BR-021–BR-025 fix listed permissions, assigned-inventory scope, Manager/Staff provisioning and history viewing; BR-026/BR-027 add deactivation and constrained assignment. Invitation/authentication, session revocation and unlisted actions remain TBD. |
| Nonfunctional testability | Partial | Numeric response targets are proposed, but dataset and concurrency profile are TBD. Availability, recovery objectives, browser/accessibility criteria and retention have no approved targets. |
| Zero-cost feasibility | Open risk | GitHub Actions, Render and Supabase remain candidates. Eligibility, quotas, payment/overage safeguards, PostgreSQL connectivity, external egress and recovery limits are unverified. |
| Test evidence | Open evidence gap | Source PoC reports record 14/14 passing; PoC source reviewed there had 15 test methods; the later 16/16 result is owner-reported and lacks a matching artifact/source revision. None is formal Tory Testing. |
| Schedule/capacity | High risk | Deadline is 27 November 2026; capacity 10–15 hours/week. Planning estimates 44–54 remaining hours including contingency versus 43–64 theoretical hours. Target Requirements window is compressed and all downstream stages must follow sequentially. |
| Stage boundaries | Pass | SRS and proposed criteria are Requirements work; architecture and schema details are deferred to Design; no implementation or formal Testing is claimed. |

## 3. Approved rules and remaining owner decisions

The owner approved [BR-001–BR-033](OWNER_REQUIREMENTS_DECISIONS.md); BR-012–BR-025 are supplementary owner-provided approvals documented/reconciled on 1 November 2026, with no original approval timestamp supplied. These approvals do not approve the complete SRS or Requirements exit. The following interpretations and mechanics remain open; the owner may resolve or explicitly defer them with a target stage. No stakeholder interview is claimed.

1. **Product identity/lifecycle:** BR-001 says case-insensitive uniqueness among active products; BR-017 says within a business. Whether inactive SKU reuse is allowed needs an explicit interpretation. SKU renaming, characters/length/display, inventory-specific selling-price format/maintenance, catalogue-level authorization and the exact remaining-stock resolution/ordinary-transaction boundary before soft deactivation also remain open. BR-021 fixes Manager create/edit/deactivate; BR-028 fixes Manager reactivation.
2. **Role and account mechanics:** [Manager/Staff cells](ROLE_PERMISSION_MATRIX.md) named in BR-021–BR-025 are approved, including assigned-inventory history viewing. Initial Manager setup and Manager Staff invite/create are approved (BR-023), but invitation/authentication, account reactivation, session revocation, assignment lifecycle, initial Manager inventory assignments and unlisted administrator actions remain TBD. BR-027 does not expand viewing beyond BR-022.
3. **Stock history and validation:** BR-020 fixes whole-number base units; packaging conversion, maximum values, manual duplicate requests, history view fields, correction/retention policy and reliable dated stock-out records remain open.
4. **CSV details and inventory/batch conflict:** encoding/BOM, whitespace, row shape/order/limits, duplicate identity/hashing/retention/concurrent upload safeguards and error format. The approved `sku,change` format cannot itself select among separate inventories, supply receiving-batch expiry or distinguish ordinary issue from disposal; determine how it coexists with BR-016/BR-022/BR-028/BR-029/BR-031–BR-033 without silently changing the format.
5. **Observation coverage:** decide how each day is reliably known complete, including verified zero days, and how evidence is retained. No-record days cannot silently count as zero; no schema/architecture is chosen here.
6. **Expiry and quarantine:** exact expiration boundary and timezone, no-expiry batch ordering and FEFO ties, quarantine implementation/release/disposal workflow, movement classification, and concurrency among receipt, issue, quarantine and deactivation. BR-029–BR-033 fix the stated behavior but not these mechanisms.
7. **Reorder interpretation:** BR-012 fixes the at-or-below alert even when suggested quantity is zero, BR-013 excludes pending deliveries, BR-014 limits MVP settings to lead time and safety stock, BR-015 allows nonnegative whole safety stock including zero, and BR-030 excludes quarantine from available-to-issue. Exact alert presentation when inputs are unavailable and treatment of other potential stock holds remain TBD; minimum quantities and pack sizes are outside MVP.
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
- [ ] Approved Manager/Staff cells are traced; remaining unlisted actions and account/assignment mechanics are resolved or explicitly deferred. BR-021–BR-027 fix only their stated permissions and constraints.
- [ ] Remaining business-rule interpretations are resolved or explicitly deferred; BR-001–BR-033 are recorded with their respective evidence/date distinctions.
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
