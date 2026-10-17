"""Small clean-ups that run after every database update."""


def backfill_task_numbers():
    """Give tasks created before numbering a number too, oldest first."""
    from .models import Sequence, Task

    for task in Task.objects.filter(number__isnull=True).order_by("created_at", "id"):
        Task.objects.filter(pk=task.pk).update(number=Sequence.next_number("task"))


def normalise_item_types():
    """Items saved before types became free text hold 'material' / 'product': show them as Material / Product."""
    from .models import InventoryItem

    for old, new in (("material", "Material"), ("product", "Product")):
        InventoryItem.objects.filter(kind=old).update(kind=new)
