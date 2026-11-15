# Tory Agile Iteration Log

**Cadence decision:** Prospective sprint-style timeboxes from 12 November 2026, within the Agile Kanban method adopted on 3 November 2026. The original 29 October Waterfall Planning baseline remains historical evidence.

**Timezone:** Asia/Singapore

**Constraints:** One developer, 10–15 hours/week, SGD 0 cash budget, one item In Progress at a time, approved scope unchanged.

**Deadline:** 27 November 2026 at 17:00 Asia/Singapore.

## Record and evidence rules

The [TORY Jira board](https://mikefrancoabat.atlassian.net/jira/software/projects/TORY/boards/34) tracks **To Do → In Progress → Review/Test → Done**. Its current simple-board configuration does not expose native sprint assignment or sprint reporting. Jira is authoritative for current issue states and linked PR/test evidence. This log records cycle goals, dates, blockers, actual reviews and retrospectives; update results only after the activities occur. A cycle goal is a plan, not a claim of delivery or acceptance. Preserve requirement decisions and historical approvals in their original records.

As checked on 12 November 2026, [TORY-14](https://mikefrancoabat.atlassian.net/browse/TORY-14) is **Done** after merged PR #36. [TORY-33](https://mikefrancoabat.atlassian.net/browse/TORY-33) is **Review/Test** after merged PR #37; its manual browser checklist is pending. [TORY-19](https://mikefrancoabat.atlassian.net/browse/TORY-19) is **Review/Test**, pending staging verification of the approved one-hour expiry-quarantine evidence limit. These are point-in-time states; check Jira before relying on them later.

## Pre-sprint Kanban evidence

These PRs were completed under Kanban delivery before the new cadence was recorded. They are **not Sprint 1 results**. Dates below are merge dates in Asia/Singapore; PR #37 merged on 12 November before this prospective cadence record.

| Merged PR | Merge date | Delivery evidence |
|---|---|---|
| [#34](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/pull/34) | 9 November 2026 | TORY-23 seven-day demand forecasting with verified complete days and PostgreSQL commit-time handling. |
| [#35](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/pull/35) | 9 November 2026 | TORY-24 shared reorder settings and expiry-aware recommendations. |
| [#36](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/pull/36) | 11 November 2026 | TORY-14 Manager product deactivation/reactivation with cross-inventory physical-zero guard and audit trail. Jira status: Done. |
| [#37](https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat/pull/37) | 12 November 2026 | TORY-33 Django workspace, sidebar, themes and stock navigation integration. Jira status: Review/Test; manual browser checklist remains pending. |

## Sprint 1 — 12–18 November 2026

**Goal:** Assess and establish the zero-cost staging, backup and restore path under [TORY-27](https://mikefrancoabat.atlassian.net/browse/TORY-27). If staging is available, complete [TORY-19](https://mikefrancoabat.atlassian.net/browse/TORY-19)'s staging evidence that one system-attributed expiry-quarantine event is recorded within one hour of the Asia/Singapore midnight boundary, while expired stock becomes unavailable immediately.

**Planned evidence:** Record no-cost provider/account/quota and PostgreSQL suitability, deployment/security and backup/restore test results if feasible. For TORY-19, record actual staging scheduler timing, effective and recording timestamps, absence of duplicate events and applicable test/PR links. Do not mark either outcome complete without evidence.

**Visible blockers:** Provider and account eligibility, payment-method/quota rules, secrets/HTTPS and PostgreSQL access, reliable scheduling, backup storage and restore viability are unverified. If staging is unavailable, TORY-19's one-hour staging verification remains blocked. Escalate a no-cost feasibility failure and any capacity forecast miss; do not silently change scope or the SGD 0 ceiling.

**Actual review:** Pending — record completed work, evidence links, unresolved blockers and Sprint 2 replan after the review occurs.

**Retrospective:** Pending — record observations and an agreed process adjustment only after the retrospective occurs.

## Sprint 2 — provisional 19–25 November 2026

**Candidate work:** [TORY-26](https://mikefrancoabat.atlassian.net/browse/TORY-26) integrated accuracy, concurrency and performance; [TORY-28](https://mikefrancoabat.atlassian.net/browse/TORY-28) diagrams/framework evidence; [TORY-29](https://mikefrancoabat.atlassian.net/browse/TORY-29) individual CA1 report and critical evaluation; [TORY-30](https://mikefrancoabat.atlassian.net/browse/TORY-30) demo, package and submission preparation. These are candidates, not a commitment that all four fit. Their combined scope may exceed **10–15 hours/week**; replan priority, remaining effort and blockers at the Sprint 1 review. Performance evidence and any unresolved staging dependencies remain visible.

**Actual review:** Pending — confirm scope and results only after the review occurs.

**Retrospective:** Pending — record actual findings only after the retrospective occurs.

## Final reserve — 26–27 November 2026

Reserve this window for critical fixes, demo rehearsal, package verification and submission by **27 November 2026 at 17:00 Asia/Singapore**. The reserve is inside the existing deadline and capacity. Do not use it to imply that outstanding staging, performance or acceptance evidence has passed.
