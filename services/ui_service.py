"""
Fré Pathé v1.7.0 - UI Service
Handles template rendering, static file helpers, and UI utilities.
"""
from pathlib import Path
from typing import Dict, Any

from .config import BASE, DATA
from .styles import STYLE_PRESETS

# ========= Paths =========
TEMPLATES_DIR = BASE / "templates"
STATIC_DIR = BASE / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"
STYLE_CSS_PATH = STATIC_DIR / "style.css"
APP_JS_PATH = STATIC_DIR / "app.js"
LOGO_PATH = STATIC_DIR / "logo.png"

# Default audio analysis prompt
DEFAULT_AUDIO_PROMPT = """Analyze this audio for visual storytelling.
Return a JSON object with:
- title: A compelling title
- audio_dna: mood, tempo, energy_curve, key_moments
- suggested_scenes: array of scene suggestions"""


# ========= Template Builders =========

def get_style_options_html() -> str:
    """Generate HTML options for style preset dropdown."""
    return "\n".join([f'<option value="{k}">{v["label"]}</option>' for k, v in STYLE_PRESETS.items()])


def build_index_html() -> str:
    """Build the main index.html with injected values."""
    tpl = INDEX_HTML_PATH.read_text(encoding="utf-8")
    style_opts = get_style_options_html()
    return (tpl
            .replace("__STYLE_OPTIONS__", style_opts)
            .replace("__DEFAULT_AUDIO_PROMPT__", DEFAULT_AUDIO_PROMPT.replace("`", "'")))


def get_app_js_content() -> str:
    """Get app.js content with injected values."""
    js = APP_JS_PATH.read_text(encoding="utf-8")
    return js.replace("__DEFAULT_AUDIO_PROMPT__", DEFAULT_AUDIO_PROMPT.replace("`", "'"))


def get_media_type(filepath: str) -> str:
    """Determine media type from file extension."""
    if filepath.endswith(".jpg") or filepath.endswith(".jpeg"):
        return "image/jpeg"
    elif filepath.endswith(".webp"):
        return "image/webp"
    elif filepath.endswith(".mp4"):
        return "video/mp4"
    elif filepath.endswith(".mp3"):
        return "audio/mpeg"
    elif filepath.endswith(".css"):
        return "text/css"
    elif filepath.endswith(".js"):
        return "application/javascript"
    return "image/png"
