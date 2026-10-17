"""Stock figures and number formatting for the inventory pages (all exact Decimal maths)."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")


def fmt_qty(value):
    """12.00 -> 12, 2.50 -> 2.5"""
    if value is None or value == "":
        return ""
    text = format(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def fmt_money(value):
    """Up to 3 decimals, at least 2, with thousands separators: 1234.5 -> 1,234.50"""
    if value is None or value == "":
        return "-"
    text = format(Decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), ",f")
    whole, _, frac = text.partition(".")
    return f"{whole}.{frac.rstrip('0').ljust(2, '0')}"


def blank_stats():
    return {"bought": ZERO, "used": ZERO, "spent": ZERO, "in_stock": ZERO, "avg_cost": None, "last_price": None}


def item_stats(item_id=None):
    """{item id: figures}. Pass an id to get the figures for that one item only."""
    from .models import Purchase, TaskMaterial

    purchases, usages = Purchase.objects.order_by("date", "id"), TaskMaterial.objects.all()
    if item_id is not None:
        purchases, usages = purchases.filter(item_id=item_id), usages.filter(item_id=item_id)
    stats = {}
    for pk, qty, price in purchases.values_list("item_id", "quantity", "unit_price"):
        s = stats.setdefault(pk, blank_stats())
        s["bought"] += qty
        s["spent"] += qty * price
        s["last_price"] = price
    for pk, qty in usages.values_list("item_id", "quantity"):
        stats.setdefault(pk, blank_stats())["used"] += qty
    for s in stats.values():
        s["in_stock"] = s["bought"] - s["used"]
        s["avg_cost"] = (s["spent"] / s["bought"]) if s["bought"] else None
    return stats


def stats_for(item):
    return item_stats(item.pk).get(item.pk) or blank_stats()


def average_cost(item):
    """Average price paid per unit over all purchases of this item (None if never bought)."""
    return stats_for(item)["avg_cost"]


def stock_flag(item, stats):
    """'negative', 'low' or ''."""
    if stats["in_stock"] < 0:
        return "negative"
    if item.min_stock is not None and stats["in_stock"] <= item.min_stock:
        return "low"
    return ""


def item_types():
    """Every type in use plus the two starter ones, one spelling each, alphabetical."""
    from .models import InventoryItem

    seen = {}
    for name in list(InventoryItem.DEFAULT_TYPES) + list(InventoryItem.objects.values_list("kind", flat=True)):
        name = " ".join((name or "").split())
        if name:
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)
