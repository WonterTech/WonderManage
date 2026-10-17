from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from . import serverctl


@login_required
def shutdown(request):
    if not serverctl.can_shutdown(request.user):
        raise PermissionDenied
    if request.method == "POST":
        backup = serverctl.shutdown_now()
        return render(request, "tracker/server_shutdown.html", {"stopped": True, "backup": backup})
    return render(request, "tracker/server_shutdown.html", {"stopped": False})
