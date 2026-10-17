from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _after_migrate(sender, **kwargs):
    from .access import seed_default_roles, sync_administrator_role
    from .maintenance import backfill_task_numbers, normalise_item_types

    for step in (seed_default_roles, sync_administrator_role, backfill_task_numbers, normalise_item_types):
        try:
            step()
        except Exception as exc:   # never stop a database update because of a tidy-up step
            print(f"{step.__name__} problem: {exc}", flush=True)


class TrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"

    def ready(self):
        post_migrate.connect(_after_migrate, sender=self)
