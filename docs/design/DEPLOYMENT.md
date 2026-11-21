# Tory deployment view

Staging is a single Linux VM running the TORY-37 image with docker compose. Managed PostgreSQL services cannot run with `track_commit_timestamp=on`, which Tory's demand attribution requires, so PostgreSQL runs in the stack. The deployment decision and runbook are part of TORY-38 (PR #71).

```mermaid
flowchart TB
    user["Browser"] -->|"HTTPS 443<br/>(HTTP 80 redirects)"| caddy

    subgraph vm["Staging VM · docker compose project tory-staging"]
        direction TB
        caddy["caddy:2.11.9<br/>TLS termination, Let's Encrypt<br/>X-Forwarded-For / -Proto"]
        subgraph webc["web container (non-root uid 10001)"]
            gunicorn["gunicorn workers"] --> django["Django 5.2<br/>DJANGO_ENV=staging<br/>WhiteNoise static files<br/>TrustedProxyMiddleware"]
        end
        db[("postgres:18.3<br/>track_commit_timestamp=on")]
        pgdata[["volume: pgdata"]]
        caddydata[["volume: caddy_data<br/>(certificates)"]]
        cron["host cron · every 5 min<br/>deploy.sh scheduled<br/>process_expiry_quarantine<br/>finalize_commit_times"]
        caddy -->|"HTTP :8000<br/>no published port"| gunicorn
        django -->|"psycopg, CONN_MAX_AGE 60"| db
        db --- pgdata
        caddy --- caddydata
        cron -->|"docker compose exec"| django
    end

    subgraph gh["GitHub"]
        actions["GitHub Actions<br/>CD · Release · scheduled-jobs monitor"]
        ghcr[("GHCR<br/>image sha-&lt;commit&gt;")]
        env["staging environment<br/>secrets: VM_HOST, VM_USER, VM_SSH_KEY,<br/>DJANGO_SECRET_KEY, POSTGRES_PASSWORD"]
    end

    actions -->|"push image"| ghcr
    env -.-> actions
    actions -->|"SSH: deploy files, .env (mode 600),<br/>deploy.sh deploy / rollback"| vm
    vm -->|"docker pull with short-lived job token"| ghcr
    actions -->|"smoke test /healthz, /login/"| caddy
```

| Element | Responsibility |
| --- | --- |
| Caddy | Obtains and renews the certificate for `TORY_DOMAIN`, redirects HTTP to HTTPS, and is the only container publishing ports. |
| web (gunicorn + Django) | Runs migrations on start (entrypoint) and serves the app and static files. `/healthz` checks the database. It trusts Caddy's forwarded scheme and client address only because nothing else can reach it. |
| PostgreSQL | Stores all data on the `pgdata` volume. Its triggers enforce stock and audit invariants, and commit timestamps attribute CSV demand. |
| Host cron | Runs the idempotent TORY-19 jobs every five minutes and records a heartbeat. An hourly GitHub workflow fails if the heartbeat is older than 15 minutes. |
| GitHub Actions + GHCR | Build and store immutable images. Deploy over SSH and roll back to the previous image if the smoke test fails. |

For local development the same image runs from the root [docker-compose.yml](../../docker-compose.yml): PostgreSQL plus the web container, without Caddy. See also the [CI/CD pipeline](CICD_PIPELINE.md) and the [component view](COMPONENTS.md).
