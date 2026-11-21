#!/bin/sh
# Staging control script on the VM (ADR-005). The CD workflow copies this file
# and docker-compose.prod.yml into ~/tory, writes ~/tory/.env, then calls:
#
#   deploy.sh deploy <image> <ghcr-user>   GHCR token on stdin; pull and start
#   deploy.sh rollback <failed-image>      restart the previous image if <failed-image> is live
#   deploy.sh manage <command> [args...]   run a Django management command
#   deploy.sh scheduled                    run the TORY-19 jobs (cron, every 5 minutes)
#   deploy.sh check-scheduled              fail if the jobs have not succeeded recently
#   deploy.sh status                       show containers and the deployed image
set -eu

cd "$(dirname "$0")"
compose() {
    docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml "$@"
}

install_cron() {
    # Idempotent: replace only this project's line in the user's crontab.
    line="*/5 * * * * $(pwd)/deploy.sh scheduled >> $(pwd)/scheduled.log 2>&1 # tory-scheduled"
    { crontab -l 2>/dev/null | grep -v '# tory-scheduled' || true; echo "$line"; } | crontab -
}

start() {
    printf 'TORY_IMAGE=%s\n' "$1" > .image.env
    # The web entrypoint applies migrations before gunicorn starts; --wait
    # returns only when every service reports healthy.
    compose up --detach --remove-orphans --wait --wait-timeout 300
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
    status)
        cat .image.env
        compose ps
        ;;
    *)
        echo "usage: $0 deploy <image> <ghcr-user> | rollback <failed-image> | manage <command> | scheduled | check-scheduled | status" >&2
        exit 2
        ;;
esac
