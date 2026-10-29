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
| FR-001 Identify/select product | Proposed detail / Must-support | O-01, O-05 | AT-FR001: product identity/current quantity retrieval and unknown product handling | TBD — data/interface design | TBD — implementation link/revision | TBD — result, environment, source revision |
| FR-002 View current inventory | Proposed detail / Must-support | O-01 | AT-FR002: authorized current quantity and denied access | TBD | TBD | TBD |
| FR-003 Record stock-in | Confirmed capability / Must | O-01, O-03 | AT-FR003: valid addition, invalid quantity, failure atomicity | TBD | TBD | TBD |
| FR-004 Record stock-out | Confirmed capability / Must | O-01, O-03, O-06 | AT-FR004: valid depletion, insufficient stock proposal, concurrency and demand classification | TBD | TBD | TBD |
| FR-005 Record adjustment | Confirmed capability / Must | O-01, O-03 | AT-FR005: approved adjustment semantics, permissions and rollback | TBD | TBD | TBD |
| FR-006 Atomic CSV stock transaction import | Confirmed capability / Must | O-02, O-03 | AT-FR006: all-valid commit; invalid row at each position causes zero batch changes; catalog rows excluded | TBD | TBD | TBD |
| FR-007 Authentication/role distinction | Role distinction confirmed; details proposed / Must | O-04 | AT-FR007: Manager and Staff allow/deny test for each approved matrix action | TBD | TBD | TBD |
| FR-008 Per-product supplier/reorder settings | Confirmed capability / Must | O-05, O-06 | AT-FR008: persistence, validation and product isolation | TBD | TBD | TBD |
| FR-009 Eligible demand observations | Proposed/TBD / Must-support | O-06 | AT-FR009: approved demand source and complete/incomplete windows | TBD | TBD | TBD |
| FR-010 Explainable 7-day average | Confirmed capability; details proposed / Must | O-06 | AT-FR010: known seven-day series, zeros, missing data, boundary and rounding | TBD | TBD | TBD |
| FR-011 Reorder recommendation | Confirmed capability; formula proposed / Must | O-05, O-06 | AT-FR011: known lead time, safety stock, on-hand and approved formula | TBD | TBD | TBD |
| FR-012 Validation feedback | Proposed detail / Should | O-01, O-02, O-06 | AT-FR012: actionable errors without partial commits or sensitive detail | TBD | TBD | TBD |

## Nonfunctional traceability

| Requirement | Group / status | Charter objective | Proposed verification | Design evidence placeholder | Build evidence placeholder | Formal test evidence placeholder |
|---|---|---|---|---|---|---|
| NFR-001 Server-side authorization | Security / proposed detail | O-04 | AT-NFR001: deny unpermitted operations at server boundary | TBD | TBD | TBD |
| NFR-002 Credential/secret handling | Security / proposed, some criteria TBD | O-04, O-07 | Security review: no committed secrets; staging transport/config check | TBD | TBD | TBD |
| NFR-003 Transaction integrity | Correctness / proposed detail | O-01, O-02, O-03 | PostgreSQL rollback, constraint and concurrency cases | TBD | TBD | TBD |
| NFR-004 Forecast reproducibility | Correctness / proposed detail | O-06 | Fixed input/output reference cases and explanation check | TBD | TBD | TBD |
| NFR-005 Understandable outcomes | Usability / proposed | O-01, O-02, O-06 | Scenario walkthrough/usability review; method TBD | TBD | TBD | TBD |
| NFR-006 Response-time targets | Performance / proposed numeric targets | O-01, O-06 | Warm staging p95 measurement on approved dataset/load | TBD | TBD | TBD |
| NFR-007 Versioned schema changes/review | Maintainability / proposed | O-03 | Migration-from-clean-database and review checklist | TBD | TBD | TBD |
| NFR-008 Failure recovery | Reliability / TBD targets | O-02, O-03, O-07 | Restore/reseed exercise after recovery policy approved | TBD | TBD | TBD |
| NFR-009 Zero-cost hosted staging | Deployment / confirmed constraint; provider TBD | O-03, O-07 | Account/quota/billing/connectivity verification and demo | TBD | TBD | TBD |
| NFR-010 Automated CI on PostgreSQL | Deployment / confirmed baseline; provider TBD | O-03, O-07 | CI job applies migrations and runs approved tests on PostgreSQL | TBD | TBD | TBD |
| NFR-011 Requirement testability/traceability | Testability / proposed process | O-01–O-07 | Review each approved Must requirement for assigned deterministic acceptance test | TBD | TBD | TBD |

## Evidence status

All design/build/test evidence cells are **TBD**. The historical PoC evidence is listed in PoC reports and ADR-001; it is not evidence that these Tory requirements are implemented or formally tested. The 14/15/16 test discrepancy remains as documented in [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) and must not be collapsed into a single verified result.
