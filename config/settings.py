import os
import shutil
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Where your data lives
# ---------------------------------------------------------------------------
# Everything private (database, secret key, backups) is kept in ONE folder:
#     <project folder>/data/
# Move it somewhere else by setting the WORKLOG_DATA_DIR environment variable.
DATA_DIR = Path(os.environ.get("WORKLOG_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "db.sqlite3"

# Older versions kept the database next to manage.py. Copy it over once so nothing is lost.
_legacy_db = BASE_DIR / "db.sqlite3"
if _legacy_db.exists() and not DB_PATH.exists():
    shutil.copy2(_legacy_db, DB_PATH)


def _load_secret_key():
    """Use WORKLOG_SECRET_KEY if set; otherwise create a random key once and keep it in data/."""
    from_env = os.environ.get("WORKLOG_SECRET_KEY")
    if from_env:
        return from_env
    key_file = DATA_DIR / "secret_key.txt"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(64)
    key_file.write_text(key)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return key


SECRET_KEY = _load_secret_key()

# ---------------------------------------------------------------------------
# Safe by default
# ---------------------------------------------------------------------------
# DEBUG shows detailed error pages, so it is OFF unless you ask for it: WORKLOG_DEBUG=1
DEBUG = os.environ.get("WORKLOG_DEBUG") == "1"

# serve.py --lan sets WORKLOG_LAN=1. Your computer's network address can change (or not exist yet when
# Windows is still connecting to Wi-Fi at start-up), so in that mode Django accepts any Host header and
# tracker.security checks it instead: only IP addresses on a private network, "localhost", or names you list.
LAN_MODE = os.environ.get("WORKLOG_LAN") == "1"
_extra_hosts = [h.strip() for h in os.environ.get("WORKLOG_ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS = ["*"] if LAN_MODE else ["localhost", "127.0.0.1", "[::1]"] + _extra_hosts
# The friendly name other devices type instead of an IP address: http://wondermanage.local
SERVER_NAME = os.environ.get("WORKLOG_NAME", "wondermanage").lower()
TRUSTED_HOSTNAMES = {"localhost", SERVER_NAME, SERVER_NAME + ".local"} | {h.lower() for h in _extra_hosts}

# Refuse any visitor whose address is not this computer or a private home/office network address.
LOCAL_ONLY = os.environ.get("WORKLOG_LOCAL_ONLY", "1") != "0"

# serve.py --tailscale sets WORKLOG_TAILSCALE=1: also accept visitors coming through your Tailscale network
# (addresses 100.64.0.0/10 and *.ts.net names), so you can reach the site from anywhere with Tailscale on.
ALLOW_TAILSCALE = os.environ.get("WORKLOG_TAILSCALE") == "1"
# Tailscale ONLY: devices on the Wi-Fi / cable are refused; only this computer and Tailscale (encrypted, authenticated).
TAILSCALE_ONLY = os.environ.get("WORKLOG_TAILSCALE_ONLY") == "1"

# Lock sign-in for a while after too many wrong passwords from one address.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

# Automatic backups made by serve.py (only when the data changed): at start, then every N hours.
BACKUP_EVERY_HOURS = 12
BACKUP_KEEP = 40            # how many backup files to keep in data/backups/

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tracker",
]

MIDDLEWARE = [
    "tracker.security.LocalNetworkOnlyMiddleware",
    "tracker.security.LoginThrottleMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tracker.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "tracker.context.map_config",
        "tracker.context.server_control",
        "tracker.context.branding",
    ]},
}]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        "OPTIONS": {"timeout": 20},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # filled by `collectstatic`, served by WhiteNoise
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Where the map opens when you have no saved pins yet: [latitude, longitude] and zoom level.
MAP_DEFAULT_CENTER = [36.8065, 10.1815]
MAP_DEFAULT_ZOOM = 12

# Map tile servers (OpenStreetMap) reject requests that carry no Referer header.
# Django's default policy is "same-origin", which hides it, so allow the origin to be sent.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Map tiles. If OpenStreetMap still blocks you, swap in another provider, e.g. CARTO:
# MAP_TILE_URL = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
# MAP_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
MAP_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

# Sign-in
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Sessions and cookies
SESSION_COOKIE_AGE = 12 * 60 * 60          # signed out after 12 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# Cookies are NOT marked "secure" on plain http, because a secure cookie would never be sent back and nobody could
# sign in. When serve.py runs with HTTPS (network.bat option 5) they are, and browsers are told to insist on https.
HTTPS = os.environ.get("WORKLOG_HTTPS") == "1"
if HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 7 * 24 * 3600   # a week: short on purpose, so turning https off later does not lock you out for long

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
