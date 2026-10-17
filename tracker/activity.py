"""Write entries to the activity log and describe what changed."""
from decimal import Decimal

from .inventory import fmt_money, fmt_qty
from .models import ActivityLog

LONG_TEXT = 60


def log(who, action, kind, target, details=""):
    """`who` is a request or a user. action: created / updated / deleted."""
    user = getattr(who, "user", who)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    ActivityLog.objects.create(
        user=user,
        username=user.get_username() if user else "",
        action=action,
        kind=kind,
        target=str(target)[:200],
        details=details,
    )


def _show(value, money=False):
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Decimal):
        return fmt_money(value) if money else fmt_qty(value)
    return str(value)


def snapshot(obj, fields):
    """{label: text} for (attribute, label[, 'money']) entries, ready to compare before/after."""
    out = {}
    for entry in fields:
        attr, label = entry[0], entry[1]
        money = len(entry) > 2 and entry[2] == "money"
        display = getattr(obj, f"get_{attr}_display", None)
        value = display() if callable(display) else getattr(obj, attr, None)
        out[label] = _show(value, money)
    return out


def describe(snap):
    """All the non-empty values of a snapshot, for 'created' and 'deleted' entries."""
    return "; ".join(f"{k}: {v}" for k, v in snap.items() if v != "-")


def changes(before, after):
    """'label: old -> new' for everything that differs ('' if nothing did)."""
    parts = []
    for label, new in after.items():
        old = before.get(label, "-")
        if old == new:
            continue
        if len(old) > LONG_TEXT or len(new) > LONG_TEXT:
            parts.append(f"{label}: edited")
        else:
            parts.append(f"{label}: {old} -> {new}")
    return "; ".join(parts)


TASK_FIELDS = [
    ("mission", "type"), ("place", "location"), ("due_date", "due"), ("priority", "priority"),
    ("status", "status"), ("estimated_minutes", "estimated minutes"), ("description", "description"),
]
ITEM_FIELDS = [
    ("name", "name"), ("kind", "type"), ("reference", "reference"), ("unit", "unit"),
    ("min_stock", "warning level"), ("note", "note"), ("is_active", "active"),
]
PURCHASE_FIELDS = [
    ("date", "date"), ("quantity", "quantity"), ("unit_price", "price per unit", "money"),
    ("supplier", "supplier"), ("supplier_location", "supplier location"), ("note", "note"),
]
MATERIAL_FIELDS = [
    ("item", "material"), ("quantity", "quantity"), ("unit_price", "cost per unit", "money"), ("note", "note"),
]
