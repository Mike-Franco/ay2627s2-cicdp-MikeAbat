"""Recoverable PostgreSQL commit-time finalization for CSV demand."""

from django.db import DatabaseError, connection, transaction

from .models import ObservationActivation, StockImport


ACTIVATION_LOCK = (20261109, 23)


def tracking_enabled():
    with connection.cursor() as cursor:
        cursor.execute("SHOW track_commit_timestamp")
        return cursor.fetchone()[0] == "on"


def lock_activation(*, shared):
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {function}(%s, %s)", ACTIVATION_LOCK)


def current_xid():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_current_xact_id()::text")
        return cursor.fetchone()[0]


def _commit_time(xid):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT CASE WHEN pg_xact_status(%s::xid8) = 'committed' "
            "THEN pg_xact_commit_timestamp(%s::xid8::xid) END",
            [xid, xid],
        )
        return cursor.fetchone()[0]


def finalize_stock_import(import_id):
    """Idempotent; a missing timestamp keeps attribution unavailable."""
    if not tracking_enabled():
        return False
    try:
        with transaction.atomic():
            record = StockImport.objects.select_for_update().get(pk=import_id)
            if record.commit_attribution != "pending" or not record.origin_xid:
                return record.commit_attribution == "resolved"
            committed_at = _commit_time(record.origin_xid)
            if committed_at is None:
                return False
            record.actual_committed_at = committed_at
            record.commit_attribution = "resolved"
            record.save(update_fields=["actual_committed_at", "commit_attribution"])
            return True
    except (DatabaseError, StockImport.DoesNotExist):
        return False


def finalize_activation(activation_id):
    if not tracking_enabled():
        return False
    try:
        with transaction.atomic():
            record = ObservationActivation.objects.select_for_update().get(pk=activation_id)
            if record.state != "pending":
                return record.state == "active"
            committed_at = _commit_time(record.origin_xid)
            if committed_at is None:
                return False
            from .services import expiry_boundary

            record.actual_committed_at = committed_at
            record.state = "active" if committed_at < expiry_boundary(record.first_observed_date) else "invalid"
            record.save(update_fields=["actual_committed_at", "state"])
            return record.state == "active"
    except (DatabaseError, ObservationActivation.DoesNotExist):
        return False
