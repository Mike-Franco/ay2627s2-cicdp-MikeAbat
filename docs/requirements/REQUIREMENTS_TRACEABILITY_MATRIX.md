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
| FR-001 Identify/select product | BR-001, BR-016–BR-019, BR-021, BR-028, BR-038, BR-040 approved; rename/resolution workflow TBD / Must-support | O-01, O-04, O-05 | AT-FR001: inactive SKU cannot pass to another product in same business; shared catalogue/separate inventories; Manager deactivation denied while any business inventory has physical stock including quarantine; history retained | TBD — data/interface design | TBD — implementation link/revision | TBD — result, environment, source revision |
| FR-002 View current inventory/history | BR-016, BR-018, BR-021–BR-022, BR-024 approved; view details TBD / Must-support | O-01, O-04 | AT-FR002: both roles view assigned same-business inventory and its history; unassigned/cross-business denied; same product may have inventory-specific prices | TBD | TBD | TBD |
| FR-003 Record stock-in | BR-020–BR-022, BR-028, BR-032, BR-036 approved / Must | O-01, O-03, O-04 | AT-FR003: whole-base-unit addition/atomicity; expiry-tracked product received manually with batch/expiry details; optional expiry otherwise; unassigned/inactive denied | TBD | TBD | TBD |
| FR-004 Record stock-out | BR-002, BR-006, BR-020–BR-022, BR-028–BR-029, BR-031, BR-033–BR-035, BR-037, BR-040 approved / Must | O-01, O-03, O-04, O-06 | AT-FR004: dated FEFO then undated FIFO; Singapore midnight expiry cutoff; Manager-only reasoned disposal; quarantined physical units continue to block product deactivation until resolved | TBD | TBD | TBD |
| FR-005 Record adjustment | BR-003, BR-006, BR-020–BR-022 approved / Must | O-01, O-03, O-04 | AT-FR005: Manager whole-base-unit count/reason/difference in assigned inventory; Staff denied; adjustment excluded from demand | TBD | TBD | TBD |
| FR-006 Atomic CSV stock transaction import | BR-002, BR-004–BR-006, BR-016, BR-020–BR-022, BR-028–BR-029, BR-031–BR-036, BR-039, BR-041 approved; parsing/concurrency TBD / Must | O-02, O-03, O-04, O-06 | AT-FR006: Manager selects one authorized inventory before upload; every row applies there; exact-byte prior success rejected only in that inventory; expiry-tracked positive row rolls back batch; negative issue uses FEFO then undated FIFO | TBD | TBD | TBD |
| FR-007 Authentication/role distinction | BR-003, BR-019, BR-021–BR-027, BR-037, BR-039–BR-040, BR-042–BR-045 approved; delivery/timing TBD / Must | O-04 | AT-FR007: Manager/Staff email-password login; wrong password denied; invitee sets own password with BR-027 scope; expired/reused invite/reset tokens denied; logout and deactivated-session access denied; unauthorized inventory denied | TBD | TBD | TBD |
| FR-008 Per-product supplier/reorder settings | BR-010, BR-014–BR-015, BR-025 approved / Must | O-05, O-06 | AT-FR008: positive whole-day lead time, nonnegative whole safety stock including zero; Manager edit/Staff view; advanced settings absent | TBD | TBD | TBD |
| FR-009 Eligible demand observations | BR-006–BR-008, BR-031, BR-037 approved; coverage/classification TBD / Must-support | O-06 | AT-FR009: dated ordinary issues, attributable Manager disposal and quarantine excluded, verified zeros, missing coverage and Singapore boundaries | TBD | TBD | TBD |
| FR-010 Explainable 7-day average | BR-006–BR-009, BR-021–BR-022, BR-031 approved / Must | O-04, O-06 | AT-FR010: both roles view only assigned same-business forecast; verified `[1,0,1,0,1,0,0]` gives `0.43`; quarantine/disposal excluded; missing day unavailable | TBD | TBD | TBD |
| FR-011 Reorder recommendation | BR-008–BR-015, BR-021–BR-022, BR-030 approved / Must | O-04, O-05, O-06 | AT-FR011: threshold alert including zero suggestion at equality; pending deliveries ignored; full precision; nonnegative whole safety stock; quarantine excluded; both roles assigned-scope view; no order | TBD | TBD | TBD |
| FR-012 Validation feedback | Proposed detail / Should | O-01, O-02, O-06 | AT-FR012: actionable errors without partial commits or sensitive detail | TBD | TBD | TBD |

## Nonfunctional traceability

| Requirement | Group / status | Charter objective | Proposed verification | Design evidence placeholder | Build evidence placeholder | Formal test evidence placeholder |
|---|---|---|---|---|---|---|
| NFR-001 Server-side authorization | Security / BR-021–BR-027, BR-037, BR-039, BR-042, BR-045 approved; unlisted actions TBD | O-04 | AT-NFR001: authenticated server session still limited to assigned own-business inventory; deactivated session and invalid-CSRF mutation denied; out-of-scope assignment/CSV selection denied | TBD | TBD | TBD |
| NFR-002 Credential/secret handling | Security / BR-042–BR-045 approved; delivery/timing/rate limits TBD | O-04, O-07 | AT-NFR002: wrong password denied; invitee-set password; expired/reused invite/reset links denied; logout; HttpOnly session cookie, HTTPS and CSRF checks; no committed/exposed secrets | TBD | TBD | TBD |
| NFR-003 Transaction integrity and audit | Correctness / owner-approved 1 Nov NFR decision; BR-002–BR-005, BR-019–BR-020, BR-028–BR-029, BR-032–BR-041 preserved | O-01, O-02, O-03, O-04 | AT-NFR003: PostgreSQL integration tests verify all-or-none inventory/audit mutation, nonnegative available balance, concurrent no-double-batch-allocation, invalid CSV full rollback, BR-041 same-inventory byte-duplicate rejection; audit fields and attribution survive account/product deactivation | TBD | TBD | TBD |
| NFR-004 Forecast reproducibility | Correctness / BR-007–BR-015, BR-030–BR-031, BR-037 approved | O-06 | Fixed Singapore dates, verified zero/missing day, attributable disposal/quarantine excluded, pending deliveries ignored, threshold alert distinct from suggestion, full precision | TBD | TBD | TBD |
| NFR-005 Understandable outcomes | Usability / proposed | O-01, O-02, O-06 | Scenario walkthrough/usability review; method TBD | TBD | TBD | TBD |
| NFR-006 Response-time targets | Performance / owner-approved 1 Nov thresholds; workload/boundaries TBD | O-01, O-06 | AT-NFR006: measure approved normal and forecast request workloads separately; compute p95 ≤ 2 s and ≤ 3 s respectively; record dataset, environment and measurement boundaries | TBD | TBD | TBD |
| NFR-007 Versioned schema changes/review | Maintainability / proposed | O-03 | Migration-from-clean-database and review checklist | TBD | TBD | TBD |
| NFR-008 Failure recovery | Reliability / owner-approved 1 Nov daily PostgreSQL backup and pre-deployment restore test; destination/RPO/RTO TBD | O-02, O-03, O-07 | AT-NFR008: inspect dated daily backup evidence; complete ≥1 successful isolated PostgreSQL restore before Deployment, verify representative stock/audit records and record result/environment | TBD | TBD | TBD |
| NFR-009 Zero-cost hosted staging | Deployment / owner-approved 1 Nov HTTPS Django/PostgreSQL demo, S$0 target; feasibility TBD | O-03, O-07 | AT-NFR009: demonstrate HTTPS-hosted Django app with PostgreSQL connectivity; verify email delivery and backup storage plus provider limits, quotas and no-charge safeguards before claiming feasibility | TBD | TBD | TBD |
| NFR-010 Automated CI on PostgreSQL | Deployment / owner-approved 1 Nov GitHub Actions PR test gate; details/quota TBD | O-03, O-07 | AT-NFR010: PR GitHub Actions run executes Django tests against PostgreSQL; passing run passes, controlled failing-test run fails CI check; retain run/revision evidence | TBD | TBD | TBD |
| NFR-011 Requirement testability/traceability | Testability / owner-approved 1 Nov audit traceability; other process detail proposed | O-01–O-07 | AT-NFR011: inspect representative audit records for actor, business/inventory, action, timestamp, quantity before/after or change and applicable reason; link to source action and verify attribution after deactivation | TBD | TBD | TBD |

## Evidence status

All design/build/test evidence cells are **TBD**. The historical PoC evidence is listed in PoC reports and ADR-001; it is not evidence that these Tory requirements are implemented or formally tested. The 14/15/16 test discrepancy remains as documented in [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) and must not be collapsed into a single verified result.

BR-001–BR-045 are recorded in [Owner Requirements Decisions](OWNER_REQUIREMENTS_DECISIONS.md). BR-012–BR-025 have a 1 November 2026 documentation/reconciliation date and no supplied original approval timestamp; BR-034–BR-045 were approved on 1 November. BR-046 onward have no approval recorded. The separate six owner-approved nonfunctional decisions dated 1 November map to existing NFR-003, NFR-006, NFR-008–NFR-011; their test references above are plans, not completed results. The acceptance cases in [Business Rules](BUSINESS_RULES_AND_EDGE_CASES.md#edge-case-acceptance-examples-to-approve) are likewise plans.
