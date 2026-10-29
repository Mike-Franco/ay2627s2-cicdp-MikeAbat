# Tory Feasibility Assessment

**Course:** Singapore Polytechnic ST0529 CA1  
**Planning baseline:** 29 October 2026  
**Status:** Updated for owner-confirmed deadline and capacity; provider eligibility and account checks remain outstanding.

## Executive assessment

**Assessment: marginal feasibility / high schedule risk.** From 29 October through 27 November 2026 there are 30 calendar days (about 4.29 weeks), giving an approximate capacity of **43–64 hours** at the confirmed 10–15 hours per week, assuming that capacity is available throughout. A rough remaining-work estimate is **40–49 hours plus 4–5 hours contingency (44–54 hours total)**. It fits only above the low end of the capacity range and leaves limited room for stage-gate delays, defects, course conflicts or account problems. At 10 hours per week the full approved scope is unlikely to fit; at 15 hours per week it is possible only if work is near the lower/middle estimate and the zero-cost services work immediately. This is a low-confidence planning estimate, not a delivery guarantee. Do not silently reduce scope; if assumptions fail, the owner should use formal schedule or scope change control.

The accepted stack is Django 5.2 LTS + PostgreSQL ([ADR-001](../decisions/ADR-001-backend-and-database.md)). The PoC supports technical feasibility for narrow inventory operations, but does not establish full-product readiness, service performance, hosting feasibility or completion of formal Testing.

## Technical feasibility

**Assessment: Core technologies are feasible; full-scope delivery by the deadline remains uncertain.**

The isolated PoC uses Django 5.2.18, psycopg 3.3.6 and PostgreSQL 18.3. Its reviewed source uses a unique SKU and nonnegative quantity model; a stock-change service with transactions and row locking; and an outer-transaction CSV importer. The recorded historical test reports show database constraints, stock changes, rollback behavior and one two-connection concurrent stock-out scenario passed. The [PoC Results](../POC_RESULTS.md), [Technical Feasibility report](../TECHNICAL_FEASIBILITY.md), and [PoC Handover](../POC_HANDOVER.md) describe evidence and limitations.

The checked-in results and handover report 14/14 tests passing (the results document also records a shuffled 14-test pass and five additional concurrency-test passes). Current test source contains 15 test methods. The owner has reported a later 16/16 run, but matching output/source revision is not available in the reviewed project documents; treat that result as unverified until artifacts are available. These are historical records, not fresh test execution for this assessment. Do not count any PoC tests as completion of Tory's formal Testing stage.

The PoC does not implement or test Manager/Staff permissions, per-product supplier/reorder settings, the forecast, user-facing workflows, movement history, staging, CI/CD or production security. Those require Requirements, Design, Implementation and Testing work. The main technical unknowns include detailed role policy, inventory audit design, forecast data rules, error handling, security architecture, selected hosting/database service and test coverage. The existing test discrepancy remains: checked-in reports say 14/14 passed, source has 15 test methods, and 16/16 is owner-reported without an artifact. It is not treated as verified evidence.

The Planning comparison in [TECHNOLOGY_EVALUATION.md](../TECHNOLOGY_EVALUATION.md) scores Django 4.10/5, FastAPI 3.60/5 and Node.js/Express 3.55/5. These totals are decision support, not empirical comparative benchmarks. Django is the approved choice; the alternative scores remain evidence about the Planning decision basis, not open technology selection.

## Economic feasibility

**Assessment: Not yet quantified; feasibility depends on confirming no-cost or affordable access to required services.**

The confirmed cash budget ceiling is **SGD 0**; only zero-cost services may be used. A provider must not be adopted if the required service, account or quota would require payment. Costs to investigate include staging compute, managed PostgreSQL or database hosting, storage/backups, network services if required, CI usage beyond included quotas, and any required paid tooling. Account eligibility, quota and payment-method conditions are not yet verified. If a required capability is unavailable at zero cost, the current scope/deadline combination is infeasible unless the owner approves a change.

The solo developer's time is a project cost even if no cash is budgeted. Django's learning curve may increase early effort; built-in ORM, migrations, authentication/permissions and admin may reduce integration work later. Express is more familiar to the developer but requires assembling more supporting components. The approved stack reflects the weighted comparison and PoC evidence, not a verified cost-saving estimate.

**Economic gate:** zero cash is confirmed. Before Design exit, verify the developer's eligibility, payment-method requirements, resource quotas, demo duration and retention needs for any candidate services. Specific accounts and quotas remain TBD.

## Operational feasibility

**Assessment: Technically plausible for a temporary demonstration, conditional on account/eligibility checks and low-cost-tier limitations.**

One developer is available for 10–15 hours per week through the 27 November deadline. This is a tight delivery window for the remaining scope. Codex is planned as guided development support, with generated code independently checked; it does not replace testing, security review or operational ownership. The solo developer will also own environment configuration, database migrations, test maintenance, deployment preparation and troubleshooting unless other support is confirmed. The Django learning curve and single-person dependency remain material risks.

PostgreSQL is required both for the application and meaningful transactional/concurrency validation. The PoC used a local PostgreSQL server; it does not prove the selected staging host can run PostgreSQL, that credentials/secrets are managed safely, or that backups/restore and uptime are suitable. Staging provider, database service, access policy, backup retention and support expectations are TBD. The PoC's local development settings (`DEBUG=True` and an insecure fallback secret) are not deployment settings.

Automated CI is a fixed requirement. CI must install the pinned application dependencies, provision or connect to PostgreSQL, apply migrations and run approved automated checks. Database credentials and secret values must be supplied securely. CI provider, quota, pipeline checks and handling of migration/test database permissions are TBD. CD is optional and has not been selected.

### Zero-cost service candidates (not selected or approved)

The following combination is technically plausible for a short-lived staging demonstration and CI, subject to account and quota verification:

- **CI candidate: GitHub Actions.** GitHub documents standard hosted-runner minutes as free for public repositories; private-repository included minutes depend on account plan and overage can be billed. A private repository is preferable for coursework unless the owner explicitly approves public exposure. GitHub documents PostgreSQL service containers for workflow jobs, which can run migration and test steps against PostgreSQL. Verify account entitlement, repository privacy, minute quota, service-container support and that billing cannot breach SGD 0. [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
- **Staging app candidate: Render Free web service.** Render documents Python web services on its free tier. It spins down after 15 minutes idle (next request may wait about a minute), has an ephemeral filesystem, and may disable builds/services when included usage is exhausted without a payment method. Render also warns that unusually high outbound traffic, including external database access, can suspend a free service. These limitations may be acceptable only for a scheduled demonstration and must be checked against the planned traffic. [Render free services](https://render.com/docs/free), [Render Django deployment guide](https://render.com/docs/deploy-django).
- **Staging database candidate: Supabase Free PostgreSQL.** The current Free plan lists a dedicated PostgreSQL database, 500 MB database size and 5 GB egress; low-activity projects may be paused after seven days. Free-tier automatic backups are not included, so synthetic demo data and an owner-approved manual export/reseed plan are needed. Confirm account eligibility, region/connectivity, quota and provider terms before selecting it. [Supabase pricing](https://supabase.com/pricing), [Free project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), [database backups](https://supabase.com/docs/guides/platform/backups).

This Render + Supabase + GitHub Actions arrangement is a **candidate only**, not an approved hosting or CI selection. Cross-provider connectivity, PostgreSQL connection settings, TLS, egress thresholds, current eligibility and no-charge operation have not been tested. Render's own free PostgreSQL is another short-lived candidate (1 GB, no backups, expires 30 days after creation); given the deadline, it is unsuitable unless creation timing, demo retention and expiry are verified. No free provider is assumed viable until checks pass. Provider information was researched from official docs on **29 October 2026**. [Render free PostgreSQL limits](https://render.com/docs/free).

## Schedule feasibility

**Assessment: At risk; the approved deadline is fixed, but available hours are insufficient at the low-capacity case.**

The six Waterfall stages are planned in [PROJECT_SCHEDULE.md](PROJECT_SCHEDULE.md), with sequential target dates through **27 November 2026**. The deadline and 10–15 hour weekly capacity are owner-confirmed. The assignment's available capacity is approximately 43–64 hours; estimated remaining work including contingency is 44–54 hours. Therefore the timeline is marginally feasible near sustained upper capacity, but not reliably achievable at 10 hours per week. Stage-gate turnaround and course-calendar conflicts remain unverified.

For a solo student, schedule risk is concentrated in Django learning, requirements clarification, PostgreSQL-backed integration testing, staging/CI setup, defects and coursework conflicts. The schedule includes a 10% provisional contingency. The effort estimate is low-confidence until requirements are baselined and free-tier checks pass. PoC test completion does not satisfy formal Testing exit criteria.

## Feasibility conclusion and conditions

The scope may be achievable only if the solo developer sustains near the upper end of available time, service/account checks pass promptly, and effort stays near the lower/middle estimate. This is not yet a reliable schedule commitment. The owner should consider schedule change control first; if the deadline cannot move, any scope adjustment requires explicit owner change approval and must not silently remove fixed requirements. Before Design exit, verify the zero-cost staging/CI path, available data, PostgreSQL deployment version and operational limitations.

### Source documents

- [ADR-001: Backend Framework and Database](../decisions/ADR-001-backend-and-database.md)
- [Technology Evaluation & Selection](../TECHNOLOGY_EVALUATION.md)
- [PoC Results](../POC_RESULTS.md)
- [Technical Feasibility](../TECHNICAL_FEASIBILITY.md)
- [PoC Handover](../POC_HANDOVER.md)
- [Project Charter](PROJECT_CHARTER.md)
- [Project Schedule](PROJECT_SCHEDULE.md)
- [Official provider documentation: GitHub Actions, Render and Supabase](#zero-cost-service-candidates-not-selected-or-approved)
