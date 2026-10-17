"""Lets a superuser stop the server from the website (only when it was started with serve.py)."""
import os
import threading
import time

from .backups import make_backup


def can_shutdown(user):
    return bool(
        user.is_authenticated and user.is_superuser and os.environ.get("WORKLOG_SERVE") == "1"
    )


def _exit_later(delay):
    time.sleep(delay)   # let the "stopping" page reach the browser first
    os._exit(0)


def shutdown_now(delay=2.0):
    """Back up the database, then stop the server a moment later. Returns the backup file (or None)."""
    backup = None
    try:
        backup = make_backup()
    except Exception as exc:   # a failed backup must not leave the server stuck on
        print(f"Backup before shutdown failed: {exc}", flush=True)
    threading.Thread(target=_exit_later, args=(delay,), daemon=True).start()
    return backup
