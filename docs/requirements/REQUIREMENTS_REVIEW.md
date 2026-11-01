# Tory Requirements Review

**Review status:** Draft review complete; SRS **PENDING OWNER APPROVAL**.  
**Requirements exit:** **NOT APPROVED**.  
**Target window:** 31 October–5 November 2026, subject to tracked schedule risk.  
**P1:** Planning exit approved with conditions; Requirements entry authorized 29 October 2026.

## 1. Review summary

The draft SRS is aligned to the approved Charter, P1 conditions and ADR-001. It covers all fixed baseline capabilities and keeps proposed detail separate from approved scope. It does not select a frontend, hosting provider or application architecture. The owner has now selected GitHub Actions for the NFR-010 pull-request test gate, refining the earlier Planning-stage CI-vendor TBD; workflow details and no-cost quota remain open. No implementation, test completion, stakeholder interview, market study, or zero-cost provider eligibility is claimed.

Jira and a separate `tory-inventory` GitHub repository are desired work-management changes. Neither is verified as configured or required to approve a product behavior in this SRS; repository migration, if pursued, needs a separate recorded decision.

Completeness is **partial pending owner decisions**. [BR-001–BR-045](OWNER_REQUIREMENTS_DECISIONS.md) are individually approved: BR-001–BR-011 have the 29 October 2026 decision date, BR-012–BR-025 are supplementary owner-provided ChatGPT Requirements review approvals documented/reconciled 1 November 2026 without a supplied original approval timestamp, and BR-026–BR-045 have the 1 November decision date. The owner separately approved G-01/G-02/G-09 Option A on 1 November 2026; these add no BR ID. BR-046 onward remain unapproved. Stock-out demand is not validated customer sales. Trustworthy daily coverage and dated movement evidence remain essential; their mechanism, retention and architecture remain undecided.

## 2. Completeness, consistency and testability review

| Review area | Status | Finding |
|---|---|---|
| Fixed scope coverage | Pass | Manual stock movements, atomic stock-transaction CSV, PostgreSQL, distinct roles, per-product settings, seven-day average, recommendation, staging and CI are represented. Product catalog import and unapproved features remain excluded. |
| Approved decisions | Pass | Django 5.2 LTS + PostgreSQL follows ADR-001. Six owner-approved nonfunctional decisions dated 1 November refine existing NFR IDs; GitHub Actions is selected for PR Django/PostgreSQL tests, while hosting provider and deployment versions remain TBD. P1 authorized Requirements entry only. |
| Functional completeness | Needs owner decisions | BR-001–BR-045 and G-01/G-02/G-09 Option A behaviours approved. Equal-expiry ordering is fixed; G-02 evidence-delay bound and G-09 separate rejected-attempt logging remain undecided. SKU rename/alias, remaining-stock resolution, daily coverage and delivery/timing mechanics also remain open. |
| Correctness / data integrity | Needs design/verification | Owner approved atomic **all** inventory transactions, nonnegative available stock, no double batch allocation, full invalid-CSV rollback, BR-041 duplicate prevention and the G-01/G-02/G-09 Option A ordering, quarantine and committed-event semantics. Transaction/locking design, batch-ID comparison, evidence-delay bound, separate rejected-attempt logging, audit schema/retention and concurrent test workload remain open. |
| Forecast testability | Partial | Prior seven complete Asia/Singapore days, verified zeros, missing-day unavailability, two-decimal display, full precision, threshold alert distinct from quantity, pending-delivery exclusion, available-to-issue input and quarantine/disposal demand exclusion approved. Trustworthy observation coverage and movement classification remain unproven and need a Design solution. |
| Security / RBAC | Needs mechanics | BR-021–BR-027 fix listed permissions and assignment boundaries; BR-037 limits disposal to Managers. BR-042–BR-045 fix Django email/password authentication, secure Manager Staff email invitation, single-use time-limited reset links, server sessions, HttpOnly cookies, HTTPS and CSRF. Email delivery, invite/reset duration, session timeout, rate limiting, deactivation invalidation mechanics and unlisted actions remain TBD. |
| Nonfunctional testability | Partial | p95 ≤2 s normal requests and ≤3 s forecast requests are approved (NFR-006); workload, dataset, concurrency and measurement boundaries TBD. Daily PostgreSQL backups and ≥1 successful pre-deployment restore are approved (NFR-008); destination, retention and recovery objectives TBD. |
| Zero-cost feasibility | Open risk | HTTPS Django/PostgreSQL staging is approved (NFR-009), but hosting/database/email/backup provider eligibility, quotas, payment/overage safeguards, connectivity and storage remain unverified at S$0. GitHub Actions is approved for PR CI, not proof its quota is sufficient. No hosting provider is selected. |
| Test evidence | Open evidence gap | Source PoC reports record 14/14 passing; PoC source reviewed there had 15 test methods; the later 16/16 result is owner-reported and lacks a matching artifact/source revision. None is formal Tory Testing. |
| Schedule/capacity | High risk | Deadline is 27 November 2026; capacity 10–15 hours/week. Planning estimates 44–54 remaining hours including contingency versus 43–64 theoretical hours. Target Requirements window is compressed and all downstream stages must follow sequentially. |
| Stage boundaries | Pass | SRS and proposed criteria are Requirements work; architecture and schema details are deferred to Design; no implementation or formal Testing is claimed. |

## 3. Approved rules and remaining owner decisions

The owner approved [BR-001–BR-045](OWNER_REQUIREMENTS_DECISIONS.md); BR-012–BR-025 are supplementary owner-provided approvals documented/reconciled on 1 November 2026, with no original approval timestamp supplied; BR-034–BR-045 were approved on 1 November. These approvals do not approve the complete SRS or Requirements exit. The following interpretations and mechanics remain open; the owner may resolve or explicitly defer them with a target stage. No stakeholder interview is claimed.

1. **Product identity/lifecycle:** BR-038 permanently reserves a business SKU to its original product, including after deactivation, resolving cross-product inactive-SKU reuse. SKU renaming/alias behavior, characters/length/display, inventory-specific selling-price format/maintenance and catalogue-level authorization remain open. BR-040 requires zero physical stock, including quarantine, in every business inventory before deactivation; exact resolution workflow, cross-inventory consistency and ordinary-transaction classification remain TBD. BR-021 fixes Manager create/edit/deactivate; BR-028 fixes Manager reactivation.
2. **Role and account mechanics:** [Manager/Staff cells](ROLE_PERMISSION_MATRIX.md) named in BR-021–BR-025 are approved, including assigned-inventory history viewing. BR-042–BR-045 settle Django email/password authentication, secure Manager email invitation with invitee-set password, time-limited single-use reset links, server sessions, HttpOnly cookies, HTTPS and CSRF. Initial Manager credential setup, account reactivation, assignment lifecycle, initial Manager inventory assignments and unlisted administrator actions remain TBD. BR-027 does not expand viewing beyond BR-022.
3. **Authentication delivery and timing:** email delivery for invitations/resets, invite and reset token expiry durations, invitation token reuse/invalidity mechanics, session timeout and logout/deactivation invalidation mechanics, authentication rate limiting and free staging feasibility for HTTPS/email remain unresolved. Proposed acceptance cases reject wrong passwords, expired/reused invitation and reset links, invalid CSRF proof, ended/deactivated sessions and unauthorized inventory access; exact implementation and feedback need review.
4. **Stock history and validation:** BR-020 fixes whole-number base units; packaging conversion, maximum values, manual duplicate requests, history view fields, correction/retention policy and reliable dated stock-out records remain open.
5. **CSV details and batch handling:** BR-039 requires a Manager to select one authorized inventory before upload and scopes every row to it. BR-036 rejects positive `sku,change` rows for expiry-tracked products and routes those receipts to manual batch/expiry entry; negative issues use approved G-01 FEFO/FIFO tie ordering without changing the header. BR-041 fixes duplicate identity as exact file bytes of a prior success within the same inventory; semantically equivalent but byte-different records are not identical under this rule. G-09 requires linked committed row movements and full stock/audit rollback. The [draft G-03/G-04 CSV owner decision package](CSV_GAP_OWNER_DECISIONS.md) compares non-expiry positive-row receiving and a bounded CSV contract, including proposed limits. Encoding/BOM, whitespace, row shape/order/limits, byte-comparison/retention implementation, non-expiry-tracked positive-row batch handling, concurrent upload safeguards and error format remain open. **G-03 and G-04 remain blocking and PENDING OWNER DECISION.** CSV is not an approved disposal route.
6. **Observation coverage:** decide how each day is reliably known complete, including verified zero days, and how evidence is retained. No-record days cannot silently count as zero; no schema/architecture is chosen here.
7. **Expiry, quarantine and disposal:** BR-034 fixes dated FEFO followed by undated receiving-order FIFO; BR-035 fixes unavailability at 00:00 on the expiry date in Asia/Singapore; BR-037 fixes Manager-only reasoned disposal. The [batch-integrity owner decision package](BATCH_INTEGRITY_OWNER_DECISIONS.md) records owner-approved G-01/G-02/G-09 Option A on 1 November 2026. G-01 observable ties are resolved. G-02 derived eligibility, immediate displayed quarantine and physical-stock preservation are approved, but maximum evidence-recording delay remains blocking. G-09 committed audit semantics are approved, but separate rejected-attempt logging remains blocking. Release policy, disposal reason format, retention/correction and G-11 concurrency mechanisms remain open.
8. **Reorder interpretation:** BR-012 fixes the at-or-below alert even when suggested quantity is zero, BR-013 excludes pending deliveries, BR-014 limits MVP settings to lead time and safety stock, BR-015 allows nonnegative whole safety stock including zero, and BR-030 excludes quarantine from available-to-issue. Exact alert presentation when inputs are unavailable and treatment of other potential stock holds remain TBD; minimum quantities and pack sizes are outside MVP.
9. **Approved nonfunctional criteria, measurement still open:** NFR-006 fixes p95 ≤2 s normal and ≤3 s forecast response times; decide workload, dataset, concurrency, clock/boundaries and environment. NFR-003/NFR-011 fix atomicity and audit fields; decide transaction/locking design, audit retention/correction and representative concurrency cases. NFR-008 fixes daily PostgreSQL backups and a successful pre-deployment restore; decide destination, retention, recovery objectives and test environment. Staging availability and accessibility targets remain TBD.
10. **CI and staging feasibility:** NFR-010 selects GitHub Actions to run Django tests on PostgreSQL for pull requests and fail checks on failed tests; workflow details, quota and full gate set remain TBD. NFR-009 requires HTTPS-hosted Django/PostgreSQL staging at S$0; verify database connectivity, email delivery, backup storage, provider limits, payment/overage safeguards and no-cost eligibility before claiming feasibility. No hosting provider is selected. This later Requirements decision refines P1's earlier CI-vendor candidate status without approving Requirements exit.
11. **Scope and feasibility response:** confirm that the fixed deadline and scope remain unchanged while tracking the 44–54h estimate; if forecasts exceed available hours, decide whether to request schedule change control or submit a formal scope change. No scope reduction is implicit.

## 4. Planning conditions carried into Requirements

- Keep the approved scope and exclusions intact; no silent reduction to compensate for schedule risk.
- Treat the P1 date, 10–15 hours/week, 27 November deadline and SGD 0 cap as fixed unless formally changed.
- Track actual effort and gate slippage; escalate immediately if projected completion exceeds available hours.
- Do not accept provider candidates as viable until account eligibility, quotas, PostgreSQL connectivity and no-charge safeguards are verified.
- Keep risk scores provisional; P1 did not approve risk tolerances or contingency decisions.
- Preserve the test evidence distinction: 14 recorded, 15 test methods in the reviewed PoC source, 16/16 owner-reported but unverified. Do not claim formal Testing completion.

## 5. Requirements gate-readiness checklist

The [gap analysis](REQUIREMENTS_GAP_ANALYSIS.md) audits BR-001–BR-045, FR-001–FR-012 and NFR-001–NFR-011. It records **9 blocking, 8 conditional and 2 nonblocking open gaps**, with G-01 requirements behaviour resolved and Design verification still open. G-02 maximum evidence-recording delay and G-09 separate rejected-attempt logging need owner decisions or bounded deferrals; approved Option A does not by itself close them. Other suggested defaults remain proposals. The later 1 November NFR-010 decision selects GitHub Actions for PR Django/PostgreSQL tests; dated Planning and ADR language calling the CI provider a candidate is historical. SRS §2.2 should clarify that its excluded detailed pipeline choice is workflow design, not the approved CI service.

The [batch-integrity owner decision package](BATCH_INTEGRITY_OWNER_DECISIONS.md) records **owner-approved Option A for G-01, G-02 and G-09**, dated 1 November 2026, and proposed acceptance examples. G-01 behaviour is resolved; G-02 and G-09 retain the blocking parameters above. This does not approve the complete SRS or Requirements exit.

The [draft CSV owner decision package](CSV_GAP_OWNER_DECISIONS.md) presents alternatives and proposed acceptance examples for **G-03 and G-04**. Its 256 KiB/1,000-row candidate caps and parsing choices are **PROPOSED, NOT APPROVED**. Both gaps retain their blocking status; the open-gap count and Requirements gate status above do not change.

### Deterministic behavior and acceptance

- [ ] G-01–G-04: Verify approved tied FEFO/FIFO order in Design; owner disposition sets G-02 maximum evidence-recording delay and G-03/G-04 non-expiry positive CSV receiving and bounded `sku,change` contract. No additional CSV columns are assumed.
- [ ] G-05–G-06 and G-09: Deactivation has a permitted zero-stock resolution path or explicit guarded deferral; seven-day observation coverage is demonstrable; approved committed-event audit semantics are testable and owner disposes of separate rejected-attempt logging.
- [ ] G-07–G-08: Invitation/reset/session/rate policies and the p95 benchmark envelope have measurable criteria or explicit bounded deferrals.
- [ ] G-11–G-13, G-16–G-17: Concurrency, whole-unit/packaging boundary, assignment and catalogue scope, SKU/price/settings behavior, and available-to-issue/reorder inputs have recorded owner dispositions.

### Feasibility, traceability and stage control

- [ ] G-10/G-14/G-15: Owner acknowledges the S$0 feasibility risk; backup/restore, email, HTTPS Django/PostgreSQL staging and GitHub Actions PostgreSQL PR checks have evidence plans and named Design-exit decisions. No hosting provider is presumed viable.
- [ ] G-15: SRS pipeline wording is reconciled with approved GitHub Actions NFR-010 while preserving the older Planning/ADR records as dated history.
- [ ] G-18: Effort and 27 November gate forecast are reviewed against 10–15 hours/week; any schedule or scope change follows formal change control.
- [ ] G-19/G-20: Proposed usability/feedback criteria are explicitly accepted or deferred, and PoC 14/15/16 evidence remains accurately labelled.
- [ ] Each gap disposition, especially any deferral of a blocking item, names the responsible role, target stage, required verification evidence and owner acceptance. A suggested default alone closes nothing.

Requirements exit remains pending until all are completed and explicitly approved by the owner:

- [ ] All fixed baseline requirements remain covered with no unapproved scope additions.
- [ ] Owner resolves or explicitly defers the remaining decision packages above.
- [ ] Approved Manager/Staff cells are traced; remaining unlisted actions and account/assignment mechanics are resolved or explicitly deferred. BR-021–BR-027 fix only their stated permissions and constraints.
- [ ] Remaining business-rule interpretations are resolved or explicitly deferred; BR-001–BR-045 are recorded with their respective evidence/date distinctions.
- [ ] Each approved Must requirement has deterministic acceptance criteria and a traceability entry.
- [ ] Approved p95 thresholds are paired with owner-disposed workload/dataset/measurement parameters; audit, backup/restore, CI and staging verification plans are testable and feasible.
- [ ] Scope, zero-cost constraint and schedule risk are reconciled; GitHub Actions quota and HTTPS staging/database/email/backup feasibility are evidenced, with no hosting-provider assumption.
- [ ] Owner approves the SRS revision and records Requirements exit / Design entry separately.

**Current decision: Requirements exit PENDING OWNER APPROVAL.**

## 6. Review and evidence references

- [SRS](SOFTWARE_REQUIREMENTS_SPECIFICATION.md)
- [Draft CSV Gap Owner Decisions](CSV_GAP_OWNER_DECISIONS.md)
- [Draft Batch Integrity Owner Decisions](BATCH_INTEGRITY_OWNER_DECISIONS.md)
- [Role Permission Matrix](ROLE_PERMISSION_MATRIX.md)
- [Business Rules and Edge Cases](BUSINESS_RULES_AND_EDGE_CASES.md)
- [Traceability Matrix](REQUIREMENTS_TRACEABILITY_MATRIX.md)
- [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md)
- [P1 Gate Record](../planning/PLANNING_GATE_P1.md)
- [Owner Decisions](../planning/OWNER_DECISIONS.md)
- [Feasibility Assessment](../planning/FEASIBILITY_ASSESSMENT.md) and [Project Schedule](../planning/PROJECT_SCHEDULE.md)
- [ADR-001](../decisions/ADR-001-backend-and-database.md), [Technology Evaluation](../TECHNOLOGY_EVALUATION.md), and [PoC evidence](../POC_RESULTS.md)
