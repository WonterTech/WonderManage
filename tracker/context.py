from django.conf import settings


def map_config(request):
    return {
        "map_config": {
            "center": list(getattr(settings, "MAP_DEFAULT_CENTER", [36.8065, 10.1815])),
            "zoom": getattr(settings, "MAP_DEFAULT_ZOOM", 12),
            "tileUrl": getattr(settings, "MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
            "attribution": getattr(
                settings,
                "MAP_ATTRIBUTION",
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            ),
        }
    }


def server_control(request):
    from .serverctl import can_shutdown

    return {"can_shutdown": can_shutdown(request.user)}


def branding(request):
    from .branding import brand_context

    return {"brand": brand_context()}
