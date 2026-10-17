"""Safe copies of the database, kept in data/backups/."""
import sqlite3
from datetime import datetime

from django.conf import settings


def make_backup(force=False):
    """Copy the database into data/backups/ and drop the oldest copies.

    Returns the new file, or None when nothing has changed since the last backup
    (pass force=True to copy anyway). Safe to run while the server is in use.
    """
    db = settings.DB_PATH
    if not db.exists():
        return None
    folder = settings.DATA_DIR / "backups"
    folder.mkdir(exist_ok=True)
    existing = sorted(folder.glob("db-*.sqlite3"))
    if not force and existing and existing[-1].stat().st_mtime >= db.stat().st_mtime:
        return None

    target = folder / f"db-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    source = sqlite3.connect(db)
    copy = sqlite3.connect(target)
    try:
        with copy:
            source.backup(copy)
    finally:
        copy.close()
        source.close()
    try:
        target.chmod(0o600)
    except OSError:
        pass

    for old in sorted(folder.glob("db-*.sqlite3"))[: -settings.BACKUP_KEEP]:
        old.unlink()
    return target
