# Tory component view

Tory is one Django project with four apps. Views stay thin: they authorize, bind forms and render templates. The service modules own the business rules and take row locks. PostgreSQL triggers enforce the stock and audit invariants again at the database, so a bug or a direct SQL write cannot break them.

```mermaid
flowchart TB
    req["HTTP request"] --> mw

    subgraph mw["Middleware (config/settings.py)"]
        direction LR
        m1["SecurityMiddleware<br/>HTTPS redirect, /healthz exempt"] --> m2["WhiteNoise<br/>static files"] --> m3["Sessions"] --> m4["Common"] --> m5["CSRF"] --> m6["Authentication"] --> m7["Messages"]
    end

    mw --> urls["config.urls<br/>named routes · /healthz · ops-admin"]
    urls --> views

    subgraph views["Views + forms (per app)"]
        direction LR
        va["accounts<br/>login, invitations,<br/>password reset, staff"]
        vi["inventory_access<br/>inventory list, create,<br/>rename, status"]
        vc["catalogue<br/>products, catalogue, stock,<br/>history, forecast, insights,<br/>bulk demand verify, CSV export"]
        vr["receiving<br/>receive, issue, adjust,<br/>dispose, CSV import"]
    end

    pv["protected_view<br/>absolute + idle session expiry"] -.-> views

    subgraph services["Service modules (business rules, locks, transactions)"]
        direction LR
        sa["accounts: throttle, sessions,<br/>invitations, password_resets,<br/>deactivation, dashboard"]
        si["inventory_access: authorization,<br/>inventory_changes,<br/>context_processors"]
        sc["catalogue: authorization, reorder,<br/>lifecycle, product_changes,<br/>csv_exports"]
        sr["receiving: services (FEFO stock),<br/>demand, csv_import, commit_times"]
    end

    views --> services
    views --> tpl["Templates<br/>base.html · includes/ · per-app pages<br/>404/403/500 · tory_format, tory_cards tags"]
    services --> orm["Django ORM<br/>models, migrations, atomic + select_for_update"]
    orm --> pg

    subgraph pg["PostgreSQL 18 (track_commit_timestamp=on)"]
        direction LR
        t1["Business-scope triggers<br/>inventory / product / assignment /<br/>membership business guards"]
        t2["Stock-balance triggers<br/>batch, stock-out, adjustment,<br/>disposal, expiry apply/initial/delete guards"]
        t3["Audit triggers<br/>audit required · immutable ·<br/>consistency guards"]
        t4["Advisory locks<br/>login throttle keys"]
        t5["pg_xact_commit_timestamp<br/>CSV demand attribution"]
    end

    sr -->|"targeted SQL"| t5
    sa -->|"pg_advisory_xact_lock"| t4
    tpl --> resp["HTML response"]
```

| Component | Key modules | Notes |
| --- | --- | --- |
| accounts | [models](../../accounts/models.py), [throttle](../../accounts/throttle.py), [sessions](../../accounts/sessions.py), [dashboard](../../accounts/dashboard.py) | Email user model. The login throttle reserves a slot under advisory locks, then hashes the password outside them (TORY-46). |
| inventory_access | [authorization](../../inventory_access/authorization.py), [inventory_changes](../../inventory_access/inventory_changes.py) | Businesses, memberships, inventories and assignments. All pages resolve scope through these helpers. |
| catalogue | [views](../../catalogue/views.py), [reorder](../../catalogue/reorder.py), [lifecycle](../../catalogue/lifecycle.py) | Products, inventory links, reorder settings and the forecast, insights and bulk verification pages. |
| receiving | [services](../../receiving/services.py), [demand](../../receiving/demand.py), [csv_import](../../receiving/csv_import.py), [commit_times](../../receiving/commit_times.py) | Batches with FEFO allocation, stock movements, expiry quarantine, disposal, audit events, CSV import and verified demand. |
| PostgreSQL triggers | migrations in each app | About 50 triggers (for example `receiving_batch_scope_balance_guard`, `receiving_audit_immutable_guard`, `inventory_access_assignment_business_guard`) re-check business scope, balances and audit immutability on every write. |

See also the [application structure and stock-out sequence](ARCHITECTURE.md), the [ERD](ERD.md), the [CI/CD pipeline](CICD_PIPELINE.md) and the [deployment view](DEPLOYMENT.md).
