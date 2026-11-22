#!/bin/sh
# Staging control script on the VM (ADR-005). The CD workflow copies this file
# and docker-compose.prod.yml into ~/tory, writes ~/tory/.env, then calls:
#
#   deploy.sh deploy <image> <ghcr-user>   GHCR token on stdin; pull and start
#   deploy.sh rollback <failed-image>      restart the previous image if <failed-image> is live
#   deploy.sh manage <command> [args...]   run a Django management command
#   deploy.sh scheduled                    run the TORY-19 jobs (cron, every 5 minutes)
#   deploy.sh check-scheduled              fail if the jobs have not succeeded recently
#   deploy.sh backup                       pg_dump to backups/ with 14-day retention (cron, daily)
#   deploy.sh check-backup                 fail if the newest backup is older than 26 hours
#   deploy.sh restore-test [file]          restore into a scratch database and compare row counts
#   deploy.sh restore <file>               replace the live database from a backup (takes a safety backup first)
#   deploy.sh status                       show containers and the deployed image
set -eu

cd "$(dirname "$0")"
BACKUP_DIR="$(pwd)/backups"
RETENTION_DAYS=14
MAX_BACKUP_AGE=$((26 * 3600))
# Tables whose row counts a restore test compares with the live database.
CHECK_TABLES="django_migrations accounts_user inventory_access_inventory catalogue_product catalogue_inventoryproduct receiving_receivingbatch receiving_receiptauditevent receiving_demandauditevent"

compose() {
    docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml "$@"
}

db_sh() {
    # Run a shell command in the db container, where POSTGRES_USER and POSTGRES_DB are set.
    compose exec -T db sh -c "$1"
}

install_cron() {
    # Idempotent: replace only this project's lines in the user's crontab.
    scheduled="*/5 * * * * $(pwd)/deploy.sh scheduled >> $(pwd)/scheduled.log 2>&1 # tory-scheduled"
    backup="23 2 * * * $(pwd)/deploy.sh backup >> $(pwd)/backups.log 2>&1 # tory-backup"
    { crontab -l 2>/dev/null | grep -v -e '# tory-scheduled' -e '# tory-backup' || true
      echo "$scheduled"; echo "$backup"; } | crontab -
}

start() {
    printf 'TORY_IMAGE=%s\n' "$1" > .image.env
    # The web entrypoint applies migrations before gunicorn starts; --wait
    # returns only when every service reports healthy.
    compose up --detach --remove-orphans --wait --wait-timeout 300
}

take_backup() {
    # $1: file name prefix. Writes atomically, owner-only, and prints the path.
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
    target="$BACKUP_DIR/$1-$(date -u +%Y%m%dT%H%M%SZ).dump"
    umask 077
    db_sh 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$target.partial"
    mv "$target.partial" "$target"
    echo "$target"
}

latest_backup() {
    find "$BACKUP_DIR" -maxdepth 1 -name 'tory-*.dump' -type f 2>/dev/null | sort | tail -n 1
}

row_counts() {
    # $1: database name. Prints "table count" lines for CHECK_TABLES.
    for table in $CHECK_TABLES; do
        printf '%s %s\n' "$table" "$(db_sh "psql -U \"\$POSTGRES_USER\" -d $1 -Atc 'SELECT count(*) FROM $table'")"
    done
}

require_backup_file() {
    file="${1:?backup file required}"
    case "$file" in /*) ;; *) file="$BACKUP_DIR/$(basename "$file")" ;; esac
    if [ ! -s "$file" ]; then
        echo "Backup file not found or empty: $file" >&2
        exit 1
    fi
}

case "${1:-}" in
    deploy)
        image="${2:?image required}"
        user="${3:?GHCR user required}"
        docker login ghcr.io --username "$user" --password-stdin
        pull_status=0
        docker pull "$image" || pull_status=$?
        docker logout ghcr.io
        [ "$pull_status" -eq 0 ] || exit "$pull_status"
        if [ -f .image.env ]; then
            cp .image.env .previous-image.env
        fi
        start "$image"
        install_cron
        docker image prune --force >/dev/null
        echo "Deployed $image"
        ;;
    rollback)
        failed="${2:?failed image required}"
        current="$(sed -n 's/^TORY_IMAGE=//p' .image.env 2>/dev/null || true)"
        if [ "$current" != "$failed" ]; then
            # The failed image never replaced the running one (for example the
            # pull failed), so the live stack is already the last good image.
            echo "Running image is ${current:-none}; nothing to roll back."
            exit 0
        fi
        if [ ! -f .previous-image.env ]; then
            echo "No previous deployment recorded; nothing to roll back to." >&2
            exit 1
        fi
        previous="$(sed -n 's/^TORY_IMAGE=//p' .previous-image.env)"
        start "$previous"
        echo "Rolled back to $previous"
        ;;
    manage)
        shift
        compose exec -T web python manage.py "$@"
        ;;
    scheduled)
        echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        compose exec -T web python manage.py process_expiry_quarantine
        compose exec -T web python manage.py finalize_commit_times
        date -u +%s > .last-scheduled-ok
        tail -n 2000 scheduled.log > scheduled.log.tmp 2>/dev/null && mv scheduled.log.tmp scheduled.log || true
        ;;
    check-scheduled)
        last="$(cat .last-scheduled-ok 2>/dev/null || echo 0)"
        age=$(( $(date -u +%s) - last ))
        tail -n 6 scheduled.log 2>/dev/null || true
        if [ "$age" -gt 900 ]; then
            echo "Scheduled jobs last succeeded ${age}s ago (limit 900s)." >&2
            exit 1
        fi
        echo "Scheduled jobs last succeeded ${age}s ago."
        ;;
    backup)
        echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) backup"
        file="$(take_backup tory)"
        echo "Wrote $file ($(wc -c < "$file") bytes)"
        find "$BACKUP_DIR" -maxdepth 1 -name 'tory-*.dump' -type f -mtime +$((RETENTION_DAYS - 1)) -print -delete \
            | sed 's/^/Removed expired /'
        find "$BACKUP_DIR" -maxdepth 1 -name 'pre-restore-*.dump' -type f -mtime +$((RETENTION_DAYS - 1)) -delete
        date -u +%s > .last-backup-ok
        tail -n 1000 backups.log > backups.log.tmp 2>/dev/null && mv backups.log.tmp backups.log || true
        ;;
    check-backup)
        newest="$(latest_backup)"
        if [ -z "$newest" ]; then
            echo "No backups found in $BACKUP_DIR." >&2
            exit 1
        fi
        age=$(( $(date -u +%s) - $(date -u -r "$newest" +%s) ))
        tail -n 4 backups.log 2>/dev/null || true
        if [ "$age" -gt "$MAX_BACKUP_AGE" ]; then
            echo "Newest backup $(basename "$newest") is ${age}s old (limit ${MAX_BACKUP_AGE}s)." >&2
            exit 1
        fi
        echo "Newest backup $(basename "$newest") is ${age}s old; $(find "$BACKUP_DIR" -maxdepth 1 -name 'tory-*.dump' | wc -l) kept."
        ;;
    restore-test)
        if [ -n "${2:-}" ]; then require_backup_file "$2"; else file="$(latest_backup)"; fi
        [ -n "${file:-}" ] || { echo "No backup to test." >&2; exit 1; }
        scratch=tory_restore_test
        echo "Restoring $(basename "$file") into scratch database $scratch"
        db_sh "dropdb -U \"\$POSTGRES_USER\" --if-exists $scratch && createdb -U \"\$POSTGRES_USER\" $scratch"
        db_sh "pg_restore -U \"\$POSTGRES_USER\" -d $scratch --no-owner --exit-on-error" < "$file"
        row_counts "$scratch" > .restore-test.restored
        db_sh 'echo "$POSTGRES_DB"' > .restore-test.live-db
        row_counts "$(cat .restore-test.live-db)" > .restore-test.live
        db_sh "dropdb -U \"\$POSTGRES_USER\" $scratch"
        printf '%-32s %10s %10s\n' table backup live
        paste -d ' ' .restore-test.restored .restore-test.live | awk '{printf "%-32s %10s %10s\n", $1, $2, $4}'
        rm -f .restore-test.restored .restore-test.live .restore-test.live-db
        echo "Restore test passed: $(basename "$file") restores cleanly. Live counts may be higher if data changed since the backup."
        ;;
    restore)
        require_backup_file "${2:-}"
        safety="$(take_backup pre-restore)"
        echo "Safety backup of the current database: $safety"
        compose stop web
        db_sh 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction --exit-on-error' < "$file"
        compose start web
        compose up --detach --wait --wait-timeout 300
        echo "Restored $(basename "$file"). To undo: $0 restore $safety"
        ;;
    status)
        cat .image.env
        compose ps
        ;;
    *)
        echo "usage: $0 deploy <image> <ghcr-user> | rollback <failed-image> | manage <command> | scheduled | check-scheduled | backup | check-backup | restore-test [file] | restore <file> | status" >&2
        exit 2
        ;;
esac
