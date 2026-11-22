# ADR-004: Guarded Backdating for the Demo Seed

**Decision date:** 21 November 2026
**Status:** Accepted by project owner, with two hardening conditions
**Issue:** TORY-39 (PR #62)
**Scope:** `seed_demo`, `receiving/services.py`, migration `receiving/0022_guard_demo_receipt_dates`, operations admin

## Context

TORY-39 requires a fresh local, Docker or staging database to show a numeric seven-day forecast immediately after `migrate` and `seed_demo`. A forecast needs seven complete, verified Asia/Singapore dates of attributed issues. The demand rules intentionally make this impossible to fake. Manual receipts and issues take the current time. The PostgreSQL receipt guard compares each receipt with `clock_timestamp()` in Singapore. Earlier or partial dates are never counted. The ticket also requires the seed to go through the existing receiving services, so audit and integrity rules still apply.

## Decision

Allow a narrow, demo-only backdating path:

- `receive_manual(..., demo_received_at=...)` and `issue_stock(..., demo_issued_at=...)` accept a past timestamp. That timestamp then sets the recorded movement time and the Singapore day used for expiry and FEFO eligibility. Every other service rule still runs, including authorization, locking, quantity limits, audit events, balances and sequences.
- `seed_demo` is the only caller. The web views and the CSV import never pass these arguments.
- Migration `0022` replaces the receipt-date trigger. It validates a receipt against the date it simulates only when all of the following hold:
  - the receipt is manual and the actor is a Manager;
  - the transaction-local setting `tory.demo_receipt_token` equals that receipt's request token (the service sets and clears it inside the same transaction);
  - the timestamp is in the past and no more than eight days old;
  - the inventory's business is named `Tory Demo`.

  Every other receipt still uses PostgreSQL's current Singapore date.

## Guards

| Guard | Where | Effect |
| --- | --- | --- |
| `DJANGO_ENV != "production"` | `_check_demo_movement` in `receiving/services.py`, and the `seed_demo` command | Backdated receipts and issues are rejected in production before any write. Tested in `tests/test_seed_demo.py` (`DemoBackdatingProductionGuardTests`), with a non-production control. |
| Business name `Tory Demo` | Service check and the PostgreSQL trigger | Limits the bypass to the demo business. |
| Name cannot be switched on through the admin | `BusinessAdmin` in `config/ops_admin.py` | The `Tory Demo` business's name is read-only. No business can be created as, or renamed to, `Tory Demo`, ignoring case and surrounding spaces. Tested in `tests/test_ops_admin.py`. |
| Per-receipt token | Transaction-local PostgreSQL setting | A backdated receipt is accepted only for the request token the service is committing in that transaction. |
| Eight-day window, past timestamps only | Service and trigger | Covers the seven verified days the seed needs. Future-dated receipts are never allowed. |

## Consequences and residual risk

- The demo business's forecasts come from synthetic history. They demonstrate the feature, not real demand.
- The production refusal lives in Python only. The trigger has no environment check, because PostgreSQL does not know `DJANGO_ENV`. Code that bypasses the services, or a direct SQL session that sets the token and a matching business name, could still create a backdated receipt. Creating a business named `Tory Demo` is now blocked in the admin, but not at the database layer. Operators should not create that business in production. `seed_demo` refuses to run there.
- Removing the feature later requires a migration that restores the `0015` trigger body, plus removal of the two service parameters.

## Rejected alternatives

1. **Wait seven real days.** Activate observation, issue stock daily, and let a Manager verify each completed date (the TORY-26 approach in `scripts/tory26_prepare_coverage.py`). This keeps every rule intact. It was rejected because a fresh Docker or staging environment must show numbers immediately, and the deadline is 27 November 2026 at 17:00 Asia/Singapore.
2. **Raw SQL inserts, or disabling the trigger while seeding.** This would avoid touching the services. It was rejected because it skips audit events, balances and sequence rules. It would also create history the application could never have produced, and TORY-39 explicitly requires the existing services.
3. **Mocking time in Python only.** This does not work: the receipt guard and the demand-attribution logic use PostgreSQL's `clock_timestamp()` and commit timestamps, not Django's clock.
