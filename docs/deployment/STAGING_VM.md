# Staging VM runbook

This runbook sets up the staging VM described in [ADR-005](../decisions/ADR-005-staging-vm-hosting.md). After these steps, every merge to `main` deploys automatically through the [CD workflow](../../.github/workflows/cd.yml).

## 1. VM and DNS

- Use Ubuntu 24.04 LTS or similar, with at least 1 vCPU and 2 GB RAM (PBKDF2 sign-in is CPU-bound). Allow 20 GB of disk.
- Open inbound TCP 22 (ideally restricted to your own address), TCP 80 and 443, and UDP 443. Keep everything else closed.
- Point a DNS name at the VM's public IP; that name becomes `TORY_DOMAIN`. Without a domain, `<ip-with-dashes>.sslip.io` (for example `203-0-113-10.sslip.io`) resolves to the IP, and Let's Encrypt can issue a certificate for it.

## 2. Docker and a deploy user

Run as an administrator on the VM:

```text
curl -fsSL https://get.docker.com | sudo sh
sudo apt-get install -y cron
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
```

Membership of the `docker` group is root-equivalent. Use this account only for deployment.

## 3. Deploy key

On your own machine, create a key used only by GitHub Actions:

```text
ssh-keygen -t ed25519 -N "" -C tory-staging-deploy -f tory_deploy_key
```

Append `tory_deploy_key.pub` to `/home/deploy/.ssh/authorized_keys` on the VM (directory mode 700, file mode 600). Then record the host key so the workflow can pin it:

```text
ssh-keyscan -H <vm-host>
```

## 4. GitHub `staging` environment

In **Settings → Environments → New environment**, create `staging`, optionally restricted to the `main` branch. Add:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `VM_HOST` | VM public IP or hostname |
| Secret | `VM_USER` | `deploy` |
| Secret | `VM_SSH_KEY` | contents of `tory_deploy_key` (private key) |
| Secret | `VM_SSH_KNOWN_HOSTS` | output of `ssh-keyscan -H <vm-host>`; recommended, since without it the workflow trusts whatever key it scans |
| Secret | `DJANGO_SECRET_KEY` | a long random value, for example `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| Secret | `POSTGRES_PASSWORD` | a long random value |
| Variable | `TORY_DOMAIN` | the DNS name from step 1 |
| Variable | `VM_SSH_PORT` | optional; defaults to 22 |
| Variable | `POSTGRES_DB`, `POSTGRES_USER` | optional; both default to `tory` |
| Variable/secret | `EMAIL_HOST`, `EMAIL_HOST_USER`, `DEFAULT_FROM_EMAIL` / `EMAIL_HOST_PASSWORD` | optional; enables invitation and reset email |

Values must not contain a single quote or a newline. The workflow writes them to `~/tory/.env` with mode 600 on every deploy.

## 5. First deploy

Merge to `main`, or run **Actions → CD → Run workflow** on `main`. The run waits for all checks, publishes `ghcr.io/<owner>/<repo>:sha-<commit>`, deploys, and smoke-tests `https://TORY_DOMAIN`. The first certificate can take up to a minute; the smoke test retries for two minutes.

Then create the first Manager on the VM:

```text
cd ~/tory && docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml exec web python manage.py bootstrap_manager --business-name "..." --manager-email ... --inventory "..."
```

## Operating

| Task | Command on the VM (as `deploy`, in `~/tory`) |
| --- | --- |
| What is running | `./deploy.sh status` |
| Run a management command | `./deploy.sh manage <command>` |
| Scheduled jobs log | `tail scheduled.log`; `./deploy.sh check-scheduled` |
| Roll back the live image | `./deploy.sh rollback "$(sed -n 's/^TORY_IMAGE=//p' .image.env)"` |
| Logs | `docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml logs web` |

Release a deployed commit by pushing a tag: `git tag v1.0.0 <commit> && git push origin v1.0.0`.

Changing `POSTGRES_PASSWORD` in GitHub does not change the existing database role's password; run `ALTER ROLE` first.

## Backups (NFR-008)

Every deploy installs a daily cron job (02:23 VM time) that runs `./deploy.sh backup`:

- `pg_dump --format=custom` of the live database to `~/tory/backups/tory-<UTC timestamp>.dump`, written atomically. The directory is mode 700 and the files mode 600.
- Backups older than 14 days are deleted. Every run is logged to `~/tory/backups.log`.
- The hourly **Staging scheduled jobs and backup monitor** workflow runs `./deploy.sh check-backup` and fails if the newest backup is more than 26 hours old.

| Task | Command (as `deploy`, in `~/tory`) |
| --- | --- |
| Back up now | `./deploy.sh backup` |
| Newest backup and its age | `./deploy.sh check-backup` |
| Test a backup without touching live data | `./deploy.sh restore-test` (newest) or `./deploy.sh restore-test tory-<timestamp>.dump` |
| Replace the live database | `./deploy.sh restore tory-<timestamp>.dump` |

These backups live on the VM's own disk, so they protect against bad deploys, mistaken changes and database corruption, but not against losing the VM. Copy them off the VM as described in the [off-site backup policy](../decisions/TORY-27-offsite-backup-policy.md) (still a draft).

### Restore test

Run this after the first deploy and then monthly, and record the result:

1. `./deploy.sh backup`, then `./deploy.sh restore-test`.
2. The script restores the newest dump into a scratch database (`tory_restore_test`) and prints row counts for migrations, users, inventories, products, inventory products, batches, receipts and issues. It shows the restored count next to the live count, then drops the scratch database. Live data is never touched.
3. Check that it ends with "Restore test passed". Restored counts should equal live counts if nothing changed since the backup; live counts may only be higher.
4. Record the date, backup file name and output in the TORY-27 restore evidence.

### Restoring the live database

`./deploy.sh restore <file>` first takes a `pre-restore-<timestamp>.dump` safety backup. It then stops the web container and restores the file in a single transaction with `pg_restore --clean`, which leaves the old data in place if the restore fails. Finally it starts the web container again (migrations run on start). The last line prints the command that undoes the restore. Afterwards, run `./deploy.sh manage finalize_commit_times`: CSV demand attribution recorded after the backup was taken is not in the restored data.
