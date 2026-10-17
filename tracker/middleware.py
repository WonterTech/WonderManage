from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import resolve_url


class LoginRequiredMiddleware:
    """Send anyone who is not signed in to the login page (the Django admin has its own login)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not self._exempt(request.path):
            return redirect_to_login(request.get_full_path(), resolve_url(settings.LOGIN_URL))
        return self.get_response(request)

    @staticmethod
    def _exempt(path):
        static_prefix = "/" + settings.STATIC_URL.lstrip("/")
        return (
            path == resolve_url(settings.LOGIN_URL)
            or path == "/branding/logo/"
            or path.startswith("/admin/")
            or path.startswith(static_prefix)
        )
