"""Small bounded in-process handoff for anonymous reset requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock

from django.db import close_old_connections, connections

from .password_resets import request_password_reset
from .reset_email import ResetDeliveryError, delivery_origin, send_reset


_slots = BoundedSemaphore(32)
_executor = None
_executor_lock = Lock()


def _run_reset(email, source_ip):
    """Run one admitted request after checkout; testable without a worker."""
    origin = delivery_origin()
    result = request_password_reset(email, source_ip)
    if result.credentials is not None:
        send_reset(result.credentials, origin)


def process_reset(email, source_ip):
    """Worker entry point; admitted work is the only source of credentials."""
    try:
        close_old_connections()
        _run_reset(email, source_ip)
    except Exception:
        # No credential or identity is written to logs or public responses.
        pass
    finally:
        connections.close_all()
        _slots.release()


def enqueue_reset(email, source_ip):
    """Return immediately when all 32 running/queued slots are occupied."""
    global _executor
    if not _slots.acquire(blocking=False):
        return False
    try:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tory-reset")
            executor = _executor
        executor.submit(process_reset, email, source_ip)
        return True
    except (RuntimeError, OSError):
        _slots.release()
        return False
