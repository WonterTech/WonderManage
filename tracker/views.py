import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .activity import TASK_FIELDS, changes, describe, log, snapshot
from .forms import DailyLogForm, LocationForm, MissionForm, TaskForm
from .models import DailyLog, Location, Mission, Task

OPEN_STATUSES = [Task.Status.TODO, Task.Status.DOING]


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _safe_next(request, fallback=""):
    """A same-site 'next' URL from the query string or form, else the fallback."""
    target = request.GET.get("next") or request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _loc_json(loc):
    return {"id": loc.pk, "name": loc.name, "note": loc.note, "lat": loc.latitude, "lng": loc.longitude}


def _month_start(request, today):
    try:
        year, month = request.GET.get("month", "").split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return today.replace(day=1)


def _build_calendar(first, today, per_cell=3):
    """Weeks (Monday first) of day cells, each holding that day's tasks."""
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]
    by_day = defaultdict(list)
    for t in Task.objects.filter(due_date__range=(start, end)).select_related("mission", "place"):
        by_day[t.due_date].append(t)
    for tasks in by_day.values():
        tasks.sort(key=lambda t: (t.status == Task.Status.DONE, -t.priority))
    rows = []
    for week in weeks:
        cells = []
        for d in week:
            tasks = by_day.get(d, [])
            cells.append({
                "date": d,
                "in_month": d.month == first.month,
                "is_today": d == today,
                "tasks": tasks[:per_cell],
                "more": max(len(tasks) - per_cell, 0),
            })
        rows.append(cells)
    return rows


def dashboard(request):
    if not request.user.has_perm("tracker.view_task"):
        return render(request, "tracker/no_access.html")
    today = timezone.localdate()
    Status = Task.Status
    open_tasks = Task.objects.exclude(status=Status.DONE).select_related("mission", "place")

    # ---- Calendar ---------------------------------------------------------
    first = _month_start(request, today)
    weeks = _build_calendar(first, today)

    # ---- Work outside the calendar ---------------------------------------
    overdue = list(open_tasks.filter(due_date__lt=today))
    unscheduled = list(open_tasks.filter(due_date__isnull=True)[:10])
    due_today = Task.objects.filter(due_date=today).count()

    # ---- Statistics -------------------------------------------------------
    completed = list(
        Task.objects.filter(status=Status.DONE, completed_at__date__gte=today - timedelta(days=90))
        .values_list("completed_at", flat=True)
    )
    done_dates = [timezone.localtime(c).date() for c in completed]
    per_day = Counter(done_dates)

    chart_days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    peak = max([per_day[d] for d in chart_days] + [1])
    chart = [{"date": d, "count": per_day[d], "height": round(100 * per_day[d] / peak)} for d in chart_days]

    done_this_week = sum(1 for d in done_dates if d >= today - timedelta(days=6))

    due30 = Task.objects.filter(due_date__range=(today - timedelta(days=30), today))
    due30_total = due30.count()
    due30_done = list(due30.filter(status=Status.DONE, completed_at__isnull=False))
    completion_rate = _pct(len(due30_done), due30_total)
    on_time = sum(1 for t in due30_done if timezone.localtime(t.completed_at).date() <= t.due_date)
    on_time_rate = _pct(on_time, len(due30_done))

    hours_week = (
        DailyLog.objects.filter(date__gte=today - timedelta(days=6)).aggregate(s=Sum("hours_worked"))["s"] or 0
    )

    log_days = set(DailyLog.objects.filter(date__gte=today - timedelta(days=90)).values_list("date", flat=True))
    active = set(done_dates) | log_days
    cursor = today if today in active else today - timedelta(days=1)
    streak = 0
    while cursor in active:
        streak += 1
        cursor -= timedelta(days=1)

    weekday_counts = Counter(d.weekday() for d in done_dates)
    best_day = calendar.day_name[weekday_counts.most_common(1)[0][0]] if weekday_counts else None

    # ---- Mission types ----------------------------------------------------
    types = []
    for m in Mission.objects.annotate(
        open_count=Count("tasks", filter=Q(tasks__status__in=OPEN_STATUSES)),
        done_count=Count("tasks", filter=Q(tasks__status=Status.DONE)),
    ):
        total = m.open_count + m.done_count
        if total:
            types.append({"pk": m.pk, "title": m.title, "open": m.open_count,
                          "done": m.done_count, "pct": _pct(m.done_count, total) or 0})
    types.sort(key=lambda x: -x["open"])

    context = {
        "today": today,
        "weeks": weeks,
        "weekdays": [calendar.day_abbr[i] for i in range(7)],
        "month_start": first,
        "prev_month": (first - timedelta(days=1)).replace(day=1),
        "next_month": (first + timedelta(days=31)).replace(day=1),
        "is_current_month": first == today.replace(day=1),
        "overdue": overdue,
        "unscheduled": unscheduled,
        "due_today": due_today,
        "chart": chart,
        "done_this_week": done_this_week,
        "completion_rate": completion_rate,
        "on_time_rate": on_time_rate,
        "hours_week": hours_week,
        "streak": streak,
        "best_day": best_day,
        "types": types,
        "today_log": DailyLog.objects.filter(date=today).first(),
    }
    return render(request, "tracker/dashboard.html", context)


@require_POST
@permission_required("tracker.change_task", raise_exception=True)
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk)
    old_status = task.get_status_display()
    task.status = Task.Status.TODO if task.status == Task.Status.DONE else Task.Status.DONE
    task.save()
    log(request, "updated", "Task", task.code, f"status: {old_status} -> {task.get_status_display()}")
    return redirect(_safe_next(request, reverse("dashboard")))


# ---- Generic CRUD -----------------------------------------------------------
class FormPage:
    template_name = "tracker/form.html"
    page_title = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = self.page_title
        ctx["cancel_url"] = _safe_next(self.request, reverse("dashboard"))
        return ctx

    def get_success_url(self):
        return _safe_next(self.request) or super().get_success_url()


class TaskFormPage(FormPage):
    template_name = "tracker/task_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["locations"] = [_loc_json(loc) for loc in Location.objects.all()]
        return ctx


class TaskList(PermissionRequiredMixin, ListView):
    permission_required = "tracker.view_task"
    model = Task
    template_name = "tracker/task_list.html"
    context_object_name = "tasks"
    filters = {"open": "Open", "todo": "To do", "doing": "In progress", "done": "Done", "all": "All"}

    def get_queryset(self):
        qs = Task.objects.select_related("mission", "place")
        params, labels = {}, []

        self.day = None
        raw = self.request.GET.get("date", "")
        if raw:
            try:
                self.day = parse_date(raw)
            except ValueError:
                self.day = None
        if self.day:
            qs = qs.filter(due_date=self.day)
            params["date"] = self.day.isoformat()
            labels.append("due " + date_format(self.day, "l j F"))

        self.mission = None
        raw = self.request.GET.get("mission", "")
        if raw.isdigit():
            self.mission = Mission.objects.filter(pk=int(raw)).first()
        if self.mission:
            qs = qs.filter(mission=self.mission)
            params["mission"] = self.mission.pk
            labels.append(f'mission type "{self.mission.title}"')

        self.place = None
        raw = self.request.GET.get("place", "")
        if raw.isdigit():
            self.place = Location.objects.filter(pk=int(raw)).first()
        if self.place:
            qs = qs.filter(place=self.place)
            params["place"] = self.place.pk
            labels.append(f'at "{self.place.name}"')

        self.current = self.request.GET.get("status", "all" if params else "open")
        if self.current not in self.filters:
            self.current = "open"
        if self.current == "open":
            qs = qs.exclude(status=Task.Status.DONE)
        elif self.current != "all":
            qs = qs.filter(status=self.current)

        self.labels = labels
        self.extra_qs = ("&" + urlencode(params)) if params else ""
        self.add_qs = urlencode({k: v for k, v in params.items() if k in ("date", "place")})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(filters=self.filters, current=self.current, extra_qs=self.extra_qs,
                   add_qs=self.add_qs, filter_labels=self.labels)
        return ctx


class TaskLogMixin:
    """Writes the activity log whenever a task is added, changed or deleted."""

    def form_valid(self, form):
        creating = form.instance.pk is None
        before = None if creating else snapshot(Task.objects.get(pk=form.instance.pk), TASK_FIELDS)
        response = super().form_valid(form)
        after = snapshot(self.object, TASK_FIELDS)
        if creating:
            log(self.request, "created", "Task", self.object.code, describe(after))
        elif changes(before, after):
            log(self.request, "updated", "Task", self.object.code, changes(before, after))
        return response


class TaskCreate(PermissionRequiredMixin, TaskLogMixin, TaskFormPage, CreateView):
    permission_required = "tracker.add_task"
    model, form_class, success_url, page_title = Task, TaskForm, reverse_lazy("task_list"), "New task"

    def get_initial(self):
        try:
            day = parse_date(self.request.GET.get("date", ""))
        except ValueError:
            day = None
        initial = {"due_date": day or timezone.localdate()}
        raw = self.request.GET.get("place", "")
        if raw.isdigit():
            initial["place"] = int(raw)
        return initial

    def get_success_url(self):
        # Land on the new task so materials can be added straight away.
        return _safe_next(self.request) or reverse("task_detail", args=[self.object.pk])


class TaskUpdate(PermissionRequiredMixin, TaskLogMixin, TaskFormPage, UpdateView):
    permission_required = "tracker.change_task"
    model, form_class, success_url, page_title = Task, TaskForm, reverse_lazy("task_list"), "Edit task"


class TaskDelete(PermissionRequiredMixin, DeleteView):
    permission_required = "tracker.delete_task"
    model, success_url = Task, reverse_lazy("task_list")
    template_name = "tracker/confirm_delete.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lines = self.object.materials.count()
        if lines:
            ctx["delete_note"] = f"The {lines} material line(s) recorded on it are removed too, so that stock goes back up."
        return ctx

    def form_valid(self, form):
        task = self.object
        label, lines = task.code, task.materials.count()
        details = describe(snapshot(task, TASK_FIELDS))
        if lines:
            details += f"; {lines} material line(s) removed with it"
        response = super().form_valid(form)
        log(self.request, "deleted", "Task", label, details)
        return response


class MissionList(PermissionRequiredMixin, ListView):
    permission_required = "tracker.view_mission"
    model = Mission
    template_name = "tracker/mission_list.html"
    context_object_name = "missions"

    def get_queryset(self):
        return Mission.objects.annotate(
            open_count=Count("tasks", filter=Q(tasks__status__in=OPEN_STATUSES), distinct=True),
            done_count=Count("tasks", filter=Q(tasks__status=Task.Status.DONE), distinct=True),
        )


class MissionCreate(PermissionRequiredMixin, FormPage, CreateView):
    permission_required = "tracker.add_mission"
    model, form_class, success_url, page_title = Mission, MissionForm, reverse_lazy("mission_list"), "New mission"


class MissionUpdate(PermissionRequiredMixin, FormPage, UpdateView):
    permission_required = "tracker.change_mission"
    model, form_class, success_url, page_title = Mission, MissionForm, reverse_lazy("mission_list"), "Rename mission"


class MissionDelete(PermissionRequiredMixin, DeleteView):
    permission_required = "tracker.delete_mission"
    model, success_url = Mission, reverse_lazy("mission_list")
    template_name = "tracker/confirm_delete.html"


class LocationList(PermissionRequiredMixin, ListView):
    permission_required = "tracker.view_location"
    model = Location
    template_name = "tracker/location_list.html"
    context_object_name = "locations"

    def get_queryset(self):
        return Location.objects.annotate(
            open_count=Count("tasks", filter=Q(tasks__status__in=OPEN_STATUSES)),
            done_count=Count("tasks", filter=Q(tasks__status=Task.Status.DONE)),
            client_document_count=Count("client_documents", distinct=True),
            supplier_purchase_count=Count("supplier_purchases", distinct=True),
        ).order_by(Lower("name"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        upcoming = defaultdict(list)
        open_here = (
            Task.objects.filter(place__isnull=False)
            .exclude(status=Task.Status.DONE)
            .order_by(F("due_date").asc(nulls_last=True), "-priority")
        )
        for t in open_here:
            if len(upcoming[t.place_id]) < 5:
                upcoming[t.place_id].append(
                    {"title": t.display_title, "due": t.due_date.isoformat() if t.due_date else None}
                )
        ctx["map_data"] = [
            dict(
                _loc_json(p), open=p.open_count, done=p.done_count, tasks=upcoming.get(p.pk, []),
                clients=list(p.client_documents.order_by("-date").values_list("client_name", flat=True).distinct()[:4]),
                suppliers=list(
                    p.supplier_purchases.exclude(supplier="").order_by("-date")
                    .values_list("supplier", flat=True).distinct()[:4]
                ),
            )
            for p in ctx["locations"]
        ]
        user = self.request.user
        ctx["map_urls"] = {
            "tasks": reverse("task_list"),
            "newTask": reverse("task_create"),
            "canAdd": user.has_perm("tracker.add_location"),
            "canEdit": user.has_perm("tracker.change_location"),
            "canViewTasks": user.has_perm("tracker.view_task"),
            "canAddTask": user.has_perm("tracker.add_task"),
        }
        return ctx


@require_POST
def location_save(request, pk=None):
    """Create or update a location. Returns JSON so it can be used from a popup without leaving the page."""
    needed = "tracker.change_location" if pk else "tracker.add_location"
    if not request.user.has_perm(needed):
        return JsonResponse({"ok": False, "error": "You don't have permission to do that."}, status=403)
    instance = get_object_or_404(Location, pk=pk) if pk else None
    form = LocationForm(request.POST, instance=instance)
    if form.is_valid():
        return JsonResponse({"ok": True, "location": _loc_json(form.save())})
    message = " ".join(" ".join(errors) for errors in form.errors.values())
    return JsonResponse({"ok": False, "error": message}, status=400)


class LocationDelete(PermissionRequiredMixin, DeleteView):
    permission_required = "tracker.delete_location"
    model, success_url = Location, reverse_lazy("location_list")
    template_name = "tracker/confirm_delete.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["delete_note"] = "Tasks at this place are kept, but they will no longer have a location."
        return ctx


class LogList(PermissionRequiredMixin, ListView):
    permission_required = "tracker.view_dailylog"
    model = DailyLog
    template_name = "tracker/log_list.html"
    context_object_name = "logs"


class LogUpdate(PermissionRequiredMixin, FormPage, UpdateView):
    permission_required = "tracker.change_dailylog"
    model, form_class, success_url, page_title = DailyLog, DailyLogForm, reverse_lazy("log_list"), "Daily log"


class LogDelete(PermissionRequiredMixin, DeleteView):
    permission_required = "tracker.delete_dailylog"
    model, success_url = DailyLog, reverse_lazy("log_list")
    template_name = "tracker/confirm_delete.html"


def _line(task):
    return f"- {task.display_title}" + (f" ({task.place.name})" if task.place else "")


@permission_required("tracker.add_dailylog", raise_exception=True)
def log_today(request):
    """Open today's log for editing, creating it (pre-filled) if it doesn't exist yet."""
    today = timezone.localdate()
    log, created = DailyLog.objects.get_or_create(date=today)
    if created:
        finished = Task.objects.filter(status=Task.Status.DONE, completed_at__date=today).select_related("place")
        missed = Task.objects.exclude(status=Task.Status.DONE).filter(due_date=today).select_related("place")
        log.done = "\n".join(_line(t) for t in finished)
        log.not_done = "\n".join(_line(t) for t in missed)
        log.save()
    return redirect("log_update", pk=log.pk)
