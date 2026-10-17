"""Two small guards: only local-network visitors, and a lockout after repeated wrong passwords."""
import ipaddress
import threading
import time

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import resolve_url


_TAILSCALE_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _is_tailscale(ip):
    return ip in (_TAILSCALE_V4 if ip.version == 4 else _TAILSCALE_V6)


def _is_local(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if getattr(settings, "TAILSCALE_ONLY", False):          # Wi-Fi / cable neighbours are refused outright
        return ip.is_loopback or _is_tailscale(ip)
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    return getattr(settings, "ALLOW_TAILSCALE", False) and _is_tailscale(ip)


def _host_is_local(request):
    """True if the address typed in the browser is localhost, a private IP address, or a name we trust."""
    host = request.META.get("HTTP_HOST", "").strip().lower()
    if host.startswith("["):
        host = host[1:host.find("]")] if "]" in host else host[1:]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host in settings.TRUSTED_HOSTNAMES:
            return True
        if getattr(settings, "ALLOW_TAILSCALE", False):
            # Tailscale (MagicDNS) names: "mypc" or "mypc.your-tailnet.ts.net"
            return host.endswith(".ts.net") or "." not in host
        return False
    if getattr(settings, "TAILSCALE_ONLY", False):
        return ip.is_loopback or _is_tailscale(ip)
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    return getattr(settings, "ALLOW_TAILSCALE", False) and _is_tailscale(ip)


class LocalNetworkOnlyMiddleware:
    """Answer 403 to anyone who is not on this computer or a private (home/office) network."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "LOCAL_ONLY", True) and not _is_local(request.META.get("REMOTE_ADDR", "")):
            return HttpResponseForbidden("This site is only available on the local network.", content_type="text/plain")
        if getattr(settings, "LAN_MODE", False) and not _host_is_local(request):
            return HttpResponse("Unknown address. Use the address shown when the server started.", status=400, content_type="text/plain")
        return self.get_response(request)


_lock = threading.Lock()
_failures = {}  # address -> timestamps of recent failed sign-ins (kept in memory; reset on restart)


class LoginThrottleMiddleware:
    """After too many failed sign-ins from one address, refuse further attempts for a while."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        watching = request.method == "POST" and request.path == resolve_url(settings.LOGIN_URL)
        if not watching:
            return self.get_response(request)

        address = request.META.get("REMOTE_ADDR", "")
        window = settings.LOGIN_LOCKOUT_SECONDS
        now = time.time()
        with _lock:
            recent = [t for t in _failures.get(address, []) if now - t < window]
            if recent:
                _failures[address] = recent
            else:
                _failures.pop(address, None)
            blocked = len(recent) >= settings.LOGIN_MAX_FAILURES
        if blocked:
            minutes = max(1, window // 60)
            return HttpResponse(
                f"Too many failed sign-in attempts. Wait {minutes} minutes and try again.",
                status=429,
                content_type="text/plain",
            )

        response = self.get_response(request)
        with _lock:
            if response.status_code == 200:      # the form was shown again: wrong username or password
                _failures.setdefault(address, []).append(now)
            else:                                # redirected: signed in
                _failures.pop(address, None)
        return response
