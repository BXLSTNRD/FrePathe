# Fré Pathé Services - Configuration & Shared State
# v1.7.0: Extracted from main.py

import os
import re
import json
import time
import uuid
import asyncio
import threading
import requests
import fal_client
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

# ========= Version =========
VERSION = "1.8.8"

# ========= Threading Locks =========
PROJECT_LOCKS: Dict[str, threading.Lock] = {}
PROJECT_LOCKS_LOCK = threading.Lock()

def get_project_lock(project_id: str) -> threading.Lock:
    """Get or create a lock for a specific project."""
    with PROJECT_LOCKS_LOCK:
        if project_id not in PROJECT_LOCKS:
            PROJECT_LOCKS[project_id] = threading.Lock()
        return PROJECT_LOCKS[project_id]

# ========= Storage Paths =========
BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CONTRACTS_DIR = BASE / "Contracts"

# Legacy paths (for backwards compatibility - use PathManager instead)
PROJECTS_DIR = DATA / "projects"
UPLOADS_DIR = DATA / "uploads"
RENDERS_DIR = DATA / "renders"
DEBUG_DIR = DATA / "debug"

# Create default directories
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ========= Path Manager (User-configurable workspace) =========
def get_path_manager():
    """
    Get PathManager instance with user settings.
    Lazy import to avoid circular dependencies.
    """
    from .settings_service import get_workspace_root
    from .path_service import PathManager
    
    workspace_root = get_workspace_root()
    return PathManager(workspace_root)

# Global PathManager instance
PATH_MANAGER = None

def init_path_manager():
    """Initialize global PathManager instance."""
    global PATH_MANAGER
    PATH_MANAGER = get_path_manager()
    return PATH_MANAGER

# Initialize on module load
PATH_MANAGER = init_path_manager()

# ========= Export Status (in-memory) =========
EXPORT_STATUS: Dict[str, Dict[str, Any]] = {}

# ========= API Keys =========
FAL_KEY = os.environ.get("FAL_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
CLAUDE_KEY = os.environ.get("CLAUDE_KEY", "").strip()

# ========= FAL Endpoints =========
FAL_BASE = "https://fal.run"
FAL_AUDIO = f"{FAL_BASE}/fal-ai/audio-understanding"
FAL_FLUX2_T2I = f"{FAL_BASE}/fal-ai/flux-2"
FAL_SEEDREAM45_T2I = f"{FAL_BASE}/fal-ai/bytedance/seedream/v4.5/text-to-image"
FAL_NANOBANANA_PRO_T2I = f"{FAL_BASE}/fal-ai/nano-banana-pro"
FAL_FLUX2_EDIT = f"{FAL_BASE}/fal-ai/flux-2/edit"
FAL_NANOBANANA_EDIT = f"{FAL_BASE}/fal-ai/nano-banana-pro/edit"
FAL_SEEDREAM45_EDIT = f"{FAL_BASE}/fal-ai/bytedance/seedream/v4.5/edit"

# Image-to-Video (img2vid)
FAL_LTX2_I2V = f"{FAL_BASE}/fal-ai/ltx-2-19b/distilled/image-to-video/lora"
FAL_KLING_I2V = f"{FAL_BASE}/fal-ai/kling-video/v2.6/pro/image-to-video"
FAL_VEO31_I2V = f"{FAL_BASE}/fal-ai/veo3.1/fast/image-to-video"
FAL_WAN_I2V = f"{FAL_BASE}/wan/v2.6/image-to-video"
FAL_HAILUO_I2V = f"{FAL_BASE}/fal-ai/minimax/hailuo-2.3/pro/image-to-video"
FAL_KANDINSKY5_I2V = f"{FAL_BASE}/fal-ai/kandinsky5-pro/image-to-video"

# ========= Cost Tracking =========
API_COSTS = {
    # Audio (FAL pricing Jan 2026)
    # audio-understanding: $0.01 per 5-second unit
    "fal-ai/audio-understanding": 0.01,
    # : $0.0013 per compute second (roughly = audio duration)
    "fal-ai/": 0.0013,
    # Text-to-Image
    "fal-ai/nano-banana-pro": 0.15,
    "fal-ai/flux/dev": 0.025,
    "fal-ai/flux-1/dev": 0.025,
    "fal-ai/flux-2": 0.012,
    "fal-ai/flux-pro/v1.1": 0.04,
    "fal-ai/recraft/v3": 0.04,
    "fal-ai/bytedance/seedream/v4.5/text-to-image": 0.04,
    # Image-to-Image
    "fal-ai/nano-banana-pro/edit": 0.15,
    "fal-ai/flux/dev/image-to-image": 0.025,
    "fal-ai/flux-2/edit": 0.012,
    "fal-ai/bytedance/seedream/v4.5/edit": 0.04,
    "fal-ai/kontext/edit": 0.05,
    # Internal mappings
    "fal-ai/nanobanana_edit": 0.15,
    "fal-ai/flux2_edit": 0.012,
    "fal-ai/seedream45_edit": 0.04,
    "fal-ai/kontext_edit": 0.05,
    # Image-to-Video (estimated Jan 2026 pricing)
    "fal-ai/ltx-2-19b/distilled/image-to-video/lora": 0.10,
    "fal-ai/kling-video/v2.6/pro/image-to-video": 0.25,
    "fal-ai/veo3.1/fast/image-to-video": 0.12,
    "wan/v2.6/image-to-video": 0.15,
    "fal-ai/minimax/hailuo-2.3/pro/image-to-video": 0.18,
    "fal-ai/kandinsky5-pro/image-to-video": 0.08,
    # LLM
    "claude-sonnet-4-5-20250929": 0.02,
    "claude-3-5-sonnet-latest": 0.015,
    "claude-3-5-sonnet-20241022": 0.015,
    "claude-3-haiku-20240307": 0.002,
    "gpt-4o-mini": 0.001,

    # OpenAI Speech-to-Text (pricing per minute; see OpenAI pricing docs)
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
    "whisper-1": 0.006,
    # Default
    "default": 0.05,
}

MODEL_TO_ENDPOINT = {
    "nanobanana_edit": "fal-ai/nano-banana-pro/edit",
    "flux2_edit": "fal-ai/flux-2/edit",
    "seedream45_edit": "fal-ai/bytedance/seedream/v4.5/edit",
    "kontext_edit": "fal-ai/kontext/edit",
    "nano-banana-pro": "fal-ai/nano-banana-pro",
    "flux-dev": "fal-ai/flux/dev",
    "flux-pro": "fal-ai/flux-pro/v1.1",
    "recraft-v3": "fal-ai/recraft/v3",
    "seedream45": "fal-ai/bytedance/seedream/v4.5/text-to-image",
    # Image-to-Video
    "ltx2_i2v": "fal-ai/ltx-2-19b/image-to-video",
    "kling_i2v": "fal-ai/kling-video/v2.6/pro/image-to-video",
    "veo31_i2v": "fal-ai/veo3.1/image-to-video",
    "wan_i2v": "wan/v2.6/image-to-video",
}

SESSION_COST = {"total": 0.0, "calls": []}
PRICING_LOADED = False

# ========= Render Concurrency =========
RENDER_SEMAPHORE = asyncio.Semaphore(6)
VIDEO_SEMAPHORE = asyncio.Semaphore(8)  # v1.8.2: Video generation concurrency (max 20, using 8)

# ========= Model Aliases =========
FAL_NANOBANANA = FAL_NANOBANANA_PRO_T2I
FAL_SEEDREAM45 = FAL_SEEDREAM45_T2I
FAL_FLUX2 = FAL_FLUX2_T2I

# ========= Locked Render Models =========
def locked_render_models(image_model_choice: str) -> Dict[str, Any]:
    """
    Hard-lock render models for ALL still images based on project image generator selection.
    UI values: nanobanana | seedream45 | flux2
    """
    m = (image_model_choice or "nanobanana").strip().lower()
    if m in ("flux2", "flux_2"):
        return {
            "image_model": "fal-ai/flux-2",
            "identity_model": None,
            "img2img_editor": "flux2_edit",
            "available_editors": ["flux2_edit", "nanobanana_edit", "seedream45_edit"],
        }
    if m in ("seedream45", "seedream_45", "seedream", "seedream4.5", "seedream4_5"):
        return {
            "image_model": "fal-ai/bytedance/seedream/v4.5/text-to-image",
            "identity_model": None,
            "img2img_editor": "seedream45_edit",
            "available_editors": ["seedream45_edit", "nanobanana_edit", "flux2_edit"],
        }
    # default: Nano Banana Pro
    return {
        "image_model": "fal-ai/nano-banana-pro",
        "identity_model": None,
        "img2img_editor": "nanobanana_edit",
        "available_editors": ["nanobanana_edit", "seedream45_edit", "flux2_edit"],
    }


def locked_editor_key(state: Dict[str, Any]) -> str:
    """Get the locked img2img editor key for a project."""
    rm = (state.get("project") or {}).get("render_models") or {}
    return (rm.get("img2img_editor") or "nanobanana_edit").strip()


def locked_model_key(state: Dict[str, Any]) -> str:
    """Get the locked text-to-image model key for a project."""
    rm = state.get("project", {}).get("render_models") or {}
    return rm.get("image_model", "nanobanana")


# ========= Storyboard Heuristics =========
SHOTS_PER_180S = 70
SEQ_MIN, SEQ_MAX = 6, 10
SHOTS_PER_SEQ_MIN, SHOTS_PER_SEQ_MAX = 5, 8

DEFAULT_AUDIO_PROMPT = (
    "I need you to transcribe the lyrics (timecoded); "
    "I need BPM; I need Style; "
    "I need the Structure (timecoded); Dynamics (timecoded); "
    "Vocal delivery and the Story/Arch"
)

# ========= Helper Functions =========
def require_key(name: str, value: str):
    """Raise HTTPException if key is missing."""
    from fastapi import HTTPException
    if not value:
        raise HTTPException(500, f"Missing {name}. Put it in env var {name} and restart.")

def fal_headers() -> Dict[str, str]:
    """Get FAL API headers."""
    require_key("FAL_KEY", FAL_KEY)
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}

def now_iso() -> str:
    """Current ISO timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, x))

def safe_float(x, default=0.0) -> float:
    """Safe float conversion."""
    try:
        return float(x)
    except Exception:
        return float(default)

def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Convert string to safe filename."""
    if not name:
        return "unnamed"
    safe = re.sub(r'[\s\-\.]+', '_', name)
    safe = re.sub(r'[^a-zA-Z0-9_]', '', safe)
    safe = re.sub(r'_+', '_', safe)
    safe = safe.strip('_')
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('_')
    return safe or "unnamed"

def normalize_structure_type(s: str) -> str:
    """Normalize song structure type."""
    if not s:
        return "verse"
    t = s.strip().lower()
    for k in ["intro", "verse", "prechorus", "chorus", "bridge", "breakdown", "outro", "instrumental"]:
        if t.startswith(k):
            return k
    if t.startswith("pre-chorus") or t.startswith("pre chorus"):
        return "prechorus"
    return "verse"

# ========= Retry Helper =========
def retry_on_502(func: Callable, max_retries: int = 3, delay: float = 2.0):
    """Retry function on 5xx errors with exponential backoff."""
    from fastapi import HTTPException
    
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except HTTPException as e:
                if e.status_code >= 500 and attempt < max_retries - 1:
                    wait = delay * (2 ** attempt)
                    print(f"[WARN] {e.status_code} error, retry {attempt+1}/{max_retries} in {wait:.1f}s")
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait = delay * (2 ** attempt)
                    print(f"[WARN] Request error, retry {attempt+1}/{max_retries} in {wait:.1f}s")
                    time.sleep(wait)
                    last_error = e
                else:
                    raise HTTPException(502, f"Request failed after {max_retries} retries: {str(e)[:200]}")
        raise last_error or HTTPException(502, "Max retries exceeded")
    return wrapper

# ========= Cost Tracking =========
def track_cost(model: str, count: int = 1, project_id: str = None, state: Dict = None, note: str = None):
    """Track API costs. Optional note for identifying the call type."""
    resolved_model = model
    if model.startswith("fal-ai/"):
        key = model.replace("fal-ai/", "")
        if key in MODEL_TO_ENDPOINT:
            resolved_model = MODEL_TO_ENDPOINT[key]
    elif model in MODEL_TO_ENDPOINT:
        resolved_model = MODEL_TO_ENDPOINT[model]
    
    cost = API_COSTS.get(resolved_model, API_COSTS.get(model, API_COSTS.get("default", 0.03))) * count
    call_entry = {"model": resolved_model, "cost": round(cost, 4), "ts": time.time()}
    if note:
        call_entry["note"] = note
    
    SESSION_COST["total"] += cost
    SESSION_COST["calls"].append(call_entry.copy())
    
    if state is not None:
        if "costs" not in state:
            state["costs"] = {"total": 0.0, "calls": []}
        state["costs"]["total"] = round(state["costs"].get("total", 0.0) + cost, 4)
        state["costs"]["calls"].append(call_entry.copy())
        if len(state["costs"]["calls"]) > 100:
            state["costs"]["calls"] = state["costs"]["calls"][-100:]

def fetch_live_pricing():
    """Fetch live pricing from fal.ai API."""
    global API_COSTS, PRICING_LOADED
    if not FAL_KEY:
        print("[INFO] No FAL_KEY, using default pricing")
        return
    try:
        r = requests.get(
            "https://api.fal.ai/v1/models/pricing",
            headers={"Authorization": f"Key {FAL_KEY}"},
            timeout=10
        )
        if r.ok:
            data = r.json()
            for item in data.get("prices", []):
                endpoint_id = item.get("endpoint_id", "")
                unit_price = item.get("unit_price", 0)
                if endpoint_id and unit_price:
                    API_COSTS[endpoint_id] = unit_price
            PRICING_LOADED = True
            print(f"[INFO] Loaded {len(data.get('prices', []))} prices from fal.ai")
    except Exception as e:
        print(f"[WARN] Failed to fetch live pricing: {e}")

# ========= Logging =========
def log_llm_call(endpoint: str, system: str, user: str, response: Any, project_id: str = "unknown"):
    """Log LLM prompts and responses for debugging."""
    try:
        ts = int(time.time())
        log_file = DEBUG_DIR / f"{project_id}_llm_{ts}.json"
        log_file.write_text(json.dumps({
            "timestamp": ts,
            "endpoint": endpoint,
            "system_prompt": system,
            "user_prompt": user,
            "response": response,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to log LLM call: {e}")
