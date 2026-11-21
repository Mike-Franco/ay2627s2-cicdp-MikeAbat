# TORY-46 login throttle reservations

**Decision date:** 21 November 2026
**Issue:** TORY-46 (follows the [TORY-26 login latency design review](TORY-26-login-latency-design-review.md))
**Scope:** `accounts/throttle.py`, `config/settings.py`, `tests/test_auth.py`, `scripts/tory46_login_benchmark.py`, `benchmark-results/tory46-login-*.json`

## Problem

`check_and_authenticate` held both transaction-scoped advisory locks (identity and source IP) while Django hashed the password. Concurrent sign-ins sharing a key therefore ran one at a time. Five browsers behind one IP took roughly five password checks end to end.

## Decision

Reserve the attempt before hashing, then release the locks:

1. In a short transaction, take both advisory locks in sorted order and count rolling-window `LoginFailure` rows for each key. If either limit is reached, deny. Otherwise insert one `LoginFailure` row carrying both keys, the reservation, and commit. This releases the locks.
2. Run `authenticate` / `check_password` with no lock held.
3. On success, delete only that reservation row. On a wrong password the row stays, and it is the recorded failure.

The TORY-26 review set requirements for a reservation design. This design meets them as follows:

| Requirement in the TORY-26 review | How this design meets it |
| --- | --- |
| Atomic acquisition for both keys, no partial reservation | One row holds both keys and is inserted while both locks are held. |
| Concurrent wrong passwords must not exceed either cap | In-flight reservations count as failures. Six simultaneous wrong passwords still record exactly five (`test_competing_failures_share_postgresql_limit`). |
| Bound expensive in-flight hashing | At most 5 hashes per identity and 20 per IP can be in flight, because each needs a slot. |
| Crash recovery without a lease | Fails closed. A crash or error during the check leaves the reservation counted as a failure until the normal 15-minute window passes (`test_error_during_password_check_stays_counted`). Previously such an attempt rolled back and was not counted. |
| Success must not erase failure history | Success deletes only its own row (`test_success_removes_only_its_own_reservation`). |
| Unknown or inactive identities keep equivalent timing | Unchanged. Django's `authenticate` still runs the hasher for unknown users. |

**Accepted trade-off:** an in-flight successful attempt occupies a slot until it finishes. A user with four failures in the window who submits two correct passwords at the same moment may see the second denied (`test_in_flight_attempt_counts_towards_limit_until_it_succeeds`). Previously both would have queued and succeeded.

The inclusive limits (5 per identity, 20 per IP, 15-minute rolling window), HMAC key derivation, generic error messages and password hasher iterations are unchanged.

`CONN_MAX_AGE = 60` with `CONN_HEALTH_CHECKS = True` lets each gunicorn worker reuse its database connection. Advisory locks are transaction-scoped, so a reused connection never carries one over.

## Benchmark

[`scripts/tory46_login_benchmark.py`](../../scripts/tory46_login_benchmark.py) ran against the TORY-37 Docker stack (gunicorn sync workers, `WEB_CONCURRENCY=5`, PostgreSQL 18.3; the Docker VM had 12 CPUs; client on the Windows 11 host). Each timed POST is a fresh browser session. All five clients share one source IP, the contended throttle key. Both runs used the same settings and the Django default PBKDF2 hasher.

| Run | Sequential median | 5 concurrent, same IP: median | p95 | max | Round wall-time median |
| --- | --- | --- | --- | --- | --- |
| Before (`develop` at `77888cc`) | 1.049 s | 3.266 s | 5.820 s | 6.647 s | 5.935 s |
| After (TORY-46 on `870c496`) | 1.086 s | **2.013 s** | **2.613 s** | 2.688 s | **2.803 s** |

Raw data: [`tory46-login-before.json`](../../benchmark-results/tory46-login-before.json) and [`tory46-login-after.json`](../../benchmark-results/tory46-login-after.json).

Concurrent sign-in no longer queues behind one lock: p95 fell 55% and round time 53%. The concurrent median is still above the sequential one because the hashing itself contends for CPU. Inside the same container, one `check_password` took a median 1.196 s alone, 1.270 s with two in parallel, and 1.897 s with five in parallel (separate processes, no database). The post-change concurrent median, 2.013 s, is that 1.897 s plus request overhead. The remaining gap is hardware contention on this laptop, not locking.

These are local measurements on one uncontrolled developer machine. They show the lock wait is gone. They do not establish TORY-26's 2-second p95 target on staging hardware; re-measure there.
