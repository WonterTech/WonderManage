from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import access
from .forms import UserForm

User = get_user_model()


def manager_required(view):
    return permission_required("tracker.manage_users", raise_exception=True)(view)


def _editable_by(actor, target):
    """Only superusers may touch superuser accounts."""
    return actor.is_superuser or not target.is_superuser


# ---------------------------------------------------------------- users
@manager_required
def user_list(request):
    rows = []
    for u in User.objects.prefetch_related("groups").order_by("username"):
        groups = list(u.groups.all())
        rows.append({
            "u": u,
            "role": groups[0].name if groups else None,
            "can_edit": _editable_by(request.user, u),
            "is_me": u.pk == request.user.pk,
        })
    return render(request, "tracker/user_list.html", {"rows": rows})


@manager_required
def user_edit(request, pk=None):
    target = get_object_or_404(User, pk=pk) if pk else None
    if target and not _editable_by(request.user, target):
        raise PermissionDenied
    form = UserForm(request.POST or None, instance=target, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("user_list")
    return render(request, "tracker/form.html", {
        "form": form,
        "page_title": f"Edit {target.username}" if target else "Add user",
        "cancel_url": reverse("user_list"),
    })


@manager_required
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk or not _editable_by(request.user, target):
        raise PermissionDenied
    if request.method == "POST":
        target.delete()
        return redirect("user_list")
    return render(request, "tracker/confirm_delete.html", {
        "object": target,
        "delete_note": "They will no longer be able to sign in. Tasks and logs are shared, so none of them are removed.",
        "cancel_url": reverse("user_list"),
    })


# ---------------------------------------------------------------- roles
@manager_required
def role_list(request):
    roles = list(Group.objects.annotate(user_count=Count("user")).order_by("name"))
    granted = {
        g.pk: set(g.permissions.filter(content_type__app_label="tracker").values_list("codename", flat=True))
        for g in roles
    }
    areas = []
    for area in access.AREAS:
        rows = [
            {"label": label, "cells": [code in granted[g.pk] for g in roles]}
            for code, label, _help in area["perms"]
        ]
        areas.append({"title": area["title"], "rows": rows})
    return render(request, "tracker/role_list.html", {"roles": roles, "areas": areas})


@manager_required
def role_edit(request, pk=None):
    role = get_object_or_404(Group, pk=pk) if pk else None
    available = {
        p.codename: p
        for p in Permission.objects.filter(content_type__app_label="tracker", codename__in=access.ALL_CODENAMES)
    }
    name = role.name if role else ""
    current = set(role.permissions.values_list("codename", flat=True)) if role else set()
    error = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        chosen = {c for c in request.POST.getlist("permissions") if c in available}
        # Allowing any action in an area always includes seeing that area.
        for area in access.AREAS:
            view = area["view"]
            if view and any(code in chosen for code, _l, _h in area["perms"] if code != view):
                chosen.add(view)
        current = chosen
        clash = Group.objects.filter(name__iexact=name)
        if role:
            clash = clash.exclude(pk=role.pk)
        if not name:
            error = "Give the role a name."
        elif clash.exists():
            error = "A role with this name already exists."
        elif (
            role and not request.user.is_superuser
            and request.user.groups.filter(pk=role.pk).exists()
            and "manage_users" not in chosen
        ):
            error = "You can't remove your own access to user management."
        if not error:
            if role:
                role.name = name
                role.save()
                others = list(role.permissions.exclude(pk__in=[p.pk for p in available.values()]))
            else:
                role = Group.objects.create(name=name)
                others = []
            role.permissions.set(others + [available[c] for c in chosen])
            return redirect("role_list")

    areas = [
        {
            "title": area["title"],
            "view": area["view"],
            "items": [
                {"code": code, "label": label, "help": help_text, "checked": code in current}
                for code, label, help_text in area["perms"]
            ],
        }
        for area in access.AREAS
    ]
    return render(request, "tracker/role_form.html", {
        "role": role, "name": name, "areas": areas, "error": error,
        "page_title": f"Edit role: {role.name}" if role else "Add role",
    })


@manager_required
def role_delete(request, pk):
    role = get_object_or_404(Group, pk=pk)
    if not request.user.is_superuser and request.user.groups.filter(pk=role.pk).exists():
        raise PermissionDenied
    count = role.user_set.count()
    if request.method == "POST":
        role.delete()
        return redirect("role_list")
    return render(request, "tracker/confirm_delete.html", {
        "object": role,
        "delete_note": f"{count} user{'s' if count != 1 else ''} with this role will be left without a role and won't see anything until you give them another.",
        "cancel_url": reverse("role_list"),
    })
