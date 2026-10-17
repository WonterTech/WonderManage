from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .activity import (
    ITEM_FIELDS, MATERIAL_FIELDS, PURCHASE_FIELDS, changes, describe, log, snapshot,
)
from .forms import InventoryItemForm, PurchaseForm, TaskMaterialForm
from .inventory import ZERO, blank_stats, item_stats, item_types, stats_for, stock_flag
from .models import InventoryItem, Purchase, Task, TaskMaterial
from .views import _safe_next


def _allow(request, codename):
    if not request.user.has_perm(f"tracker.{codename}"):
        raise PermissionDenied


# ------------------------------------------------------------------ inventory list and item pages
@permission_required("tracker.view_inventoryitem", raise_exception=True)
def inventory_list(request):
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    show_all = request.GET.get("show") == "all"
    items = InventoryItem.objects.all()
    if q:
        items = items.filter(Q(name__icontains=q) | Q(reference__icontains=q))
    if kind:
        items = items.filter(kind=kind)
    if not show_all:
        items = items.filter(is_active=True)
    stats = item_stats()
    rows, value = [], ZERO
    for item in items.order_by(Lower("name")):
        s = stats.get(item.pk) or blank_stats()
        if s["avg_cost"] is not None and s["in_stock"] > 0:
            value += s["in_stock"] * s["avg_cost"]
        rows.append({"item": item, "s": s, "flag": stock_flag(item, s)})
    return render(request, "tracker/inventory_list.html", {
        "rows": rows,
        "q": q, "kind": kind, "show_all": show_all,
        "kinds": item_types(),
        "low_count": sum(1 for r in rows if r["flag"]),
        "stock_value": value,
    })


@permission_required("tracker.view_inventoryitem", raise_exception=True)
def item_detail(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    s = stats_for(item)
    return render(request, "tracker/item_detail.html", {
        "item": item, "s": s, "flag": stock_flag(item, s),
        "purchases": item.purchases.all()[:100],
        "usages": item.usages.select_related("task").order_by("-created_at", "-id")[:100],
        "can_see_usage": request.user.has_perm("tracker.view_taskmaterial"),
    })


def item_edit(request, pk=None):
    _allow(request, "change_inventoryitem" if pk else "add_inventoryitem")
    item = get_object_or_404(InventoryItem, pk=pk) if pk else None
    before = snapshot(item, ITEM_FIELDS) if item else None
    form = InventoryItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        after = snapshot(saved, ITEM_FIELDS)
        if item is None:
            log(request, "created", "Inventory item", saved.name, describe(after))
        elif changes(before, after):
            log(request, "updated", "Inventory item", saved.name, changes(before, after))
        return redirect("item_detail", pk=saved.pk)
    return render(request, "tracker/item_form.html", {
        "form": form,
        "kinds": item_types(),
        "page_title": f"Edit {item.name}" if item else "Add a product or material",
        "cancel_url": reverse("item_detail", args=[item.pk]) if item else reverse("inventory_list"),
    })


def item_delete(request, pk):
    _allow(request, "delete_inventoryitem")
    item = get_object_or_404(InventoryItem, pk=pk)
    used = item.usages.count()
    if used == 0 and request.method == "POST":
        name, details = item.name, describe(snapshot(item, ITEM_FIELDS))
        count = item.purchases.count()
        item.delete()
        log(request, "deleted", "Inventory item", name, f"{details}; {count} purchase(s) removed with it")
        return redirect("inventory_list")
    note = f"{item.purchases.count()} recorded purchase(s) of it will be deleted too."
    if used:
        note = (f"It can't be deleted because it was used on {used} task line(s). "
                "Untick \"Active\" when editing it to hide it instead; nothing is lost.")
    return render(request, "tracker/confirm_delete.html", {
        "object": item, "delete_note": note, "blocked": bool(used),
        "cancel_url": reverse("item_detail", args=[item.pk]),
    })


# ------------------------------------------------------------------ purchases
def purchase_edit(request, item_pk=None, pk=None):
    _allow(request, "change_purchase" if pk else "add_purchase")
    purchase = get_object_or_404(Purchase.objects.select_related("item"), pk=pk) if pk else None
    item = purchase.item if purchase else get_object_or_404(InventoryItem, pk=item_pk)
    before = snapshot(purchase, PURCHASE_FIELDS) if purchase else None
    form = PurchaseForm(request.POST or None, instance=purchase)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.item = item
        saved.save()
        after = snapshot(saved, PURCHASE_FIELDS)
        if purchase is None:
            log(request, "created", "Purchase", item.name, describe(after))
        elif changes(before, after):
            log(request, "updated", "Purchase", item.name, changes(before, after))
        return redirect("item_detail", pk=item.pk)
    return render(request, "tracker/form.html", {
        "form": form,
        "page_title": f"Edit purchase of {item.name}" if purchase else f"Record a purchase of {item.name}",
        "cancel_url": reverse("item_detail", args=[item.pk]),
    })


def purchase_delete(request, pk):
    _allow(request, "delete_purchase")
    purchase = get_object_or_404(Purchase.objects.select_related("item"), pk=pk)
    item = purchase.item
    if request.method == "POST":
        details = describe(snapshot(purchase, PURCHASE_FIELDS))
        purchase.delete()
        log(request, "deleted", "Purchase", item.name, details)
        return redirect("item_detail", pk=item.pk)
    return render(request, "tracker/confirm_delete.html", {
        "object": purchase,
        "delete_note": "The stock of this item goes down by the quantity of this purchase.",
        "cancel_url": reverse("item_detail", args=[item.pk]),
    })


# ------------------------------------------------------------------ task page and the materials used on it
@permission_required("tracker.view_task", raise_exception=True)
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.select_related("mission", "place"), pk=pk)
    can_materials = request.user.has_perm("tracker.view_taskmaterial")
    lines = list(task.materials.select_related("item")) if can_materials else []
    return render(request, "tracker/task_detail.html", {
        "task": task,
        "lines": lines,
        "can_materials": can_materials,
        "total": sum((line.line_total for line in lines), ZERO),
    })


def material_edit(request, task_pk=None, pk=None):
    _allow(request, "change_taskmaterial" if pk else "add_taskmaterial")
    line = get_object_or_404(TaskMaterial.objects.select_related("task", "item"), pk=pk) if pk else None
    task = line.task if line else get_object_or_404(Task, pk=task_pk)
    before = snapshot(line, MATERIAL_FIELDS) if line else None
    form = TaskMaterialForm(request.POST or None, instance=line, show_price=request.user.has_perm("tracker.view_costs"))
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.task = task
        if line is None:
            saved.added_by = request.user
        saved.save()
        after = snapshot(saved, MATERIAL_FIELDS)
        target = f"{task.code}: {saved.item.name}"
        if line is None:
            log(request, "created", "Material used", target, describe(after))
        elif changes(before, after):
            log(request, "updated", "Material used", target, changes(before, after))
        return redirect(_safe_next(request, reverse("task_detail", args=[task.pk])))
    return render(request, "tracker/form.html", {
        "form": form,
        "page_title": f"Edit material on {task.code}" if line else f"Add material to {task.code}",
        "cancel_url": reverse("task_detail", args=[task.pk]),
    })


def material_delete(request, pk):
    _allow(request, "delete_taskmaterial")
    line = get_object_or_404(TaskMaterial.objects.select_related("task", "item"), pk=pk)
    task = line.task
    if request.method == "POST":
        target, details = f"{task.code}: {line.item.name}", describe(snapshot(line, MATERIAL_FIELDS))
        line.delete()
        log(request, "deleted", "Material used", target, details)
        return redirect("task_detail", pk=task.pk)
    return render(request, "tracker/confirm_delete.html", {
        "object": line,
        "delete_note": "The quantity goes back into stock.",
        "cancel_url": reverse("task_detail", args=[task.pk]),
    })
