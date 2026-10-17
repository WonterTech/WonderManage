#!/usr/bin/env python
"""Make a safe copy of the database right now (into data/backups/). Safe to run while the server is on."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
from tracker.backups import make_backup  # noqa: E402

print(f"Backup saved: {make_backup(force=True)}")
