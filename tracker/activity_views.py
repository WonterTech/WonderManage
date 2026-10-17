from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_date

from .models import ActivityLog

KINDS = ["Task", "Material used", "Inventory item", "Purchase"]
ACTIONS = [("created", "Added"), ("updated", "Changed"), ("deleted", "Deleted")]


def _date(raw):
    try:
        return parse_date(raw) if raw else None
    except ValueError:
        return None


@permission_required("tracker.view_activitylog", raise_exception=True)
def activity_list(request):
    entries = ActivityLog.objects.all()
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    action = request.GET.get("action", "")
    who = request.GET.get("user", "")
    start, end = _date(request.GET.get("from")), _date(request.GET.get("to"))
    if q:
        entries = entries.filter(Q(target__icontains=q) | Q(details__icontains=q))
    if kind in KINDS:
        entries = entries.filter(kind=kind)
    if action in dict(ACTIONS):
        entries = entries.filter(action=action)
    if who:
        entries = entries.filter(username=who)
    if start:
        entries = entries.filter(when__date__gte=start)
    if end:
        entries = entries.filter(when__date__lte=end)
    page = Paginator(entries, 50).get_page(request.GET.get("page"))
    keep = request.GET.copy()
    keep.pop("page", None)
    return render(request, "tracker/activity_list.html", {
        "page": page,
        "q": q, "kind": kind, "action": action, "who": who,
        "start": start.isoformat() if start else "", "end": end.isoformat() if end else "",
        "kinds": KINDS, "actions": ACTIONS,
        "users": ActivityLog.objects.exclude(username="").order_by("username").values_list("username", flat=True).distinct(),
        "keep_qs": keep.urlencode(),
    })
