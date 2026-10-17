"""Site name, logo and colours that an administrator can change (per installation)."""
import re

DEFAULT_NAME = "Work log"
MAX_LOGO_BYTES = 1024 * 1024   # 1 MB

# Named palettes: just the main colour; the page colours are worked out from it.
PALETTES = {
    "ocean": ("Ocean", "#1d4ed8"),
    "teal": ("Teal", "#0f766e"),
    "forest": ("Forest", "#166534"),
    "gold": ("Gold", "#a16207"),
    "sunset": ("Sunset", "#c2410c"),
    "rose": ("Rose", "#be123c"),
    "berry": ("Berry", "#7e22ce"),
    "slate": ("Slate", "#334155"),
}
ORIGINAL = ("original", "Original", "#0f6e6e")   # the look the site always had: no overrides
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def palette_options():
    """[{key, name, color}] for the settings page (custom is handled separately there)."""
    opts = [{"key": ORIGINAL[0], "name": ORIGINAL[1], "color": ORIGINAL[2]}]
    opts += [{"key": k, "name": n, "color": c} for k, (n, c) in PALETTES.items()]
    return opts


def valid_keys():
    return [o["key"] for o in palette_options()] + ["custom"]


# ------------------------------------------------------------------ colour maths
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def tint(color, weight, over):
    """`weight` of `color` laid over the `over` colour (0 = all over, 1 = all color)."""
    c, o = _rgb(color), _rgb(over)
    return _hex(tuple(o[i] * (1 - weight) + c[i] * weight for i in range(3)))


def _luminance(h):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ink_for(color):
    """White or near-black text, whichever reads better on `color`."""
    return "#ffffff" if _contrast(color, "#ffffff") >= _contrast(color, "#0b1418") else "#0b1418"


def accent_for(palette, custom_color):
    if palette == "custom" and HEX.match(custom_color or ""):
        return custom_color.lower()
    if palette in PALETTES:
        return PALETTES[palette][1]
    return None   # "original"


def palette_css(palette, custom_color):
    """CSS that overrides the colour variables. Built only from validated hex values."""
    base = accent_for(palette, custom_color)
    if not base:
        return ""
    white, night = "#ffffff", "#0d1114"
    dark_accent = tint(base, 0.62, white)
    light = (f"--bg:{tint(base, .08, white)};--panel:{tint(base, .03, white)};--line:{tint(base, .22, white)};"
             f"--soft:{tint(base, .14, white)};--accent:{base};--accent-ink:{ink_for(base)};")
    dark = (f"--bg:{tint(base, .10, night)};--panel:{tint(base, .15, night)};--line:{tint(base, .28, night)};"
            f"--soft:{tint(base, .22, night)};--accent:{dark_accent};--accent-ink:{ink_for(dark_accent)};")
    return f":root{{{light}}}@media (prefers-color-scheme: dark){{:root{{{dark}}}}}"


# ------------------------------------------------------------------ logo files
def detect_image_type(data):
    """Work out the image type from the file's own first bytes (never trust the file name)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ------------------------------------------------------------------ what every page receives
def brand_context():
    from .models import SiteSettings

    try:
        site = SiteSettings.current()
    except Exception:   # e.g. the database has not been updated yet: fall back to the defaults
        return {"name": DEFAULT_NAME, "logo_url": "", "css": "", "currency": ""}
    logo_url = ""
    if site.logo_data:
        logo_url = f"/branding/logo/?v={int(site.updated_at.timestamp())}"
    return {
        "name": site.site_name or DEFAULT_NAME,
        "logo_url": logo_url,
        "css": palette_css(site.palette, site.custom_color),
        "currency": site.currency,
    }
