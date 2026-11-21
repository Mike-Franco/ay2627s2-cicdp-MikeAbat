# ADR-005: Staging on a VM Running Docker Compose

**Decision date:** 21 November 2026
**Status:** Accepted by project owner; VM provider and domain to be recorded when the VM is provisioned
**Issue:** TORY-38
**Scope:** `.github/workflows/cd.yml`, `release.yml`, `scheduled-ops.yml`, `deploy/`, `config/proxy.py`

## Context

TORY-38 completes the CD half of the pipeline: every merge to `main` must reach a live HTTPS URL with no manual steps, and a failed smoke test must mark the run red. TORY-37 already packages Tory as an immutable image with a compose stack.

Tory's demand attribution reads PostgreSQL commit timestamps, so the server must run with `track_commit_timestamp=on`. The [deployment feasibility review](../requirements/DEPLOYMENT_FEASIBILITY_GAP_OWNER_DECISIONS.md) records this as a compatibility gate. Managed PostgreSQL offerings considered there (Neon, Supabase, Render) do not let a tenant set this server parameter. The same review records TORY-19's requirement to run the idempotent expiry command every five minutes, with monitoring before the one-hour evidence limit.

## Decision

Host staging on a single Linux VM that runs the TORY-37 image with docker compose ([`deploy/docker-compose.prod.yml`](../../deploy/docker-compose.prod.yml)):

- **PostgreSQL 18.3** in the stack, started with `track_commit_timestamp=on`, on a named volume. No database port is published.
- **Tory web** (gunicorn) runs the image from GitHub Container Registry tagged with the commit SHA, in `DJANGO_ENV=staging`. It publishes no port.
- **Caddy** terminates TLS on ports 80 and 443 and obtains a Let's Encrypt certificate for `TORY_DOMAIN` automatically. Because only Caddy can reach gunicorn, `DJANGO_TRUSTED_PROXY=true` is safe. Django then trusts `X-Forwarded-Proto` for HTTPS redirects and secure cookies. [`TrustedProxyMiddleware`](../../config/proxy.py) takes the client address from the rightmost `X-Forwarded-For` entry. Without it, every visitor would share Caddy's address and therefore one 20-failure login-throttle bucket.

The pipeline:

1. **Gate.** [`cd.yml`](../../.github/workflows/cd.yml) starts when Django PostgreSQL CI finishes for a push to `main`. It waits until every other check on that commit has passed (lint, tests with coverage, the Docker image job, security and docs) and requires the key jobs to be present.
2. **Publish.** It builds the image and pushes `ghcr.io/<repo>:sha-<commit>` and `:latest`.
3. **Deploy.** The `staging` GitHub environment holds the secrets. The job copies `deploy/` to `~/tory` on the VM over SSH and writes `~/tory/.env` (mode 600) from those secrets. [`deploy.sh`](../../deploy/deploy.sh) then logs in to GHCR with the short-lived job token, pulls, logs out, and runs `docker compose up --wait`. The entrypoint applies migrations before gunicorn starts.
4. **Verify.** The runner calls `https://TORY_DOMAIN/healthz` and checks that `/login/` serves the sign-in form. If the deploy or the smoke test fails, `deploy.sh rollback` restarts the previous image, and the run stays red.
5. **Release.** Pushing a `v*` tag on a deployed commit creates a GitHub Release with generated notes. It also tags that commit's image with the version.

Scheduled work runs on the VM itself. `deploy.sh` installs a crontab line that runs `process_expiry_quarantine` and `finalize_commit_times` every five minutes and records a heartbeat. An hourly GitHub workflow fails if the heartbeat is older than 15 minutes. GitHub's own scheduler is too irregular to meet the five-minute requirement alone.

## Consequences

- One VM is a single point of failure. That is acceptable for staging; a deploy restarts the web container for a few seconds.
- The VM operator owns OS patching, Docker updates, the firewall, and backups of the `pgdata` volume. [TORY-27](TORY-27-local-backup-restore.md) covers the backup tool. The off-site policy remains a draft.
- Secrets live in the GitHub `staging` environment and are written to the VM on each deploy. GHCR credentials are never stored on the VM. Changing `POSTGRES_PASSWORD` after the first deploy does not change the existing database role's password; rotate it in PostgreSQL first.
- `latest` is a convenience tag. Deploys and rollbacks always use the immutable `sha-` tag.
- Setup steps are in the [staging VM runbook](../deployment/STAGING_VM.md).

## Alternatives rejected

- **Render, Railway, Fly.io or Koyeb web with managed PostgreSQL:** the database cannot run with `track_commit_timestamp=on`.
- **A managed platform running PostgreSQL in a container:** free tiers do not offer durable volumes or reliable five-minute jobs.
- **GitHub scheduled workflows for the TORY-19 jobs:** runs can start late or be dropped. They are used only for monitoring.
