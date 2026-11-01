# Tory Requirements Traceability Matrix

**Status:** Draft; acceptance tests and later evidence are placeholders. No implementation or formal tests are claimed complete.

## Charter objective keys

These keys restate the approved Charter objectives for traceability; they do not add scope.

| Key | Approved Charter objective |
|---|---|
| O-01 | Manual stock-in, stock-out and adjustment operations |
| O-02 | Atomic CSV stock-transaction import; no product catalog import |
| O-03 | PostgreSQL persistence |
| O-04 | Manager and Staff with distinct permissions |
| O-05 | Per-product supplier lead time, safety stock and reorder settings |
| O-06 | Explainable seven-day moving-average forecast and reorder recommendation |
| O-07 | Hosted staging demonstration and automated CI; CD optional |

## Functional traceability

| Requirement | Status / priority | Charter objective | Proposed acceptance-test reference | Design evidence placeholder | Build evidence placeholder | Formal test evidence placeholder |
|---|---|---|---|---|---|---|
| FR-001 Identify/select product | BR-001, BR-016–BR-019, BR-021, BR-028 approved; SKU reuse/resolution TBD / Must-support | O-01, O-04, O-05 | AT-FR001: business-scoped SKU; shared catalogue/separate inventories and prices; Manager create/edit/deactivate/reactivate; soft history retention and stock-resolution guard | TBD — data/interface design | TBD — implementation link/revision | TBD — result, environment, source revision |
| FR-002 View current inventory/history | BR-016, BR-018, BR-021–BR-022, BR-024 approved; view details TBD / Must-support | O-01, O-04 | AT-FR002: both roles view assigned same-business inventory and its history; unassigned/cross-business denied; same product may have inventory-specific prices | TBD | TBD | TBD |
| FR-003 Record stock-in | BR-020–BR-022, BR-028, BR-032 approved / Must | O-01, O-03, O-04 | AT-FR003: whole-base-unit addition/atomicity; receiving-batch expiry recorded when tracked, optional otherwise; unassigned/inactive denied | TBD | TBD | TBD |
| FR-004 Record stock-out | BR-002, BR-006, BR-020–BR-022, BR-028–BR-029, BR-031, BR-033 approved / Must | O-01, O-03, O-04, O-06 | AT-FR004: whole-base-unit issue; insufficient eligible stock rejected; expired quarantine unavailable; FEFO; unassigned/inactive denied; ordinary issue demand, disposal excluded | TBD | TBD | TBD |
| FR-005 Record adjustment | BR-003, BR-006, BR-020–BR-022 approved / Must | O-01, O-03, O-04 | AT-FR005: Manager whole-base-unit count/reason/difference in assigned inventory; Staff denied; adjustment excluded from demand | TBD | TBD | TBD |
| FR-006 Atomic CSV stock transaction import | BR-002, BR-004–BR-006, BR-016, BR-020–BR-022, BR-028–BR-029, BR-031–BR-033 approved; CSV/inventory/batch interface TBD / Must | O-02, O-03, O-04, O-06 | AT-FR006: Manager-only assigned-inventory `sku,change` whole-unit rollback/duplicate; inactive/quarantined issue denied; ordinary negative issue demand; target inventory and batch expiry/disposal/FEFO mapping TBD | TBD | TBD | TBD |
| FR-007 Authentication/role distinction | BR-003, BR-019, BR-021–BR-027 approved; mechanics TBD / Must | O-04 | AT-FR007: approved role cells; initial Manager setup; Manager Staff invite/create/deactivate; history access/attribution; same-business assignment and access limits | TBD | TBD | TBD |
| FR-008 Per-product supplier/reorder settings | BR-010, BR-014–BR-015, BR-025 approved / Must | O-05, O-06 | AT-FR008: positive whole-day lead time, nonnegative whole safety stock including zero; Manager edit/Staff view; advanced settings absent | TBD | TBD | TBD |
| FR-009 Eligible demand observations | BR-006–BR-008, BR-031 approved; coverage/classification TBD / Must-support | O-06 | AT-FR009: dated ordinary issues, quarantine/disposal excluded, verified zeros, missing coverage and Singapore boundaries | TBD | TBD | TBD |
| FR-010 Explainable 7-day average | BR-006–BR-009, BR-021–BR-022, BR-031 approved / Must | O-04, O-06 | AT-FR010: both roles view only assigned same-business forecast; verified `[1,0,1,0,1,0,0]` gives `0.43`; quarantine/disposal excluded; missing day unavailable | TBD | TBD | TBD |
| FR-011 Reorder recommendation | BR-008–BR-015, BR-021–BR-022, BR-030 approved / Must | O-04, O-05, O-06 | AT-FR011: threshold alert including zero suggestion at equality; pending deliveries ignored; full precision; nonnegative whole safety stock; quarantine excluded; both roles assigned-scope view; no order | TBD | TBD | TBD |
| FR-012 Validation feedback | Proposed detail / Should | O-01, O-02, O-06 | AT-FR012: actionable errors without partial commits or sensitive detail | TBD | TBD | TBD |

## Nonfunctional traceability

| Requirement | Group / status | Charter objective | Proposed verification | Design evidence placeholder | Build evidence placeholder | Formal test evidence placeholder |
|---|---|---|---|---|---|---|
| NFR-001 Server-side authorization | Security / BR-021–BR-027 approved; unlisted actions TBD | O-04 | AT-NFR001: both roles restricted to assigned own-business inventories; approved role cells enforced; revoked Staff access/retained attribution; cross-business/out-of-scope assignment denied | TBD | TBD | TBD |
| NFR-002 Credential/secret handling | Security / proposed, some criteria TBD | O-04, O-07 | Security review: no committed secrets; staging transport/config check | TBD | TBD | TBD |
| NFR-003 Transaction integrity | Correctness / BR-002–BR-005, BR-019–BR-020, BR-028–BR-029, BR-032–BR-033 approved; safeguards TBD | O-01, O-02, O-03 | PostgreSQL whole-base-unit stock-out, adjustment, CSV rollback/duplicate, soft deactivation/history, quarantine, receiving-batch expiry and concurrent FEFO | TBD | TBD | TBD |
| NFR-004 Forecast reproducibility | Correctness / BR-007–BR-015, BR-030–BR-031 approved | O-06 | Fixed Singapore dates, verified zero/missing day, quarantine/disposal excluded, pending deliveries ignored, threshold alert distinct from suggestion, full precision | TBD | TBD | TBD |
| NFR-005 Understandable outcomes | Usability / proposed | O-01, O-02, O-06 | Scenario walkthrough/usability review; method TBD | TBD | TBD | TBD |
| NFR-006 Response-time targets | Performance / proposed numeric targets | O-01, O-06 | Warm staging p95 measurement on approved dataset/load | TBD | TBD | TBD |
| NFR-007 Versioned schema changes/review | Maintainability / proposed | O-03 | Migration-from-clean-database and review checklist | TBD | TBD | TBD |
| NFR-008 Failure recovery | Reliability / TBD targets | O-02, O-03, O-07 | Restore/reseed exercise after recovery policy approved | TBD | TBD | TBD |
| NFR-009 Zero-cost hosted staging | Deployment / confirmed constraint; provider TBD | O-03, O-07 | Account/quota/billing/connectivity verification and demo | TBD | TBD | TBD |
| NFR-010 Automated CI on PostgreSQL | Deployment / confirmed baseline; provider TBD | O-03, O-07 | CI job applies migrations and runs approved tests on PostgreSQL | TBD | TBD | TBD |
| NFR-011 Requirement testability/traceability | Testability / proposed process | O-01–O-07 | Review each approved Must requirement for assigned deterministic acceptance test | TBD | TBD | TBD |

## Evidence status

All design/build/test evidence cells are **TBD**. The historical PoC evidence is listed in PoC reports and ADR-001; it is not evidence that these Tory requirements are implemented or formally tested. The 14/15/16 test discrepancy remains as documented in [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) and must not be collapsed into a single verified result.

BR-001–BR-033 are recorded in [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md). BR-012–BR-025 have a 1 November 2026 documentation/reconciliation date and no supplied original approval timestamp; BR-034 onward have no approval recorded. The acceptance cases above and in [Business Rules](BUSINESS_RULES_AND_EDGE_CASES.md#edge-case-acceptance-examples-to-approve) are plans, not completed tests.
