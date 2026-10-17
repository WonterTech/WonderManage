from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from . import branding
from .forms import BrandingForm
from .manage_views import manager_required
from .models import SiteSettings


@manager_required
def branding_edit(request):
    site = SiteSettings.load()
    initial = {
        "site_name": site.site_name,
        "currency": site.currency,
        "palette": site.palette,
        "custom_color": site.custom_color,
    }
    form = BrandingForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        site.site_name = data["site_name"]
        site.currency = data["currency"]
        site.palette = data["palette"]
        if data["custom_color"]:
            site.custom_color = data["custom_color"]
        if data.get("logo"):
            site.logo_data, site.logo_type = form.logo_bytes, form.logo_type
        elif data["remove_logo"]:
            site.logo_data, site.logo_type = None, ""
        site.save()
        return redirect(reverse("branding") + "?saved=1")
    return render(request, "tracker/branding.html", {
        "form": form,
        "palettes": branding.palette_options(),
        "has_logo": bool(site.logo_data),
        "saved": request.GET.get("saved") == "1",
        "default_name": branding.DEFAULT_NAME,
    })


def logo(request):
    """The logo image. Open to everyone because the sign-in page shows it too."""
    site = SiteSettings.current()
    if not site.logo_data:
        raise Http404
    response = HttpResponse(bytes(site.logo_data), content_type=site.logo_type)
    response["Cache-Control"] = "public, max-age=86400"
    return response
