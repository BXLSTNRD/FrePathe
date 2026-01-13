import os, json, time, uuid, asyncio, threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

# v1.6.5: Lock for thread-safe project file access (prevents race condition on parallel renders)
PROJECT_LOCKS: Dict[str, threading.Lock] = {}
PROJECT_LOCKS_LOCK = threading.Lock()  # Lock to create per-project locks

def get_project_lock(project_id: str) -> threading.Lock:
    """Get or create a lock for a specific project."""
    with PROJECT_LOCKS_LOCK:
        if project_id not in PROJECT_LOCKS:
            PROJECT_LOCKS[project_id] = threading.Lock()
        return PROJECT_LOCKS[project_id]

import requests
import fal_client
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jsonschema import validate, ValidationError, Draft202012Validator

# ========= Version =========
VERSION = "1.6.6"

# ========= v1.6.1: Retry Helper =========
def retry_on_502(func: Callable, max_retries: int = 3, delay: float = 2.0):
    """Retry a function on 5xx server errors with exponential backoff. 4xx errors fail immediately."""
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except HTTPException as e:
                if e.status_code >= 500 and attempt < max_retries - 1:
                    # Server error - worth retrying
                    wait = delay * (2 ** attempt)
                    print(f"[WARN] {e.status_code} error, retry {attempt+1}/{max_retries} in {wait:.1f}s: {str(e.detail)[:100]}")
                    time.sleep(wait)
                    last_error = e
                else:
                    # 4xx or final attempt - fail immediately
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait = delay * (2 ** attempt)
                    print(f"[WARN] Request error, retry {attempt+1}/{max_retries} in {wait:.1f}s: {str(e)[:100]}")
                    time.sleep(wait)
                    last_error = e
                else:
                    raise HTTPException(502, f"Request failed after {max_retries} retries: {str(e)[:200]}")
        raise last_error or HTTPException(502, "Max retries exceeded")
    return wrapper

# ========= Storage =========
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PROJECTS_DIR = DATA / "projects"
UPLOADS_DIR = DATA / "uploads"
RENDERS_DIR = DATA / "renders"  # v1.2.3: Local render storage
DEBUG_DIR = DATA / "debug"  # v1.4: LLM prompt/response logging
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# v1.5.9.1: Export status tracking (in-memory, per project)
EXPORT_STATUS: Dict[str, Dict[str, Any]] = {}

# v1.4: Cost tracking (per session) - Real fal.ai pricing (Jan 2025)
# Source: https://fal.ai/pricing, https://docs.fal.ai/platform-apis/v1/models/pricing
# NOTE: For dynamic/live pricing, call: GET https://api.fal.ai/v1/models/pricing
API_COSTS = {
    # v1.6.1: Correct pricing from FAL dashboard (Jan 2026)
    # Audio - $0.01 per 5 seconds
    "fal-ai/audio-understanding": 0.002,  # Per second: $0.01/5s = $0.002/s
    "fal-ai/whisper": 0.0004,  # $0.0004/second ($0.024/minute)
    # Text-to-Image (per image)
    "fal-ai/nano-banana-pro": 0.15,       # $0.15/image
    "fal-ai/flux/dev": 0.025,             # $0.025/megapixel
    "fal-ai/flux-1/dev": 0.025,           # $0.025/megapixel
    "fal-ai/flux-2": 0.012,               # $0.012/megapixel
    "fal-ai/flux-pro/v1.1": 0.04,
    "fal-ai/recraft/v3": 0.04,
    "fal-ai/bytedance/seedream/v4.5/text-to-image": 0.04,  # $0.04/image
    # Image-to-Image / Edit (per image)
    "fal-ai/nano-banana-pro/edit": 0.15,  # $0.15/image
    "fal-ai/flux/dev/image-to-image": 0.025,
    "fal-ai/flux-2/edit": 0.012,          # $0.012/megapixel
    "fal-ai/bytedance/seedream/v4.5/edit": 0.04,  # $0.04/image
    "fal-ai/kontext/edit": 0.05,
    # Internal editor key mappings (same prices)
    "fal-ai/nanobanana_edit": 0.15,
    "fal-ai/flux2_edit": 0.012,
    "fal-ai/seedream45_edit": 0.04,
    "fal-ai/kontext_edit": 0.05,
    # LLM (per call, estimated ~2-5K tokens avg)
    "claude-sonnet-4-5-20250929": 0.02,   # ~$3/$15 per 1M tokens
    "claude-3-5-sonnet-latest": 0.015,
    "claude-3-5-sonnet-20241022": 0.015,
    "claude-3-haiku-20240307": 0.002,     # ~$0.25/$1.25 per 1M tokens
    "gpt-4o-mini": 0.001,
    # Default
    "default": 0.05,
}

# v1.5: Map internal model keys to FAL endpoint IDs for accurate cost tracking
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
}

SESSION_COST = {"total": 0.0, "calls": []}
PRICING_LOADED = False

# v1.5: Semaphore for concurrent render limiting
RENDER_SEMAPHORE = asyncio.Semaphore(2)  # Max 2 concurrent renders

def fetch_live_pricing():
    """v1.4.2: Fetch live pricing from fal.ai API."""
    global API_COSTS, PRICING_LOADED
    fal_key = os.environ.get("FAL_KEY", "").strip()
    if not fal_key:
        print("[INFO] No FAL_KEY, using default pricing")
        return
    try:
        r = requests.get(
            "https://api.fal.ai/v1/models/pricing",
            headers={"Authorization": f"Key {fal_key}"},
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

# v1.5: Beat Grid Calculation
def build_beat_grid(duration_sec: float, bpm: float) -> Dict[str, Any]:
    """Calculate beat and bar positions for audio sync."""
    if not bpm or bpm <= 0 or not duration_sec:
        return {"beats": [], "bars": [], "beat_sec": 0, "bar_sec": 0, "bpm": 0, "total_beats": 0, "total_bars": 0}
    
    beat_sec = 60.0 / bpm  # Duration of one beat
    bar_sec = beat_sec * 4  # 4 beats per bar (standard 4/4 time)
    
    # Generate beat positions
    beats = []
    t = 0.0
    while t <= duration_sec:
        beats.append(round(t, 3))
        t += beat_sec
    
    # Generate bar positions
    bars = []
    t = 0.0
    while t <= duration_sec:
        bars.append(round(t, 3))
        t += bar_sec
    
    return {
        "bpm": bpm,
        "beat_sec": round(beat_sec, 4),
        "bar_sec": round(bar_sec, 4),
        "beats": beats,
        "bars": bars,
        "total_beats": len(beats),
        "total_bars": len(bars),
    }

def snap_to_grid(t: float, grid: List[float], tolerance: float = 0.5) -> float:
    """Snap a time value to the nearest grid position."""
    if not grid:
        return t
    nearest = min(grid, key=lambda x: abs(x - t))
    if abs(nearest - t) <= tolerance:
        return nearest
    return t

def log_llm_call(endpoint: str, system: str, user: str, response: Any, project_id: str = "unknown"):
    """v1.4: Log LLM prompts and responses for debugging."""
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

def track_cost(model: str, count: int = 1, project_id: str = None, state: Dict = None):
    """v1.5: Track API costs - resolve model keys and save to session/state."""
    # v1.5: Resolve internal model key to endpoint ID
    resolved_model = model
    if model.startswith("fal-ai/"):
        key = model.replace("fal-ai/", "")
        if key in MODEL_TO_ENDPOINT:
            resolved_model = MODEL_TO_ENDPOINT[key]
    elif model in MODEL_TO_ENDPOINT:
        resolved_model = MODEL_TO_ENDPOINT[model]
    
    cost = API_COSTS.get(resolved_model, API_COSTS.get(model, API_COSTS.get("default", 0.03))) * count
    SESSION_COST["total"] += cost
    SESSION_COST["calls"].append({"model": resolved_model, "cost": round(cost, 4), "ts": time.time()})
    
    # v1.4.9: Update state dict if provided (caller will save it)
    if state is not None:
        if "costs" not in state:
            state["costs"] = {"total": 0.0, "calls": []}
        state["costs"]["total"] = round(state["costs"].get("total", 0.0) + cost, 4)
        state["costs"]["calls"].append({"model": resolved_model, "cost": round(cost, 4), "ts": time.time()})
        # Keep last 100 calls
        if len(state["costs"]["calls"]) > 100:
            state["costs"]["calls"] = state["costs"]["calls"][-100:]

def get_audio_duration_librosa(file_path: str) -> Optional[float]:
    """v1.4: Get accurate audio duration using librosa."""
    try:
        import librosa
        duration = librosa.get_duration(path=file_path)
        return round(duration, 2)
    except ImportError:
        print("[WARN] librosa not installed, falling back to mutagen")
        return None
    except Exception as e:
        print(f"[WARN] librosa failed: {e}")
        return None

# v1.5.8: Accurate BPM detection using librosa
def get_audio_bpm_librosa(file_path: str) -> Optional[float]:
    """Detect BPM using librosa beat tracking - much more accurate than FAL."""
    try:
        import librosa
        # Load audio file
        y, sr = librosa.load(file_path, sr=None)
        # Use beat_track for tempo detection
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        # tempo can be an array, get scalar
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else None
        else:
            tempo = float(tempo)
        if tempo:
            bpm = round(tempo, 1)
            print(f"[INFO] Librosa BPM detection: {bpm}")
            return bpm
        return None
    except ImportError:
        print("[WARN] librosa not installed for BPM detection")
        return None
    except Exception as e:
        print(f"[WARN] librosa BPM detection failed: {e}")
        return None

def get_audio_duration_mutagen(file_path: str) -> Optional[float]:
    """Fallback: Get audio duration using mutagen."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(file_path)
        if audio and audio.info:
            return round(audio.info.length, 2)
    except Exception as e:
        print(f"[WARN] mutagen failed: {e}")
    return None

def get_audio_duration(file_path: str) -> Optional[float]:
    """v1.4: Get audio duration with fallbacks."""
    # Try librosa first (most accurate)
    dur = get_audio_duration_librosa(file_path)
    if dur:
        return dur
    # Fallback to mutagen
    dur = get_audio_duration_mutagen(file_path)
    if dur:
        return dur
    return None

# ========= v1.5.9.1: Project Folder System =========
import re

def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Convert string to safe filename: ASCII alphanumeric + underscore only."""
    if not name:
        return "unnamed"
    # Replace spaces and common separators with underscore
    safe = re.sub(r'[\s\-\.]+', '_', name)
    # Keep only alphanumeric and underscore
    safe = re.sub(r'[^a-zA-Z0-9_]', '', safe)
    # Remove consecutive underscores
    safe = re.sub(r'_+', '_', safe)
    # Strip leading/trailing underscores
    safe = safe.strip('_')
    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('_')
    return safe or "unnamed"

def get_project_folder(state: Dict[str, Any]) -> Path:
    """Get project folder path, create if needed. Format: ProjectTitle_vX.X.X"""
    project = state.get("project", {})
    title = project.get("title", "Untitled")
    # Use version that created the project, or current version
    created_version = project.get("created_version", VERSION)
    
    safe_title = sanitize_filename(title, 30)
    folder_name = f"{safe_title}_v{created_version}"
    
    folder_path = PROJECTS_DIR / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path

def get_project_renders_dir(state: Dict[str, Any]) -> Path:
    """Get renders subdirectory for project."""
    renders_dir = get_project_folder(state) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    return renders_dir

def get_project_audio_dir(state: Dict[str, Any]) -> Path:
    """Get audio subdirectory for project."""
    audio_dir = get_project_folder(state) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir

def get_project_video_dir(state: Dict[str, Any]) -> Path:
    """Get video subdirectory for project."""
    video_dir = get_project_folder(state) / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    return video_dir

def get_project_llm_dir(state: Dict[str, Any]) -> Path:
    """Get LLM responses subdirectory for project."""
    llm_dir = get_project_folder(state) / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)
    return llm_dir

def save_llm_response(state: Dict[str, Any], name: str, response: Any) -> Path:
    """Save LLM response to project's llm folder. Returns path."""
    llm_dir = get_project_llm_dir(state)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.json"
    filepath = llm_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Saved LLM response: {filepath}")
    return filepath

def download_image_locally(url: str, project_id: str, prefix: str, state: Dict[str, Any] = None, friendly_name: str = None) -> str:
    """v1.5.9.1: Download image to project folder with friendly naming.
    If state provided: saves to project folder with friendly name.
    If no state: legacy behavior (saves to global renders folder).
    """
    if not url or url.startswith("/renders/"):
        return url
    try:
        ext = ".png"
        if ".jpg" in url or ".jpeg" in url:
            ext = ".jpg"
        elif ".webp" in url:
            ext = ".webp"
        
        # v1.5.9.1: Use project folder if state provided
        if state:
            renders_dir = get_project_renders_dir(state)
            if friendly_name:
                local_filename = f"{friendly_name}{ext}"
            else:
                local_filename = f"{prefix}{ext}"
            local_path = renders_dir / local_filename
            
            # Download
            r = requests.get(url, timeout=60)
            if r.status_code == 200:
                local_path.write_bytes(r.content)
            
            # Return path relative to DATA for serve_render
            rel_path = local_path.relative_to(DATA)
            return f"/renders/{rel_path.as_posix()}"
        else:
            # Legacy behavior
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            local_filename = f"{project_id}_{prefix}_{url_hash}{ext}"
            local_path = RENDERS_DIR / local_filename
            
            if not local_path.exists():
                r = requests.get(url, timeout=60)
                if r.status_code == 200:
                    local_path.write_bytes(r.content)
            
            return f"/renders/{local_filename}"
    except Exception as e:
        print(f"[WARN] Failed to download image locally: {e}")
        return url

# ========= Schema Validation (v1.12) =========
CONTRACTS_DIR = BASE / "contracts"
_SCHEMAS: Dict[str, Any] = {}

def _load_schemas() -> None:
    """Load all JSON schemas from contracts directory."""
    global _SCHEMAS
    if _SCHEMAS:
        return
    for schema_file in CONTRACTS_DIR.glob("*.schema.json"):
        try:
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
            schema_name = schema_file.stem.replace(".schema", "")
            _SCHEMAS[schema_name] = schema
        except Exception as e:
            print(f"[WARN] Failed to load schema {schema_file.name}: {e}")

def validate_against_schema(data: Dict[str, Any], schema_name: str, raise_on_error: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate data against a named schema.
    Returns (is_valid, error_message).
    """
    _load_schemas()
    schema = _SCHEMAS.get(schema_name)
    if not schema:
        return (True, None)  # No schema = skip validation
    try:
        validate(instance=data, schema=schema)
        return (True, None)
    except ValidationError as e:
        error_msg = f"Schema validation failed ({schema_name}): {e.message} at path {list(e.absolute_path)}"
        if raise_on_error:
            raise HTTPException(422, error_msg)
        return (False, error_msg)

def validate_shot(shot: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate a single shot object."""
    required_fields = ["shot_id", "sequence_id", "start", "end", "structure_type", "energy", "cast", "prompt_base"]
    missing = [f for f in required_fields if f not in shot]
    if missing:
        return (False, f"Shot missing required fields: {missing}")
    if not isinstance(shot.get("start"), (int, float)) or not isinstance(shot.get("end"), (int, float)):
        return (False, "Shot start/end must be numbers")
    if shot["start"] >= shot["end"]:
        return (False, f"Shot {shot['shot_id']}: start ({shot['start']}) must be < end ({shot['end']})")
    if not 0.0 <= shot.get("energy", 0) <= 1.0:
        return (False, f"Shot {shot['shot_id']}: energy must be 0.0-1.0")
    return (True, None)

def validate_sequence(seq: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate a single sequence object."""
    required_fields = ["sequence_id", "start", "end", "structure_type", "energy"]
    missing = [f for f in required_fields if f not in seq]
    if missing:
        return (False, f"Sequence missing required fields: {missing}")
    if seq["start"] >= seq["end"]:
        return (False, f"Sequence {seq['sequence_id']}: start ({seq['start']}) must be < end ({seq['end']})")
    return (True, None)

def validate_project_state(state: Dict[str, Any], strict: bool = False) -> Tuple[bool, List[str]]:
    """
    Validate entire project state.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    # Check required top-level keys
    required_keys = ["project", "audio_dna", "cast", "storyboard"]
    for key in required_keys:
        if key not in state:
            errors.append(f"Missing required key: {key}")
    
    # Validate project
    proj = state.get("project", {})
    if not proj.get("id"):
        errors.append("Project missing 'id'")
    if not proj.get("style_preset"):
        errors.append("Project missing 'style_preset'")
    if proj.get("aspect") not in ["square", "vertical", "horizontal", None]:
        errors.append(f"Invalid aspect: {proj.get('aspect')}")
    
    # Validate sequences
    seqs = state.get("storyboard", {}).get("sequences", [])
    for seq in seqs:
        ok, err = validate_sequence(seq)
        if not ok:
            errors.append(err)
    
    # Validate shots
    shots = state.get("storyboard", {}).get("shots", [])
    for shot in shots:
        ok, err = validate_shot(shot)
        if not ok:
            errors.append(err)
    
    # Check cast_id references in shots
    valid_cast_ids = {c.get("cast_id") for c in state.get("cast", []) if c.get("cast_id")}
    for shot in shots:
        for cid in shot.get("cast", []):
            if cid not in valid_cast_ids:
                errors.append(f"Shot {shot.get('shot_id')} references unknown cast_id: {cid}")
    
    is_valid = len(errors) == 0
    if strict and not is_valid:
        raise HTTPException(422, f"Project validation failed: {errors}")
    
    return (is_valid, errors)

# ========= Keys =========
FAL_KEY = os.environ.get("FAL_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
CLAUDE_KEY = os.environ.get("CLAUDE_KEY", "").strip()

FAL_BASE = "https://fal.run"
FAL_AUDIO = f"{FAL_BASE}/fal-ai/audio-understanding"
FAL_WHISPER = f"{FAL_BASE}/fal-ai/whisper"  # v1.5.6: Whisper transcription
# v1.11: Flux-1/dev + Redux removed (hard-disabled). Use locked T2I models instead.
FAL_FLUX2_T2I = f"{FAL_BASE}/fal-ai/flux-2"
FAL_SEEDREAM45_T2I = f"{FAL_BASE}/fal-ai/bytedance/seedream/v4.5/text-to-image"
FAL_NANOBANANA_PRO_T2I = f"{FAL_BASE}/fal-ai/nano-banana-pro"
FAL_FLUX2_EDIT = f"{FAL_BASE}/fal-ai/flux-2/edit"
FAL_NANOBANANA_EDIT = f"{FAL_BASE}/fal-ai/nano-banana-pro/edit"
FAL_SEEDREAM45_EDIT = f"{FAL_BASE}/fal-ai/bytedance/seedream/v4.5/edit"

DEFAULT_AUDIO_PROMPT = (
    "I need you to transcribe the lyrics (timecoded); "
    "I need BPM; I need Style; "
    "I need the Structure (timecoded); Dynamics (timecoded); "
    "Vocal delivery and the Story/Arch"
)

# ========= Storyboard heuristics =========
SHOTS_PER_180S = 70
SEQ_MIN, SEQ_MAX = 6, 10
SHOTS_PER_SEQ_MIN, SHOTS_PER_SEQ_MAX = 5, 8

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def target_sequences_and_shots(duration_sec: Optional[float]) -> Tuple[int, int]:
    d = float(duration_sec) if duration_sec and duration_sec > 1 else 180.0
    target_shots = int(round((d / 180.0) * SHOTS_PER_180S))
    target_shots = int(clamp(target_shots, 20, 250))

    seq_count = int(round(target_shots / 6.5))
    seq_count = int(clamp(seq_count, SEQ_MIN, SEQ_MAX))

    avg = target_shots / max(1, seq_count)
    if avg < SHOTS_PER_SEQ_MIN:
        seq_count = int(clamp(int(round(target_shots / SHOTS_PER_SEQ_MIN)), SEQ_MIN, SEQ_MAX))
    elif avg > SHOTS_PER_SEQ_MAX:
        seq_count = int(clamp(int(round(target_shots / SHOTS_PER_SEQ_MAX)), SEQ_MIN, SEQ_MAX))

    return seq_count, target_shots

def build_beat_grid(duration_sec: float, bpm: Optional[int]) -> Optional[Dict[str, Any]]:
    if not bpm or bpm <= 0 or not duration_sec or duration_sec <= 0:
        return None
    beat = 60.0 / float(bpm)
    bar = beat * 4.0
    bars = int(duration_sec / bar) + 1
    return {
        "bpm": int(bpm),
        "beat_sec": beat,
        "bar_sec": bar,
        "bars": [{"i": i, "t": round(i * bar, 3)} for i in range(bars)],
        "cut_candidates": [{"t": round(i * bar, 3), "reason": "bar"} for i in range(bars)],
    }

# ========= Styles (20) =========
STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "anamorphic_cinema": {
        "label": "Anamorphic Cinema",
        "tokens": ["anamorphic lens", "cinematic lighting", "shallow depth of field", "film grain", "high dynamic range"],
        "script_notes": "Modern cinematic coverage with motivated camera and emotional blocking.",
    },
    "8mm_vintage": {
        "label": "8mm Vintage",
        "tokens": ["8mm film", "dust and scratches", "soft halation", "vignette", "handheld drift"],
        "script_notes": "Nostalgic memory texture. Lean on match-cuts and time-jumps.",
    },
    "noir_monochrome": {
        "label": "Noir Monochrome",
        "tokens": ["black and white", "film noir lighting", "high contrast", "smoke haze", "hard shadows"],
        "script_notes": "Noir grammar: silhouettes, blinds, reflections, rain, moral tension.",
    },
    "neon_noir": {"label":"Neon Noir","tokens":["neon reflections","wet asphalt","cyan-magenta glow","urban night","hard contrast"],"script_notes":"City pulse, reflective surfaces, forward motion."},
    "documentary_handheld": {"label":"Documentary Handheld","tokens":["handheld camera","natural light","documentary realism","imperfect framing","authentic moment"],"script_notes":"Observational shots, organic camera reactivity."},
    "dreamlike_softfocus": {"label":"Dreamlike Softfocus","tokens":["soft focus","bloom","hazy atmosphere","gentle lens flare","slow motion feel"],"script_notes":"Elliptical transitions, symbolism over plot."},
    "gritty_urban": {"label":"Gritty Urban","tokens":["gritty texture","streetlight sodium glow","high ISO grain","raw realism","urban decay"],"script_notes":"Hard cuts, kinetic beats, street-level tension."},
    "period_70s": {"label":"Period 70s","tokens":["1970s film","warm tones","zoom lens","film grain","practical lighting"],"script_notes":"Zoom language, longer takes, character staging."},
    "period_90s_indie": {"label":"90s Indie","tokens":["1990s indie film","muted palette","handheld intimacy","natural window light"],"script_notes":"Lo-fi sincerity, intimate coverage."},
    "hyperreal_clean": {"label":"Hyperreal Clean","tokens":["ultra clean","sharp detail","stable camera","modern commercial lighting","minimal grain"],"script_notes":"Precise compositions, premium polish."},
    "surreal_symbolism": {"label":"Surreal Symbolism","tokens":["surreal","symbolic props","unexpected scale","dream logic","metaphoric staging"],"script_notes":"Metaphor-first transitions."},
    "one_take_energy": {"label":"One-Take Energy","tokens":["long take feel","continuous camera","blocking choreography","fluid movement"],"script_notes":"Each segment as a coherent mini-arc."},
    "stop_motion_look": {"label":"Stop‑Motion Look","tokens":["stop motion aesthetic","tactile texture","miniature set feel","slight frame jitter"],"script_notes":"Tangible props; playful but precise continuity."},
    "anime_cinematic": {"label":"Anime Cinematic","tokens":["anime cinematic framing","dramatic angles","stylized lighting","dynamic motion"],"script_notes":"Bold compositions, emotional punch-ins."},
    "western_dust": {"label":"Western Dust","tokens":["western","dusty air","backlit sun","wide landscapes","gritty close-ups"],"script_notes":"Wide establishing + intense close-ups."},
    "horror_suspense": {"label":"Horror Suspense","tokens":["low key lighting","negative space","uneasy framing","fog","subtle dread"],"script_notes":"Unease via pacing and framing; payoff on peaks."},
    "romcom_bright": {"label":"Romcom Bright","tokens":["bright soft light","warm highlights","playful composition","colorful props","gentle contrast"],"script_notes":"Readable emotions, charming beats."},
    "music_doc_backstage": {"label":"Music Doc / Backstage","tokens":["backstage","available light","close handheld","authentic gear","crowd energy"],"script_notes":"Candid moments + inserts; quick coverage."},
    "sci_fi_retro": {"label":"Retro Sci‑Fi","tokens":["retro sci-fi","chrome","analog controls","practical neon","fogged glass"],"script_notes":"World-building via set detail; beats as system states."},
    "art_nouveau_poetic": {"label":"Art Nouveau Poetic","tokens":["art nouveau curves","ornate ironwork","stained glass glow","poetic framing","elegant motifs"],"script_notes":"Repeating motifs; transitions echo rhythms."},
    "minimalist_monochrome": {"label":"Minimalist Monochrome","tokens":["minimalism","monochrome","negative space","clean lines","quiet composition"],"script_notes":"Sparse storytelling; musically motivated cuts."},
    # v1.5.7: 20 New styles
    "vaporwave_aesthetic": {"label":"Vaporwave Aesthetic","tokens":["vaporwave","pink purple gradients","greek statues","retro tech","glitch effects","palm trees"],"script_notes":"Nostalgic irony, consumer culture visuals."},
    "cyberpunk_2077": {"label":"Cyberpunk 2077","tokens":["cyberpunk","holographic ads","rain-slicked streets","neon kanji","chrome implants","dark future"],"script_notes":"Tech noir, body modification themes."},
    "studio_ghibli": {"label":"Studio Ghibli","tokens":["studio ghibli style","hand painted backgrounds","soft watercolor","whimsical nature","magical realism"],"script_notes":"Environmental storytelling, wonder."},
    "wes_anderson": {"label":"Wes Anderson","tokens":["symmetrical framing","pastel palette","vintage props","whimsical staging","centered composition"],"script_notes":"Deadpan humor, meticulous mise-en-scène."},
    "tarantino_grindhouse": {"label":"Tarantino Grindhouse","tokens":["grindhouse","film damage","exploitation aesthetic","bold typography","retro violence"],"script_notes":"Pulpy dialogue, chapter structure."},
    "blade_runner": {"label":"Blade Runner","tokens":["blade runner","rain","neon advertisements","industrial fog","noir future","flying vehicles"],"script_notes":"Existential themes, rain-soaked melancholy."},
    "wong_kar_wai": {"label":"Wong Kar-Wai","tokens":["step printing","smeared motion","saturated colors","loneliness","neon reflections","romantic melancholy"],"script_notes":"Time manipulation, unrequited love."},
    "lynch_surreal": {"label":"David Lynch Surreal","tokens":["surreal","red curtains","industrial hum","uncanny valley","dream nightmare","slow dread"],"script_notes":"Subconscious imagery, unsettling ordinary."},
    "kubrick_symmetry": {"label":"Kubrick Symmetry","tokens":["one point perspective","symmetrical","cold precision","clinical lighting","unsettling stillness"],"script_notes":"Geometric perfection, human fragility."},
    "instagram_lifestyle": {"label":"Instagram Lifestyle","tokens":["lifestyle photography","golden hour","soft bokeh","aspirational","clean minimal","influencer aesthetic"],"script_notes":"Aspirational beauty, product integration."},
    "90s_mtv": {"label":"90s MTV","tokens":["90s mtv","quick cuts","dutch angles","fish eye lens","grunge aesthetic","video effects"],"script_notes":"Energetic editing, youth rebellion."},
    "polaroid_nostalgia": {"label":"Polaroid Nostalgia","tokens":["polaroid","instant film","light leaks","vintage colors","snapshot aesthetic","authentic moments"],"script_notes":"Intimate memories, imperfect beauty."},
    "fashion_editorial": {"label":"Fashion Editorial","tokens":["high fashion","editorial lighting","stark backgrounds","dramatic poses","vogue aesthetic","model photography"],"script_notes":"Striking poses, visual impact."},
    "music_video_glam": {"label":"Music Video Glam","tokens":["music video","lens flares","smoke machines","dramatic lighting","performance shots","glamorous"],"script_notes":"Star power, visual spectacle."},
    "pixel_art_retro": {"label":"Pixel Art Retro","tokens":["pixel art","8-bit aesthetic","retro gaming","limited palette","chunky pixels","nostalgic"],"script_notes":"Gaming nostalgia, simplified forms."},
    "comic_book_pop": {"label":"Comic Book Pop","tokens":["comic book style","bold outlines","halftone dots","speech bubbles","pop art colors","dynamic panels"],"script_notes":"Sequential energy, graphic impact."},
    "renaissance_painting": {"label":"Renaissance Painting","tokens":["renaissance","chiaroscuro","oil painting","classical composition","religious light","old masters"],"script_notes":"Timeless beauty, dramatic lighting."},
    "soviet_propaganda": {"label":"Soviet Constructivism","tokens":["constructivism","red and black","bold geometry","propaganda poster","worker imagery","revolutionary"],"script_notes":"Bold graphics, ideological power."},
    "japanese_woodblock": {"label":"Japanese Woodblock","tokens":["ukiyo-e","woodblock print","flat perspective","nature scenes","edo period","stylized waves"],"script_notes":"Elegant simplicity, natural beauty."},
    "miami_vice": {"label":"Miami Vice","tokens":["miami vice","pastel suits","sunset colors","palm trees","speedboats","80s glamour","tropical noir"],"script_notes":"Sun-soaked crime, style over substance."},
    # v1.5.7: Additional styles
    "noir_classic": {"label":"Noir Classic","tokens":["1940s film noir","fedora hats","trench coats","venetian blinds","cigarette smoke","rain-slicked streets","black and white","hard boiled detective"],"script_notes":"Classic detective genre, moral ambiguity, femme fatale."},
    "noir_neo": {"label":"Neo Noir","tokens":["neo noir","modern noir","neon and shadow","urban nightscape","contemporary crime","stylized violence","no hats","no trenchcoats","sleek modern"],"script_notes":"Modern crime drama aesthetics, stylish but grounded."},
    "glitch_art": {"label":"Glitch Art","tokens":["glitch art","data corruption","pixel sorting","RGB split","digital artifacts","scan lines","VHS damage","broken signal"],"script_notes":"Digital decay, technological anxiety, broken beauty."},
    "lo_fi_bedroom": {"label":"Lo-Fi Bedroom","tokens":["lo-fi aesthetic","warm lamp light","cozy bedroom","soft textures","vintage electronics","plants","warm grain","intimate space"],"script_notes":"Intimate, comfortable, nostalgic warmth."},
    "brutalist_concrete": {"label":"Brutalist Concrete","tokens":["brutalist architecture","raw concrete","geometric shadows","monumental scale","cold modernism","stark angles","urban fortress"],"script_notes":"Imposing structures, human vs architecture tension."},
    "acid_trip": {"label":"Acid Trip","tokens":["psychedelic","kaleidoscopic patterns","color distortion","melting reality","fractal geometry","saturated hues","visual hallucination"],"script_notes":"Reality bending, sensory overload, altered states."},
    "french_new_wave": {"label":"French New Wave","tokens":["nouvelle vague","jump cuts","natural light","parisian streets","handheld camera","intellectual cool","cigarette aesthetic","black and white option"],"script_notes":"Rule-breaking editing, philosophical undertones, effortless style."},
    "afrofuturism": {"label":"Afrofuturism","tokens":["afrofuturism","african patterns","futuristic technology","cosmic imagery","gold accents","ancestral future","wakanda aesthetic"],"script_notes":"Heritage meets tomorrow, empowered futures, cultural pride."},
    "silent_film_era": {"label":"Silent Film Era","tokens":["silent film","sepia tone","iris shots","intertitles","theatrical acting","vintage vignette","1920s aesthetic","expressionist shadows"],"script_notes":"Exaggerated emotion, visual storytelling, nostalgic charm."},
    # v1.5.9.1: Puppet & Animation styles
    "muppet_show": {"label":"Muppet Show","tokens":["jim henson muppets","felt puppet","googly eyes","fabric texture","theatrical stage","warm lighting","expressive puppet faces","handcrafted aesthetic"],"script_notes":"Warm comedy, vaudeville energy, breaking fourth wall."},
    "claymation": {"label":"Claymation","tokens":["claymation","stop motion clay","plasticine texture","aardman style","fingerprint details","smooth animation","tactile characters","handmade charm"],"script_notes":"Tactile humor, physical comedy, Wallace and Gromit vibes."},
    "thunderbirds": {"label":"Thunderbirds","tokens":["supermarionation","1960s puppet","marionette strings visible","retro futurism","practical miniatures","wooden movement","tracy island aesthetic"],"script_notes":"Retro sci-fi heroics, dramatic rescues, stiff-upper-lip."},
    "spitting_image": {"label":"Spitting Image","tokens":["latex puppet","caricature","satirical puppet","grotesque features","exaggerated expressions","political satire","rubber mask aesthetic"],"script_notes":"Sharp satire, exaggerated features, biting commentary."},
    "team_america": {"label":"Team America","tokens":["team america puppets","action movie parody","marionette action","miniature explosions","puppet violence","satirical patriotism","string puppets"],"script_notes":"Action parody, irreverent humor, puppet chaos."},
}

def style_tokens(key: str) -> List[str]:
    return STYLE_PRESETS.get(key, {"tokens":[key]}).get("tokens", [key])

def style_script_notes(key: str) -> str:
    return STYLE_PRESETS.get(key, {"script_notes":""}).get("script_notes","")

# ========= App =========
app = FastAPI()

# v1.4.2: Fetch live pricing on startup
@app.on_event("startup")
async def startup_event():
    fetch_live_pricing()

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def require_key(name: str, value: str):
    if not value:
        raise HTTPException(500, f"Missing {name}. Put it in env var {name} and restart.")

def fal_headers() -> Dict[str,str]:
    require_key("FAL_KEY", FAL_KEY)
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}

def call_img2img_editor(editor_key: str, prompt: str, image_urls: List[str], aspect: str) -> str:
    """
    Returns the first output image URL or raises HTTPException.
    editor_key: flux2_edit | nanobanana_edit | seedream45_edit
    """
    require_key("FAL_KEY", FAL_KEY)

    if not image_urls:
        raise HTTPException(400, "img2img requires at least 1 image_url")

    # keep within model limits (flux2 max 4, seedream max 10, nanobanana accepts list)
    if editor_key == "flux2_edit":
        endpoint = FAL_FLUX2_EDIT
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:4],
            "guidance_scale": 2.5,
            "num_inference_steps": 28,
            "output_format": "png",
            "aspect_ratio": "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1"),
        }
    elif editor_key == "nanobanana_edit":
        endpoint = FAL_NANOBANANA_EDIT
        aspect_ratio = "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1")
        image_size = "landscape_16_9" if aspect == "horizontal" else ("portrait_16_9" if aspect == "vertical" else "square_hd")
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:4],
            "output_format": "png",
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,  # v1.5.3: Try both params
            "resolution": "2K",
        }
        print(f"[INFO] NanoBanana img2img: aspect={aspect}, aspect_ratio={aspect_ratio}, image_size={image_size}, ref_count={len(image_urls)}")
    elif editor_key == "seedream45_edit":
        endpoint = FAL_SEEDREAM45_EDIT
        aspect_ratio = "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1")
        image_size = "landscape_16_9" if aspect == "horizontal" else ("portrait_16_9" if aspect == "vertical" else "square_hd")
        # v1.5.3: Try multiple params - Seedream may use different ones
        width = 1920 if aspect == "horizontal" else (1080 if aspect == "vertical" else 1024)
        height = 1080 if aspect == "horizontal" else (1920 if aspect == "vertical" else 1024)
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:10],
            "num_images": 1,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "width": width,
            "height": height,
        }
        print(f"[INFO] Seedream img2img: aspect={aspect}, {width}x{height}, ref_count={len(image_urls)}")
    else:
        raise HTTPException(400, f"Unknown img2img_editor: {editor_key}")

    # v1.6.1: Retry on 502
    def do_request():
        r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        if r.status_code >= 500:
            # Server error - worth retrying
            raise HTTPException(502, f"img2img editor failed: {r.status_code} {r.text[:500]}")
        elif r.status_code >= 400:
            # Client error (4xx) - don't retry, fail immediately
            raise HTTPException(r.status_code, f"img2img editor failed: {r.status_code} {r.text[:500]}")
        return r
    
    r = retry_on_502(do_request)()
    
    out = r.json()
    img_url = None
    if isinstance(out, dict) and isinstance(out.get("images"), list) and out["images"]:
        img_url = out["images"][0].get("url")

    if not img_url:
        raise HTTPException(502, "img2img editor returned no image url")

    return img_url

# v1.6.6: Internal helper to generate wardrobe preview (reused by scene render and standalone endpoint)
def _generate_wardrobe_ref_internal(project_id: str, scene_id: str, state: Dict, scene: Dict, wardrobe_text: str, scene_num: str) -> Optional[str]:
    """Generate wardrobe preview: lead cast ref_a composited with scene decor and wardrobe.
    Returns local path or None if no cast ref available."""
    editor = locked_editor_key(state)
    cm = state.get("cast_matrix") or {}
    
    # Find lead cast for this scene
    lead_cast_id = scene.get("cast", [None])[0] if scene.get("cast") else None
    if not lead_cast_id:
        # Fallback to first cast
        cast_list = state.get("cast", [])
        lead_cast_id = cast_list[0].get("cast_id") if cast_list else None
    
    if not lead_cast_id:
        return None  # No cast available
    
    # Get cast ref_a
    char_refs = cm.get("character_refs", {}).get(lead_cast_id, {})
    ref_a = char_refs.get("ref_a")
    if not ref_a:
        return None  # No reference image
    
    # Upload ref if local
    ref_url = ref_a
    if ref_a.startswith("/renders/"):
        local_file = resolve_render_path(ref_a)
        if local_file.exists():
            ref_url = fal_client.upload_file(str(local_file))
    
    # Build prompt: character in wardrobe with scene decor context
    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    base_style = ", ".join(style_tokens(style))
    decor_prompt = scene.get("prompt", "")[:200]  # Truncate for safety
    
    prompt = f"{base_style}, {wardrobe_text}, {decor_prompt}, consistent identity, high quality"
    
    result_url = call_img2img_editor(editor, prompt, [ref_url], aspect)
    track_cost(f"fal-ai/{editor}", 1, state=state)
    
    # Store as wardrobe_ref
    scene_title = sanitize_filename(scene.get("title", scene_id), 20)
    local_path = download_image_locally(result_url, project_id, f"scene_{scene_id}_wardrobe", state=state, friendly_name=f"Sce{scene_num}_{scene_title}_Wardrobe")
    
    return local_path

def safe_float(x, default=0.0) -> float:
    try: return float(x)
    except Exception: return float(default)

def normalize_structure_type(s: str) -> str:
    if not s: return "verse"
    t = s.strip().lower()
    for k in ["intro","verse","prechorus","chorus","bridge","breakdown","outro","instrumental"]:
        if t.startswith(k): return k
    if t.startswith("pre-chorus") or t.startswith("pre chorus"): return "prechorus"
    return "verse"

# ========= Persistence =========
def project_path(pid: str) -> Path:
    return PROJECTS_DIR / f"{pid}.json"

def load_project(pid: str) -> Dict[str,Any]:
    p = project_path(pid)
    if not p.exists(): raise HTTPException(404, "Project not found")
    state = json.loads(p.read_text(encoding="utf-8"))
    # v1.12: Validate on load (non-strict, just warn)
    is_valid, errors = validate_project_state(state, strict=False)
    if not is_valid:
        print(f"[WARN] Project {pid} has validation errors: {errors}")
    
    # v1.5.0: Recover orphaned render files
    state = recover_orphaned_renders(state, pid)
    
    return state

def recover_orphaned_renders(state: Dict[str,Any], pid: str) -> Dict[str,Any]:
    """v1.5.0: Find render files on disk that aren't in the JSON and recover them."""
    recovered = 0
    shots = state.get("storyboard", {}).get("shots", [])
    
    for shot in shots:
        shot_id = shot.get("shot_id")
        render = shot.get("render", {})
        
        # Skip if already has a valid render
        if render.get("image_url") and render.get("status") == "done":
            continue
        
        # Look for matching files in renders directory
        # Pattern: {project_id}_{shot_id}_*.png/jpg/webp
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            for f in RENDERS_DIR.glob(f"{pid}_{shot_id}*{ext}"):
                if f.exists():
                    local_url = f"/renders/{f.name}"
                    shot["render"] = {
                        "status": "done",
                        "image_url": local_url,
                        "model": "recovered",
                        "ref_images_used": 0,
                        "error": None
                    }
                    recovered += 1
                    print(f"[INFO] Recovered render for {shot_id}: {local_url}")
                    break
            if shot.get("render", {}).get("status") == "done":
                break
    
    # Also recover scene decor refs
    scenes = state.get("cast_matrix", {}).get("scenes", [])
    for scene in scenes:
        scene_id = scene.get("scene_id")
        decor_refs = scene.get("decor_refs", [])
        
        # Skip if already has decor refs
        if decor_refs and decor_refs[0]:
            continue
        
        # Look for scene decor files
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            for f in RENDERS_DIR.glob(f"{pid}_{scene_id}_decor*{ext}"):
                if f.exists():
                    local_url = f"/renders/{f.name}"
                    scene["decor_refs"] = [local_url]
                    recovered += 1
                    print(f"[INFO] Recovered decor for {scene_id}: {local_url}")
                    break
            if scene.get("decor_refs"):
                break
    
    if recovered > 0:
        print(f"[INFO] Recovered {recovered} orphaned renders for project {pid}")
        # Save the recovered state
        save_project(state, validate=False)
    
    return state

def save_project(state: Dict[str,Any], validate: bool = True, force: bool = False) -> None:
    """Save project state. 
    v1.5.9.1: Blocks save if version mismatch unless force=True.
    """
    pid = state["project"]["id"]
    
    # v1.5.9.1: Version mismatch detection - disable autosave for old projects
    created_version = state["project"].get("created_version")
    if created_version and created_version != VERSION and not force:
        print(f"[WARN] Version mismatch: project created with {created_version}, current app is {VERSION}")
        print(f"[WARN] Autosave disabled. Use 'force=True' or update project version to save.")
        return
    
    state["project"]["updated_at"] = now_iso()
    # v1.12: Validate before save
    if validate:
        is_valid, errors = validate_project_state(state, strict=False)
        if not is_valid:
            print(f"[WARN] Saving project {pid} with validation errors: {errors}")
    project_path(pid).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # v1.5.9.1: Also save to project folder
    try:
        project_folder = get_project_folder(state)
        project_json_path = project_folder / "project.json"
        project_json_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to save to project folder: {e}")

def new_project(title: str, style_preset: str, aspect: str, llm: str = "claude", image_model_choice: str = "nanobanana", video_model: str = "none", use_whisper: bool = False) -> Dict[str,Any]:
    pid = str(uuid.uuid4())
    
    state = {
        "project": {
            "id": pid,
            "title": title,
            "style_preset": style_preset,
            "aspect": aspect,
            "llm": (llm or "claude"),
            "image_model_choice": image_model_choice,
            "video_model": video_model,  # v1.5.6: placeholder for future video models
            "use_whisper": use_whisper,  # v1.5.6: enhanced audio DNA extraction
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "created_version": VERSION,  # v1.6.1: Track which version created this project
            "render_models": locked_render_models(image_model_choice),
            "style_locked": False,  # v1.6.1: True after first cast ref generated
            "style_lock_image": None,  # v1.6.1: First generated ref becomes style anchor
        },
        "audio_dna": None,
        "cast": [],
        "storyboard": {"sequences": [], "shots": []},

        "cast_matrix": {
        "character_refs": {},   # cast_id -> { "ref_a": url, "ref_b": url }
        "scenes": []            # list of {scene_id, prompt, decor_refs:[], output_url}
        },
    }
    
    # v1.5.9.1: Create project folder with title and version
    project_folder = get_project_folder(state)
    print(f"[INFO] Created project folder: {project_folder}")
    
    return state

# v1.5.6: Get project folder path
def project_folder_path(pid: str) -> Path:
    return PROJECTS_DIR / pid

# v1.5.6: Get project renders folder
def project_renders_path(pid: str) -> Path:
    folder = PROJECTS_DIR / pid / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

# v1.5.6: Get project audio folder
def project_audio_path(pid: str) -> Path:
    folder = PROJECTS_DIR / pid / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

# ========= Render model hard-lock (v1.11) =========
def locked_render_models(image_model_choice: str) -> Dict[str, Any]:
    """
    Hard-lock render models for ALL still images based on project image generator selection.
    UI values: nanobanana | seedream45 | flux2
    """
    m = (image_model_choice or "nanobanana").strip().lower()
    if m in ("flux2", "flux_2"):
        return {
            "image_model": "fal-ai/flux-2",
            "identity_model": None,              # Redux removed in v1.11
            "img2img_editor": "flux2_edit",
            "available_editors": ["flux2_edit", "nanobanana_edit", "seedream45_edit"],
        }
    if m in ("seedream45", "seedream_45", "seedream", "seedream4.5", "seedream4_5"):
        return {
            "image_model": "fal-ai/bytedance/seedream/v4.5/text-to-image",
            "identity_model": None,              # Redux removed in v1.11
            "img2img_editor": "seedream45_edit",
            "available_editors": ["seedream45_edit", "nanobanana_edit", "flux2_edit"],
        }
    # default: Nano Banana Pro
    return {
        "image_model": "fal-ai/nano-banana-pro",
        "identity_model": None,                  # Redux removed in v1.11
        "img2img_editor": "nanobanana_edit",
        "available_editors": ["nanobanana_edit", "seedream45_edit", "flux2_edit"],
    }

def locked_editor_key(state: Dict[str, Any]) -> str:
    rm = (state.get("project") or {}).get("render_models") or {}
    return (rm.get("img2img_editor") or "nanobanana_edit").strip()

def t2i_endpoint_and_payload(state: Dict[str,Any], prompt: str, image_size: str) -> (str, Dict[str,Any], str):
    """
    Return (endpoint, payload, model_name) for the locked T2I model.
    """
    rm = (state.get("project") or {}).get("render_models") or {}
    model = (rm.get("image_model") or "fal-ai/nano-banana-pro").strip().lower()

    if model == "fal-ai/flux-2":
        return (FAL_FLUX2_T2I, {"prompt": prompt, "image_size": image_size}, "fal-ai/flux-2")
    if model == "fal-ai/bytedance/seedream/v4.5/text-to-image":
        return (FAL_SEEDREAM45_T2I, {"prompt": prompt, "image_size": image_size}, "fal-ai/bytedance/seedream/v4.5/text-to-image")

    # nano-banana-pro
    aspect = (state.get("project") or {}).get("aspect") or "horizontal"
    aspect_ratio = "16:9" if aspect=="horizontal" else ("9:16" if aspect=="vertical" else "1:1")
    return (FAL_NANOBANANA_PRO_T2I, {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": "1K"}, "fal-ai/nano-banana-pro")

def call_t2i_with_retry(state: Dict[str, Any], prompt: str, image_size: str) -> Tuple[str, str]:
    """v1.6.1: Call T2I endpoint with retry on 5xx. Returns (image_url, model_name)."""
    endpoint, payload, model_name = t2i_endpoint_and_payload(state, prompt, image_size)
    
    def do_request():
        r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        if r.status_code >= 500:
            # Server error - worth retrying
            raise HTTPException(502, f"T2I failed: {r.status_code} {r.text[:500]}")
        elif r.status_code >= 400:
            # Client error (4xx) - don't retry
            raise HTTPException(r.status_code, f"T2I failed: {r.status_code} {r.text[:500]}")
        out = r.json()
        if isinstance(out.get("images"), list) and out["images"] and out["images"][0].get("url"):
            return out["images"][0]["url"]
        raise HTTPException(502, "T2I returned no image url")
    
    url = retry_on_502(do_request)()
    return url, model_name


# ========= Audio normalizer =========
def normalize_audio_understanding(raw: Dict[str,Any]) -> Dict[str,Any]:
    """Parse audio-understanding output and extract structured data."""
    out = raw.get("output")
    duration = raw.get("duration_sec") or raw.get("duration")
    
    # Try to parse JSON from output
    parsed = None
    if isinstance(out, str) and out.strip():
        # Try to extract JSON from markdown code block or raw text
        text = out.strip()
        # Remove markdown code block if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Try to parse as JSON
        try:
            parsed = json.loads(text)
        except:
            # Try to extract JSON object from text
            json_str = _extract_json_object(text)
            if json_str:
                try:
                    parsed = json.loads(json_str)
                except:
                    pass
    
    # If we got parsed JSON, extract fields
    if parsed and isinstance(parsed, dict):
        return {
            "meta": {
                "bpm": parsed.get("bpm"),
                "style": parsed.get("style") if isinstance(parsed.get("style"), list) else ([parsed.get("style")] if parsed.get("style") else []),
                "language": parsed.get("language"),
                "duration_sec": parsed.get("duration_sec") or parsed.get("duration") or duration,
            },
            "structure": parsed.get("structure") or [],
            "dynamics": parsed.get("dynamics") or [],
            "lyrics": parsed.get("lyrics") or [],
            "vocal_delivery": parsed.get("vocal_delivery") or {},
            "story_arc": parsed.get("story_arc") or {"theme":"", "start":"", "conflict":"", "end":""},
            "raw_text_blob": out,
            "source": {"provider":"fal", "model":"fal-ai/audio-understanding", "created_at": now_iso()},
        }
    
    # Fallback: store raw output
    if isinstance(out, str) and out.strip():
        return {
            "meta": {"bpm": None, "style": [], "language": None, "duration_sec": duration},
            "structure": [],
            "dynamics": [],
            "lyrics": [],
            "vocal_delivery": {},
            "story_arc": {"theme":"", "start":"", "conflict":"", "end":""},
            "raw_text_blob": out,
            "source": {"provider":"fal", "model":"fal-ai/audio-understanding", "created_at": now_iso()},
        }
    return {"raw": raw, "source": {"provider":"fal","model":"fal-ai/audio-understanding","created_at":now_iso()}}

# ========= LLM JSON extraction/repair =========
def _extract_json_object(text: str) -> str:
    if not text: return ""
    s = text.strip()
    if s.startswith("{") and s.endswith("}"): return s
    start = s.find("{")
    if start == -1: return ""
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    return ""

def call_openai_json(system: str, user: str, model: str="gpt-4o-mini", temperature: float=0.0) -> Dict[str,Any]:
    require_key("OPENAI_KEY", OPENAI_KEY)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type":"application/json"}
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type":"json_object"},
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    if r.status_code >= 300:
        raise HTTPException(502, f"OpenAI failed: {r.status_code} {r.text}")
    txt = r.json()["choices"][0]["message"]["content"]
    return json.loads(txt)

def call_claude_json(system: str, user: str, model: str="claude-sonnet-4-5-20250929", max_tokens: int=5000) -> Dict[str,Any]:
    require_key("CLAUDE_KEY", CLAUDE_KEY)
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": CLAUDE_KEY, "anthropic-version":"2023-06-01", "content-type":"application/json"}
    payload = {
        "model": model,
        "max_tokens": int(max_tokens),
        "temperature": 0.7,
        "system": system,
        "messages": [{"role":"user","content":user}],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=240)
    if r.status_code >= 300:
        raise HTTPException(502, f"Claude failed: {r.status_code} {r.text}")
    data = r.json()
    blocks = data.get("content", [])
    txt = "".join([b.get("text","") for b in blocks if b.get("type")=="text"]).strip()
    try:
        (UPLOADS_DIR / f"claude_last_raw_{int(time.time())}.txt").write_text(txt or "<EMPTY>", encoding="utf-8")
    except Exception:
        pass
    js_txt = _extract_json_object(txt)
    if js_txt:
        try: return json.loads(js_txt)
        except Exception: pass
    if OPENAI_KEY and txt:
        return call_openai_json("You are a strict JSON repair tool. Output ONLY a single valid JSON object.", txt)
    raise HTTPException(502, "Claude returned no JSON. Check data/uploads/claude_last_raw_*.txt")

# v1.6.1: Claude model cascade (most capable → fastest)
CLAUDE_MODEL_CASCADE = [
    "claude-sonnet-4-5-20250929",      # Primary - latest Sonnet 4.5
    "claude-3-5-sonnet-latest",        # Latest stable
    "claude-3-5-sonnet-20241022",      # Older specific
    "claude-3-haiku-20240307",         # Fast fallback
]

def call_llm_json(system: str, user: str, preferred: str = "claude", max_tokens: int = 5000, state: Dict = None) -> Dict[str, Any]:
    """v1.6.1: Call LLM with Claude cascade fallback. OpenAI only as last resort. Tracks cost automatically."""
    require_key("CLAUDE_KEY", CLAUDE_KEY)
    last_error = None
    
    # Try Claude cascade first
    for model in CLAUDE_MODEL_CASCADE:
        try:
            print(f"[INFO] Calling Claude API with {model}...")
            result = call_claude_json(system, user, model=model, max_tokens=max_tokens)
            # v1.6.1: Track cost for successful call
            track_cost(model, 1, state=state)
            return result
        except HTTPException as e:
            last_error = e
            print(f"[WARN] {model} failed ({e.status_code}): {str(e.detail)[:100]}")
            if e.status_code == 400:
                # Bad request - don't retry with different model
                break
        except Exception as e:
            last_error = HTTPException(502, str(e))
            print(f"[WARN] {model} failed: {str(e)[:100]}")
    
    # OpenAI as absolute last resort
    if OPENAI_KEY:
        try:
            print(f"[INFO] All Claude models failed, trying OpenAI as last resort...")
            result = call_openai_json(system, user)
            track_cost("gpt-4o-mini", 1, state=state)
            return result
        except Exception as e:
            print(f"[ERROR] OpenAI also failed: {str(e)[:100]}")
    
    raise last_error or HTTPException(502, "All LLM providers failed")

# ========= Cast helpers =========
def find_cast(state: Dict[str,Any], cast_id: str) -> Optional[Dict[str,Any]]:
    for c in state.get("cast", []):
        if c.get("cast_id") == cast_id:
            return c
    return None

def cast_ref_urls(cast: Dict[str,Any]) -> List[str]:
    """Get reference image URLs for API calls (prefers fal_url for remote processing)."""
    refs = cast.get("reference_images") or []
    urls = []
    for r in refs:
        # v1.4.9: Prefer fal_url for API calls, fallback to url
        url = r.get("fal_url") or r.get("url")
        if url:
            urls.append(url)
    return urls[:3]



def get_identity_url(state: Dict[str,Any], cast_id: str) -> Optional[str]:
    """Prefer canonical styled ref_a from cast_matrix; fallback to first uploaded reference image."""
    cm = state.get("cast_matrix") or {}
    refs = (cm.get("character_refs") or {}).get(cast_id) or {}
    if isinstance(refs, dict) and refs.get("ref_a"):
        return refs["ref_a"]
    c = find_cast(state, cast_id)
    if not c:
        return None
    urls = cast_ref_urls(c)
    return urls[0] if urls else None
# ========= Prompt builder =========
def energy_tokens(e: float) -> List[str]:
    e = float(e or 0.5)
    if e <= 0.3: return ["quiet","minimal motion","slow camera"]
    if e <= 0.7: return ["steady motion","medium intensity"]
    return ["high intensity","aggressive motion","dramatic lighting"]

def build_prompt(state: Dict[str,Any], shot: Dict[str,Any]) -> str:
    st = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    parts: List[str] = []
    parts += style_tokens(st)
    parts += [f"aspect {aspect}"]
    parts += energy_tokens(shot.get("energy",0.5))
    parts += [shot.get("prompt_base",""), shot.get("camera_language",""), shot.get("environment","")]
    if isinstance(shot.get("symbolic_elements"), list):
        parts += shot["symbolic_elements"]
    parts += ["no text","no watermark","no subtitles","no logo"]
    return ", ".join([p.strip() for p in parts if p and str(p).strip()])

# ========= UI Template =========
TEMPLATES_DIR = BASE / "templates"
STATIC_DIR = BASE / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"
STYLE_CSS_PATH = STATIC_DIR / "style.css"
APP_JS_PATH = STATIC_DIR / "app.js"
LOGO_PATH = STATIC_DIR / "logo.png"

def build_index_html() -> str:
    tpl = INDEX_HTML_PATH.read_text(encoding="utf-8")
    style_opts = "\n".join([f'<option value="{k}">{v["label"]}</option>' for k,v in STYLE_PRESETS.items()])
    return (tpl
            .replace("__STYLE_OPTIONS__", style_opts)
            .replace("__DEFAULT_AUDIO_PROMPT__", DEFAULT_AUDIO_PROMPT.replace("`","'")))

@app.get("/static/style.css")
def static_css():
    from fastapi.responses import FileResponse
    return FileResponse(str(STYLE_CSS_PATH), media_type="text/css")

@app.get("/static/app.js")
def static_js():
    from fastapi.responses import Response
    js = APP_JS_PATH.read_text(encoding="utf-8")
    js = js.replace("__DEFAULT_AUDIO_PROMPT__", DEFAULT_AUDIO_PROMPT.replace("`","'"))
    return Response(content=js, media_type="application/javascript")

# v1.5.4: Serve logo
@app.get("/static/logo.png")
def static_logo():
    from fastapi.responses import FileResponse
    return FileResponse(str(LOGO_PATH), media_type="image/png")

@app.get("/renders/{filepath:path}")
def serve_render(filepath: str):
    """v1.6.1: Serve locally stored renders, including project subfolders."""
    from fastapi.responses import FileResponse
    
    file_path = resolve_render_path(filepath)
    
    if not file_path.exists():
        raise HTTPException(404, f"Render not found: {filepath}")
    
    # Determine media type
    media_type = "image/png"
    if filepath.endswith(".jpg") or filepath.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filepath.endswith(".webp"):
        media_type = "image/webp"
    elif filepath.endswith(".mp4"):
        media_type = "video/mp4"
    elif filepath.endswith(".mp3"):
        media_type = "audio/mpeg"
    
    return FileResponse(str(file_path), media_type=media_type)

def resolve_render_path(url_or_path: str) -> Path:
    """v1.6.1: Resolve /renders/ URL or path to actual file path."""
    filepath = url_or_path
    if filepath.startswith("/renders/"):
        filepath = filepath[9:]  # Strip /renders/
    
    # filepath can be: "filename.png" (legacy) or "projects/Title_vX/renders/filename.png" (v1.6.1)
    if filepath.startswith("projects/"):
        return DATA / filepath
    else:
        return RENDERS_DIR / filepath


@app.get("/", response_class=HTMLResponse)
def index():
    return build_index_html()

# ========= API: Project =========
@app.post("/api/project/create")
def api_create_project(payload: Dict[str,Any]):
    state = new_project(
        payload.get("title","New Production"),
        payload.get("style_preset","Anamorphic Cinema"),
        payload.get("aspect","horizontal"),
        payload.get("llm","claude"),
        payload.get("image_model","nanobanana"),
        payload.get("video_model","none"),  # v1.5.6
        payload.get("use_whisper", False),  # v1.5.6
    )
    save_project(state)
    return state

@app.get("/api/project/{project_id}")
def api_get_project(project_id: str):
    return load_project(project_id)

@app.get("/api/project/{project_id}/validate")
def api_validate_project(project_id: str):
    """v1.12: Validate project state and return detailed errors."""
    state = load_project(project_id)
    is_valid, errors = validate_project_state(state, strict=False)
    return {
        "project_id": project_id,
        "is_valid": is_valid,
        "errors": errors,
        "sequences_count": len(state.get("storyboard", {}).get("sequences", [])),
        "shots_count": len(state.get("storyboard", {}).get("shots", [])),
        "cast_count": len(state.get("cast", [])),
    }

# v1.5.6: Update project settings
@app.patch("/api/project/{project_id}/settings")
def api_update_project_settings(project_id: str, payload: Dict[str, Any]):
    """Update project settings like video_model, use_whisper, etc."""
    state = load_project(project_id)
    
    allowed_fields = ["title", "style_preset", "aspect", "video_model", "use_whisper", "audio_locked"]
    updated = []
    
    for field in allowed_fields:
        if field in payload:
            state["project"][field] = payload[field]
            updated.append(field)
    
    # Special handling for image_model - requires re-locking render models
    if "image_model" in payload:
        state["project"]["image_model_choice"] = payload["image_model"]
        state["project"]["render_models"] = locked_render_models(payload["image_model"])
        updated.append("image_model")

    # v1.6.5: Always save settings changes (force=True) regardless of version mismatch
    save_project(state, force=True)
    return {"updated": updated, "project": state["project"]}

@app.get("/api/version")
def api_version():
    """Return API version info."""
    return {"version": VERSION, "name": "BXLSTNRD Video Generator"}

@app.get("/api/costs")
def api_get_costs():
    """v1.4.9: Get session cost tracking info."""
    return {
        "total": round(SESSION_COST["total"], 4),
        "calls": SESSION_COST["calls"][-50:],
        "call_count": len(SESSION_COST["calls"]),
        "pricing_loaded": PRICING_LOADED,
    }

@app.get("/api/project/{project_id}/costs")
def api_get_project_costs(project_id: str):
    """v1.4.9: Get project-specific cost tracking."""
    state = load_project(project_id)
    costs = state.get("costs", {"total": 0.0, "calls": []})
    return {
        "total": round(costs.get("total", 0.0), 4),
        "calls": costs.get("calls", [])[-50:],
        "call_count": len(costs.get("calls", [])),
    }

@app.post("/api/costs/reset")
def api_reset_costs():
    """v1.4: Reset session cost tracking."""
    SESSION_COST["total"] = 0.0
    SESSION_COST["calls"] = []
    return {"reset": True}

@app.post("/api/costs/refresh-pricing")
def api_refresh_pricing():
    """v1.4.2: Refresh pricing from fal.ai API."""
    fetch_live_pricing()
    return {"pricing_loaded": PRICING_LOADED, "model_count": len(API_COSTS)}

# v1.6.1: Test endpoints for API connectivity
@app.get("/api/test/claude")
def api_test_claude():
    """Test Claude API connectivity."""
    if not CLAUDE_KEY:
        return {"ok": False, "error": "CLAUDE_KEY not set"}
    try:
        result = call_claude_json(
            "You are a test. Return ONLY: {\"status\": \"ok\"}",
            "Test connection",
            max_tokens=50
        )
        return {"ok": True, "response": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

@app.get("/api/test/openai")
def api_test_openai():
    """Test OpenAI API connectivity."""
    if not OPENAI_KEY:
        return {"ok": False, "error": "OPENAI_KEY not set"}
    try:
        result = call_openai_json(
            "You are a test. Return ONLY: {\"status\": \"ok\"}",
            "Test connection"
        )
        return {"ok": True, "response": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

# v1.6.1: Clear style lock
@app.post("/api/project/{project_id}/clear_style_lock")
def api_clear_style_lock(project_id: str):
    """Clear style lock to allow re-rendering with different style."""
    state = load_project(project_id)
    state["project"]["style_locked"] = False
    state["project"]["style_lock_image"] = None
    save_project(state)
    return {"style_locked": False, "style_lock_image": None}

@app.post("/api/project/{project_id}/cast/lock")
def api_lock_cast(project_id: str, payload: Dict[str,Any]):
    """v1.4: Lock or unlock cast matrix."""
    state = load_project(project_id)
    locked = payload.get("locked", True)
    state["project"]["cast_locked"] = locked
    save_project(state)
    return {"cast_locked": locked}

# v1.5.3: Update project settings (render_models, etc.)
@app.post("/api/project/{project_id}/settings")
def api_update_settings(project_id: str, payload: Dict[str,Any]):
    """Update project settings like render_models."""
    state = load_project(project_id)
    
    if "render_models" in payload:
        rm = payload["render_models"]
        if "render_models" not in state["project"]:
            state["project"]["render_models"] = {}
        
        if "image_model" in rm:
            state["project"]["render_models"]["image_model"] = rm["image_model"]
        if "img2img_editor" in rm:
            state["project"]["render_models"]["img2img_editor"] = rm["img2img_editor"]
    
    save_project(state)
    return {"updated": True, "render_models": state["project"].get("render_models")}

@app.post("/api/project/import")
def api_import_project(payload: Dict[str,Any]):
    """v1.12.2: Import a project from JSON file."""
    if not payload.get("project") or not payload["project"].get("id"):
        raise HTTPException(400, "Invalid project data: missing project.id")

    # Validate before saving
    is_valid, errors = validate_project_state(payload, strict=False)
    if errors:
        print(f"[WARN] Importing project with validation errors: {errors}")

    # v1.6.5: Update version to current so saves aren't blocked
    payload["project"]["created_version"] = VERSION

    save_project(payload, validate=False, force=True)
    return {"imported": True, "project_id": payload["project"]["id"]}

@app.post("/api/project/{project_id}/llm")
def api_set_llm(project_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)

    llm = (payload.get("llm") or "").strip().lower()
    if llm not in ("claude", "openai"):
        raise HTTPException(400, "llm must be 'claude' or 'openai'")

    state["project"]["llm"] = llm
    save_project(state)
    return {"llm": llm}    

@app.post("/api/project/{project_id}/render_models")
def api_set_render_models(project_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)
    rm = state["project"].get("render_models") or {}
    if payload.get("img2img_editor"):
        rm["img2img_editor"] = str(payload["img2img_editor"])
    state["project"]["render_models"] = rm
    save_project(state)
    return {"render_models": rm}

# ========= API: Audio =========
@app.post("/api/project/{project_id}/audio")
async def api_audio(project_id: str, file: UploadFile = File(...), prompt: str = Form(DEFAULT_AUDIO_PROMPT)):
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.split(".")[-1].lower()
    
    # v1.5.9.1: Save audio to project folder
    audio_dir = get_project_audio_dir(state)
    original_name = sanitize_filename(Path(file.filename or "audio").stem, 30) if file.filename else "track"
    tmp_path = audio_dir / f"{original_name}{ext}"
    tmp_path.write_bytes(await file.read())

    # v1.4: Get accurate duration using librosa/mutagen BEFORE fal.ai call
    local_duration = get_audio_duration(str(tmp_path))
    print(f"[INFO] Local audio duration: {local_duration}s")
    
    # v1.5.8: Get accurate BPM using librosa beat tracking
    local_bpm = get_audio_bpm_librosa(str(tmp_path))
    if local_bpm:
        print(f"[INFO] Local BPM detection (librosa): {local_bpm}")
    else:
        print(f"[WARN] Local BPM detection failed, will use FAL")

    try:
        audio_url = fal_client.upload_file(str(tmp_path))
    except Exception as e:
        return JSONResponse({"error":"fal upload_file failed","detail":str(e)}, status_code=502)

    # v1.5.6: Optionally use Whisper for better transcription
    use_whisper = state.get("project", {}).get("use_whisper", False)
    whisper_transcript = None
    
    if use_whisper:
        print(f"[INFO] Using Whisper for enhanced transcription...")
        try:
            whisper_r = requests.post(FAL_WHISPER, headers=fal_headers(), json={
                "audio_url": audio_url,
                "task": "transcribe",
                "language": "en",  # Auto-detect if empty
                "chunk_level": "segment",
                "version": "3"
            }, timeout=300)
            
            if whisper_r.status_code < 300:
                whisper_data = whisper_r.json()
                whisper_transcript = whisper_data.get("text", "")
                # Track Whisper cost
                duration_for_cost = local_duration or 180
                track_cost("fal-ai/whisper", int(duration_for_cost), state=state)
                print(f"[INFO] Whisper transcription complete: {len(whisper_transcript)} chars")
            else:
                print(f"[WARN] Whisper failed: {whisper_r.status_code}")
        except Exception as e:
            print(f"[WARN] Whisper error: {e}")

    r = requests.post(FAL_AUDIO, headers=fal_headers(), json={"audio_url":audio_url, "prompt":prompt}, timeout=300)
    # v1.5.1: Track cost based on duration ($0.01 per 5 seconds)
    duration_for_cost = local_duration or 180  # Fallback to 3 min estimate
    audio_cost_units = max(1, int(duration_for_cost / 5))  # 5-second units
    track_cost("fal-ai/audio-understanding", audio_cost_units, state=state)
    
    if r.status_code >= 300:
        return JSONResponse({"error":"fal audio-understanding failed","status":r.status_code,"body":r.text}, status_code=502)

    raw = r.json()
    audio_dna = normalize_audio_understanding(raw)
    
    # v1.5.6: Enhance lyrics with Whisper transcript if available
    if whisper_transcript:
        # Replace or supplement lyrics with Whisper transcript
        audio_dna["whisper_transcript"] = whisper_transcript
        # If existing lyrics are empty or minimal, use Whisper
        existing_lyrics = audio_dna.get("lyrics", [])
        if not existing_lyrics or len(existing_lyrics) < 3:
            # Split transcript into lines for lyrics
            lines = [l.strip() for l in whisper_transcript.split("\n") if l.strip()]
            if not lines:
                lines = [s.strip() + "." for s in whisper_transcript.split(".") if s.strip()]
            audio_dna["lyrics"] = [{"text": l} for l in lines[:50]]  # Cap at 50 lines
            audio_dna["lyrics_source"] = "whisper"
        else:
            audio_dna["lyrics_source"] = "audio-understanding"
    
    # v1.4: Use local duration (librosa) if available, otherwise fal.ai duration
    if local_duration:
        if not audio_dna.get("meta"):
            audio_dna["meta"] = {}
        audio_dna["meta"]["duration_sec"] = local_duration
        audio_dna["meta"]["duration_source"] = "librosa"
    elif audio_dna.get("meta") and not audio_dna["meta"].get("duration_sec"):
        d = raw.get("duration_sec") or raw.get("duration") or None
        if d: 
            audio_dna["meta"]["duration_sec"] = safe_float(d, None)
            audio_dna["meta"]["duration_source"] = "fal.ai"

    # v1.5.8: Use librosa BPM if available (much more accurate than FAL)
    if local_bpm:
        if not audio_dna.get("meta"):
            audio_dna["meta"] = {}
        fal_bpm = audio_dna["meta"].get("bpm", 120)
        audio_dna["meta"]["bpm"] = local_bpm
        audio_dna["meta"]["bpm_source"] = "librosa"
        audio_dna["meta"]["bpm_fal"] = fal_bpm  # Keep FAL's guess for reference
        print(f"[INFO] Using librosa BPM {local_bpm} (FAL detected: {fal_bpm})")

    # v1.5: Calculate beat grid for shot timing sync
    duration = audio_dna.get("meta", {}).get("duration_sec", 0)
    bpm = audio_dna.get("meta", {}).get("bpm", 120)
    print(f"[DEBUG] Building beat grid: duration={duration}, bpm={bpm}, types: {type(duration)}, {type(bpm)}")
    beat_grid = build_beat_grid(duration, bpm)
    print(f"[DEBUG] Beat grid result keys: {beat_grid.keys()}")
    audio_dna["beat_grid"] = beat_grid
    print(f"[INFO] Beat grid: {beat_grid.get('total_bars', 0)} bars, {beat_grid.get('total_beats', 0)} beats @ {bpm} BPM")

    state["audio_dna"] = audio_dna
    state["audio_file_path"] = str(tmp_path)  # v1.4: Store local path
    save_project(state)
    return {"audio_url": audio_url, "audio_dna": audio_dna, "local_duration": local_duration, "used_whisper": use_whisper}

# v1.5.8: Update BPM manually
@app.patch("/api/project/{project_id}/audio/bpm")
def api_update_bpm(project_id: str, payload: Dict[str, Any]):
    """Manually update the BPM if auto-detection was wrong."""
    state = load_project(project_id)
    
    new_bpm = payload.get("bpm")
    if not new_bpm or not isinstance(new_bpm, (int, float)) or new_bpm < 40 or new_bpm > 240:
        raise HTTPException(400, "BPM must be a number between 40 and 240")
    
    new_bpm = int(new_bpm)
    
    audio_dna = state.get("audio_dna")
    if not audio_dna:
        raise HTTPException(400, "No audio DNA found")
    
    # Update BPM in meta
    if "meta" not in audio_dna:
        audio_dna["meta"] = {}
    audio_dna["meta"]["bpm"] = new_bpm
    audio_dna["meta"]["bpm_source"] = "manual"
    
    # Recalculate beat grid
    duration = audio_dna.get("meta", {}).get("duration_sec", 0)
    beat_grid = build_beat_grid(duration, new_bpm)
    audio_dna["beat_grid"] = beat_grid
    print(f"[INFO] BPM updated to {new_bpm}, rebuilt beat grid: {beat_grid.get('total_bars', 0)} bars")
    
    state["audio_dna"] = audio_dna
    save_project(state)
    
    return {"bpm": new_bpm, "beat_grid": beat_grid}

# ========= API: Cast =========
@app.post("/api/project/{project_id}/cast")
async def api_cast(project_id: str, file: UploadFile = File(...), role: str = Form("lead"), name: str = Form("")):
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cast_id = f"{role}_{len(state['cast'])+1}"
    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.split(".")[-1].lower()
    
    # v1.5.9.1: Save cast image to project folder
    renders_dir = get_project_renders_dir(state)
    safe_name = sanitize_filename(name or cast_id, 20)
    local_filename = f"Cast_{safe_name}_Source{ext}"
    local_path = renders_dir / local_filename
    file_bytes = await file.read()
    local_path.write_bytes(file_bytes)
    # URL relative to DATA for serve_render
    rel_path = local_path.relative_to(DATA)
    local_url = f"/renders/{rel_path.as_posix()}"
    
    # Also upload to FAL for img2img processing (temp file)
    tmp_path = UPLOADS_DIR / f"temp_{project_id}_{cast_id}{ext}"
    tmp_path.write_bytes(file_bytes)

    try:
        fal_url = fal_client.upload_file(str(tmp_path))
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)
    except Exception as e:
        return JSONResponse({"error":"fal upload_file failed","detail":str(e)}, status_code=502)

    visual_dna = {
        "cast_id": cast_id,
        "name": name,
        "role": role,
        "text_tokens": ["consistent face", "consistent outfit"],
        "reference_images": [{"url": local_url, "fal_url": fal_url, "role": "primary_face", "notes": ""}],
        "conditioning": {
            "identity": {"enabled": True, "strength": 0.75},
            "lora": {"enabled": False, "lora_id": None, "strength": 0.8},
        },
    }
    state["cast"].append(visual_dna)
    save_project(state)
    return {"cast_added": visual_dna}

@app.post("/api/project/{project_id}/cast/{cast_id}/ref")
async def api_cast_add_ref(project_id: str, cast_id: str, file: UploadFile = File(...)):
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cast = find_cast(state, cast_id)
    if not cast: raise HTTPException(404, "Cast not found")
    refs = cast.get("reference_images") or []
    if len(refs) >= 3: raise HTTPException(400, "Max 3 reference images per cast member")

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.split(".")[-1].lower()
    tmp_path = UPLOADS_DIR / f"{project_id}_{cast_id}_ref{len(refs)+1}{ext}"
    tmp_path.write_bytes(await file.read())

    try:
        img_url = fal_client.upload_file(str(tmp_path))
    except Exception as e:
        return JSONResponse({"error":"fal upload_file failed","detail":str(e)}, status_code=502)

    refs.append({"url": img_url, "role": "ref", "notes": ""})
    cast["reference_images"] = refs
    save_project(state)
    return {"cast_updated": cast}

@app.post("/api/project/{project_id}/cast/{cast_id}/lora")
def api_cast_set_lora(project_id: str, cast_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)
    cast = find_cast(state, cast_id)
    if not cast: raise HTTPException(404, "Cast not found")

    lora_id = (payload.get("lora_id") or "").strip() or None
    strength = float(clamp(safe_float(payload.get("strength", 0.8), 0.8), 0.0, 2.0))

    cond = cast.get("conditioning") or {}
    lora = cond.get("lora") or {"enabled": False, "lora_id": None, "strength": 0.8}
    if lora_id:
        lora.update({"enabled": True, "lora_id": lora_id, "strength": strength})
    else:
        lora.update({"enabled": False, "lora_id": None, "strength": strength})
    cond["lora"] = lora
    cast["conditioning"] = cond

    save_project(state)
    return {"cast_updated": cast}

@app.patch("/api/project/{project_id}/cast/{cast_id}")
def api_cast_update(project_id: str, cast_id: str, payload: Dict[str,Any]):
    """v1.4.3: Update cast member properties (name, role, impact, prompt_extra)."""
    state = load_project(project_id)
    cast = find_cast(state, cast_id)
    if not cast: 
        raise HTTPException(404, "Cast not found")

    # Update allowed fields
    if "name" in payload:
        cast["name"] = str(payload["name"]).strip()
    if "role" in payload:
        cast["role"] = str(payload["role"]).strip().lower()
    if "impact" in payload:
        cast["impact"] = clamp(safe_float(payload["impact"], 0.7), 0.0, 1.0)
    if "prompt_extra" in payload:
        cast["prompt_extra"] = str(payload["prompt_extra"]).strip()

    save_project(state)
    return {"cast_updated": cast}

# v1.5.4: Delete cast member
@app.delete("/api/project/{project_id}/cast/{cast_id}")
def api_cast_delete(project_id: str, cast_id: str):
    """Delete a cast member from the project."""
    state = load_project(project_id)
    
    cast_list = state.get("cast", [])
    original_len = len(cast_list)
    state["cast"] = [c for c in cast_list if c.get("cast_id") != cast_id]
    
    if len(state["cast"]) == original_len:
        raise HTTPException(404, "Cast member not found")
    
    # Also remove from character_refs
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    if cast_id in char_refs:
        del char_refs[cast_id]
    
    save_project(state)
    return {"deleted": cast_id}

@app.post("/api/project/{project_id}/cast/{cast_id}/canonical_refs")
def api_cast_generate_canonical_refs(project_id: str, cast_id: str):
    """Generate both ref_a and ref_b for a cast member."""
    state = load_project(project_id)
    editor = locked_editor_key(state)
    require_key("FAL_KEY", FAL_KEY)

    cast = find_cast(state, cast_id)
    if not cast:
        raise HTTPException(404, "Cast not found")

    refs = cast_ref_urls(cast)
    if not refs:
        raise HTTPException(400, "Cast has no reference image")

    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    base_style = ", ".join(style_tokens(style) + ["no text", "no watermark", "clean background"])
    # v1.6.1: Extended negatives - no text/frame/overlay
    negatives = "no props, no objects, no mug, no cup, no drink, no phone, no bag, no accessories, clean hands, no typography, no title, no caption, no overlay, no frame, no border, no logo"
    
    # v1.6.1: Extra prompt has override priority - placed at start of prompt
    extra = cast.get("prompt_extra", "").strip()
    extra_prefix = f"{extra}, " if extra else ""

    # v1.6.1: Style lock - use existing style anchor if present
    style_lock_url = state["project"].get("style_lock_image")
    ref_images = [refs[0]]
    if style_lock_url:
        # Upload style lock image to FAL if it's a local path
        if style_lock_url.startswith("/renders/"):
            local_file = resolve_render_path(style_lock_url)
            if local_file.exists():
                try:
                    uploaded_style_lock = fal_client.upload_file(str(local_file))
                    ref_images.append(uploaded_style_lock)
                    print(f"[INFO] Using style lock image for consistency: {style_lock_url}")
                except Exception as e:
                    print(f"[WARN] Failed to upload style lock image: {e}")
        else:
            ref_images.append(style_lock_url)
            print(f"[INFO] Using style lock image for consistency: {style_lock_url}")

    prompt_a = f"{base_style}, {extra_prefix}full body, standing, three-quarter view, slight angle, neutral pose, clean background, consistent identity, {negatives}"
    prompt_b = f"{base_style}, {extra_prefix}portrait close-up, head and shoulders, three-quarter view, slight angle from side, neutral expression, clean background, consistent identity, {negatives}"

    # v1.5.8: Track costs to session only during generation (not to state, to avoid race)
    ref_a_url = call_img2img_editor(editor, prompt_a, ref_images, aspect)
    track_cost(f"fal-ai/{editor}", 1)  # Session only
    ref_b_url = call_img2img_editor(editor, prompt_b, ref_images, aspect)
    track_cost(f"fal-ai/{editor}", 1)  # Session only

    # v1.6.1: Store locally with friendly names in project folder
    cast_name = sanitize_filename(cast.get("name", cast_id), 20)
    ref_a = download_image_locally(ref_a_url, project_id, f"cast_{cast_id}_ref_a", state=state, friendly_name=f"Cast_{cast_name}_RefA")
    ref_b = download_image_locally(ref_b_url, project_id, f"cast_{cast_id}_ref_b", state=state, friendly_name=f"Cast_{cast_name}_RefB")

    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_state.setdefault("cast_matrix", {}).setdefault("character_refs", {})[cast_id] = {"ref_a": ref_a, "ref_b": ref_b}

        # v1.6.1: Set style lock if this is the first generated ref
        if not fresh_state["project"].get("style_lock_image"):
            fresh_state["project"]["style_locked"] = True
            fresh_state["project"]["style_lock_image"] = ref_a
            print(f"[INFO] Style locked to first generated ref: {ref_a}")

        # Track costs to fresh state (2 renders done)
        editor_cost = API_COSTS.get(f"fal-ai/{editor}", 0.04)
        if "costs" not in fresh_state:
            fresh_state["costs"] = {"total": 0.0, "calls": []}
        fresh_state["costs"]["total"] = round(fresh_state["costs"].get("total", 0) + (editor_cost * 2), 4)
        fresh_state["costs"]["calls"].append({"model": f"fal-ai/{editor}", "cost": round(editor_cost * 2, 4), "ts": time.time()})

        save_project(fresh_state)

    return {"cast_id": cast_id, "editor": editor, "ref_a": ref_a, "ref_b": ref_b, "style_locked": fresh_state["project"].get("style_locked", False)}

@app.post("/api/project/{project_id}/cast/{cast_id}/rerender/{ref_type}")
def api_cast_rerender_single_ref(project_id: str, cast_id: str, ref_type: str):
    """v1.4.7: Rerender only ref_a or ref_b."""
    if ref_type not in ("a", "b"):
        raise HTTPException(400, "ref_type must be 'a' or 'b'")
    
    state = load_project(project_id)
    editor = locked_editor_key(state)
    require_key("FAL_KEY", FAL_KEY)

    cast = find_cast(state, cast_id)
    if not cast:
        raise HTTPException(404, "Cast not found")

    refs = cast_ref_urls(cast)
    if not refs:
        raise HTTPException(400, "Cast has no reference image")

    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    base_style = ", ".join(style_tokens(style) + ["no text", "no watermark", "clean background"])
    # v1.6.1: Extended negatives - no text/frame/overlay
    negatives = "no props, no objects, no mug, no cup, no drink, no phone, no bag, no accessories, clean hands, no typography, no title, no caption, no overlay, no frame, no border, no logo"
    
    # v1.6.1: Extra prompt has override priority - placed at start of prompt
    extra = cast.get("prompt_extra", "").strip()
    extra_prefix = f"{extra}, " if extra else ""

    if ref_type == "a":
        prompt = f"{base_style}, {extra_prefix}full body, standing, three-quarter view, slight angle, neutral pose, clean background, consistent identity, {negatives}"
    else:
        prompt = f"{base_style}, {extra_prefix}portrait close-up, head and shoulders, three-quarter view, slight angle from side, neutral expression, clean background, consistent identity, {negatives}"

    new_url = call_img2img_editor(editor, prompt, [refs[0]], aspect)
    track_cost(f"fal-ai/{editor}", 1)  # Session only
    
    # v1.5.9.1: Store with friendly name in project folder
    cast_name = sanitize_filename(cast.get("name", cast_id), 20)
    local_path = download_image_locally(new_url, project_id, f"cast_{cast_id}_ref_{ref_type}", state=state, friendly_name=f"Cast_{cast_name}_Ref{ref_type.upper()}")
    
    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        char_refs = fresh_state.setdefault("cast_matrix", {}).setdefault("character_refs", {}).setdefault(cast_id, {})
        char_refs[f"ref_{ref_type}"] = local_path

        # Track cost to fresh state
        editor_cost = API_COSTS.get(f"fal-ai/{editor}", 0.04)
        if "costs" not in fresh_state:
            fresh_state["costs"] = {"total": 0.0, "calls": []}
        fresh_state["costs"]["total"] = round(fresh_state["costs"].get("total", 0) + editor_cost, 4)
        fresh_state["costs"]["calls"].append({"model": f"fal-ai/{editor}", "cost": round(editor_cost, 4), "ts": time.time()})

        save_project(fresh_state)

    return {"cast_id": cast_id, "ref_type": ref_type, "url": local_path}   

# v1.5.3: Upload ref image directly from file
@app.post("/api/project/{project_id}/cast/{cast_id}/ref/{ref_type}")
async def api_cast_upload_ref(project_id: str, cast_id: str, ref_type: str, file: UploadFile = File(...)):
    """Upload a custom ref image (a or b) for a cast member."""
    if ref_type not in ("a", "b"):
        raise HTTPException(400, "ref_type must be 'a' or 'b'")
    
    state = load_project(project_id)
    cast = next((c for c in state.get("cast", []) if c.get("cast_id") == cast_id), None)
    if not cast:
        raise HTTPException(404, "Cast member not found")
    
    # v1.5.9.1: Save uploaded file to project folder
    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        ext = ".png"
    
    renders_dir = get_project_renders_dir(state)
    cast_name = sanitize_filename(cast.get("name", cast_id), 20)
    local_filename = f"Cast_{cast_name}_Ref{ref_type.upper()}{ext}"
    local_path = renders_dir / local_filename
    
    contents = await file.read()
    with open(local_path, "wb") as f:
        f.write(contents)
    
    # URL relative to DATA
    rel_path = local_path.relative_to(DATA)
    local_url = f"/renders/{rel_path.as_posix()}"
    
    # Update state
    char_refs = state.setdefault("cast_matrix", {}).setdefault("character_refs", {}).setdefault(cast_id, {})
    char_refs[f"ref_{ref_type}"] = local_url
    save_project(state)
    
    return {"cast_id": cast_id, "ref_type": ref_type, "url": local_url}

@app.post("/api/project/{project_id}/castmatrix/scenes/autogen")
def api_castmatrix_autogen_scenes(project_id: str, payload: Dict[str,Any]):
    """v1.4: Generate scenes based on timeline sequences (not random!)"""
    state = load_project(project_id)
    llm = payload.get("llm","claude")
    
    # v1.4: Get sequences from timeline
    sequences = state.get("storyboard", {}).get("sequences", [])
    if not sequences:
        raise HTTPException(400, "No sequences found. Create Timeline first.")
    
    count = len(sequences)
    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    story_summary = state.get("storyboard", {}).get("story_summary", "")
    
    # v1.4: Build detailed context from sequences
    seq_context = []
    for seq in sequences:
        seq_context.append({
            "sequence_id": seq.get("sequence_id"),
            "label": seq.get("label"),
            "structure_type": seq.get("structure_type"),
            "description": seq.get("description"),
            "arc_start": seq.get("arc_start"),
            "arc_end": seq.get("arc_end"),
            "energy": seq.get("energy"),
            "cast": seq.get("cast", []),
        })

    schema_hint = '''{ "scenes":[ { 
        "scene_id":"scene_01",
        "sequence_id":"seq_01",
        "title":"Scene title matching sequence label",
        "prompt":"location, time of day, camera setup, mood, key props, atmosphere - matching the sequence's story beat",
        "decor_alt_prompt":"OPTIONAL: Alternative location/decor for flashbacks, dream sequences, or split-timeline shots. Leave empty if not needed.",
        "wardrobe":"Describe character costumes/outfits for THIS scene. Can differ from default based on story context (e.g. formal event, flashback, work uniform, transformation)"
    } ] }'''

    system = (
        "Return ONLY valid JSON. No prose.\n"
        f"Generate exactly {count} scene prompts for a music video - ONE scene per sequence.\n\n"
        "CRITICAL: Each scene MUST match its corresponding sequence:\n"
        "- scene_01 matches seq_01, scene_02 matches seq_02, etc.\n"
        "- The scene title should relate to the sequence label\n"
        "- The scene prompt should visualize the sequence's description and emotional arc\n"
        "- Match the energy level (high energy = dynamic lighting, low = moody)\n"
        "- Consider the structure_type (intro = establishing, chorus = impactful, outro = resolution)\n\n"
        "Each prompt MUST include: location, time of day, camera setup, mood, key props.\n"
        "These are LOCATION PLATES only - no characters in prompts.\n\n"
        "ALTERNATIVE DECOR (decor_alt_prompt):\n"
        "- Use ONLY when narratively justified: flashbacks, dream sequences, parallel timelines, dramatic contrasts\n"
        "- Examples: Present-day apartment vs childhood home; Glamorous party vs lonely aftermath\n"
        "- Leave empty string if the scene doesn't need an alternative perspective\n"
        "- Not every scene needs this - use sparingly for maximum impact\n\n"
        "WARDROBE: Describe what characters should WEAR in each scene.\n"
        "- This can OVERRIDE the character's default outfit based on story needs\n"
        "- Examples: 'elegant evening gowns and tuxedos' for gala, 'casual streetwear' for flashback, 'work uniforms' for job scene\n"
        "- Leave empty string if default character outfit is appropriate\n"
        f"Schema:\n{schema_hint}\n"
    )

    user = json.dumps({
        "story_summary": story_summary,
        "sequences": seq_context,
        "style_preset": style,
        "style_tokens": style_tokens(style),
        "style_notes": style_script_notes(style),
        "aspect": aspect,
    }, ensure_ascii=False)

    # v1.4: Log LLM call
    log_llm_call("scenes/autogen", system, user, None, project_id)
    
    # v1.6.1: Use fallback-enabled LLM call with automatic cost tracking
    js = call_llm_json(system, user, preferred=llm, state=state)
    
    # v1.4: Log response
    log_llm_call("scenes/autogen_response", system, user, js, project_id)
    
    # v1.5.9.1: Save to project folder
    save_llm_response(state, "scenes_autogen", {"response": js})
    
    scenes = js.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != count:
        raise HTTPException(502, f"LLM returned invalid scenes count ({len(scenes) if scenes else 0} vs {count}): {js}")

    cleaned = []
    for i, sc in enumerate(scenes):
        seq = sequences[i] if i < len(sequences) else {}
        scene_id = f"scene_{i+1:02d}"
        cleaned.append({
            "scene_id": scene_id,
            "sequence_id": seq.get("sequence_id", f"seq_{i+1:02d}"),
            "title": (sc.get("title") or seq.get("label") or scene_id).strip(),
            "prompt": (sc.get("prompt") or "").strip(),
            "decor_alt_prompt": (sc.get("decor_alt_prompt") or "").strip(),  # v1.6.2: Alt decor prompt
            "wardrobe": (sc.get("wardrobe") or "").strip(),  # v1.6.1: Scene-specific wardrobe override
            "structure_type": seq.get("structure_type", "verse"),
            "energy": seq.get("energy", 0.5),
            "decor_refs": [],
            "decor_alt": None,  # v1.6.2: Alt decor ref
            "output_url": None,
        })

    state.setdefault("cast_matrix", {})["scenes"] = cleaned
    save_project(state)
    return {"scenes": cleaned, "llm": llm, "sequence_count": len(sequences)}

@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/render")
def api_castmatrix_render_scene(project_id: str, scene_id: str):
    """v1.4: Render scene plates (1 decor ref), save locally."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    # v1.6.2: Check if decor is locked
    if scene.get("decor_locked"):
        raise HTTPException(400, "Scene decor is locked. Unlock to re-render.")

    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]

    # v1.6.3: CRITICAL - Scene decors must NEVER contain people
    no_people = "empty location, no people, no person, no human, no figure, no silhouette, no character, no faces, no hands, no body, uninhabited, deserted, vacant space"
    
    base_prompt = ", ".join(style_tokens(style) + [
        scene["prompt"],
        no_people,
        "no text",
        "no watermark",
        "wide establishing shot",
    ])

    image_size = "landscape_16_9" if aspect=="horizontal" else ("portrait_16_9" if aspect=="vertical" else "square_hd")

    decor_refs = []
    
    # Render 1 establishing shot per scene - v1.5.9.1: with retry
    url, model_name = call_t2i_with_retry(state, base_prompt, image_size)
    track_cost(f"fal-ai/{model_name}", 1, state=state)
    
    # v1.5.9.1: Friendly name with scene number
    scene_num = scene_id.replace("scene_", "")
    local_url = download_image_locally(url, project_id, f"{scene_id}_decor", state=state, friendly_name=f"Sce{scene_num}_Decor")
    decor_refs.append(local_url)

    # v1.6.2: Render alt decor if prompt exists
    decor_alt = None
    alt_prompt = scene.get("decor_alt_prompt", "").strip()
    if alt_prompt:
        alt_base_prompt = ", ".join(style_tokens(style) + [
            alt_prompt,
            no_people,
            "no text",
            "no watermark",
            "wide establishing shot",
        ])
        alt_url, alt_model = call_t2i_with_retry(state, alt_base_prompt, image_size)
        track_cost(f"fal-ai/{alt_model}", 1, state=state)
        decor_alt = download_image_locally(alt_url, project_id, f"{scene_id}_decor_alt", state=state, friendly_name=f"Sce{scene_num}_DecorAlt")
        print(f"[INFO] Generated alt decor for {scene_id}")

    # v1.6.6: Auto-generate wardrobe preview if wardrobe is defined
    wardrobe_ref = None
    wardrobe_text = scene.get("wardrobe", "").strip()
    if wardrobe_text:
        try:
            wardrobe_ref = _generate_wardrobe_ref_internal(project_id, scene_id, state, scene, wardrobe_text, scene_num)
            print(f"[INFO] Generated wardrobe preview for {scene_id}")
        except Exception as e:
            print(f"[WARN] Failed to generate wardrobe preview for {scene_id}: {e}")

    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_cm = fresh_state.get("cast_matrix") or {}
        fresh_scenes = fresh_cm.get("scenes") or []
        fresh_scene = next((s for s in fresh_scenes if s.get("scene_id") == scene_id), None)
        if fresh_scene:
            fresh_scene["decor_refs"] = decor_refs
            if decor_alt:
                fresh_scene["decor_alt"] = decor_alt
            if wardrobe_ref:
                fresh_scene["wardrobe_ref"] = wardrobe_ref
            save_project(fresh_state)

    return {"scene_id": scene_id, "decor_refs": decor_refs, "decor_alt": decor_alt, "wardrobe_ref": wardrobe_ref}

# v1.6.5: Generate alt decor for a scene
@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/decor_alt")
def api_castmatrix_scene_decor_alt(project_id: str, scene_id: str, payload: Dict[str, Any] = None):
    """Generate an alt decor image for the scene."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id") == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    payload = payload or {}
    alt_prompt = payload.get("prompt", "").strip()

    aspect = state["project"]["aspect"]
    style = state["project"]["style_preset"]
    style_toks = style_tokens(style)

    # Build prompt: base prompt + alt prompt + no people
    base_prompt = scene.get("prompt", "").strip()
    no_people = "no people, no person, no human, no figure, no silhouette, no character, no faces, no hands, no body"

    if alt_prompt:
        full_prompt = ", ".join(style_toks + [base_prompt, alt_prompt, no_people])
    else:
        # Just regenerate with slight variation
        full_prompt = ", ".join(style_toks + [base_prompt, "alternative angle or lighting variation", no_people])

    # Generate using text-to-image
    model = locked_model_key(state)
    result_url = call_txt2img(model, full_prompt, aspect, state)
    track_cost(f"fal-ai/{model}", 1, state=state)

    # Save locally
    scene_num = scene_id.replace("scene_", "")
    scene_title = sanitize_filename(scene.get("title", scene_id), 20)
    local_path = download_image_locally(result_url, project_id, f"scene_{scene_id}_decor_alt", state=state, friendly_name=f"Sce{scene_num}_{scene_title}_DecorAlt")

    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_cm = fresh_state.get("cast_matrix") or {}
        fresh_scenes = fresh_cm.get("scenes") or []
        fresh_scene = next((s for s in fresh_scenes if s.get("scene_id") == scene_id), None)
        if fresh_scene:
            fresh_scene["decor_alt"] = local_path
            if alt_prompt:
                fresh_scene["decor_alt_prompt"] = alt_prompt
            save_project(fresh_state, force=True)

    print(f"[INFO] Generated alt decor for {scene_id}")
    return {"scene_id": scene_id, "decor_alt": local_path}

# v1.5.4: Edit scene with custom prompt (img2img)
@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/edit")
def api_castmatrix_edit_scene(project_id: str, scene_id: str, payload: Dict[str,Any]):
    """Edit scene using img2img with current image + edit prompt."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    edit_prompt = payload.get("edit_prompt", "").strip()
    if not edit_prompt:
        raise HTTPException(400, "Missing edit_prompt")
    
    # Get current scene image
    current_image = scene.get("decor_refs", [None])[0]
    if not current_image:
        raise HTTPException(400, "Scene has no image to edit")
    
    # Upload current image as reference
    if current_image.startswith("/renders/"):
        local_file = RENDERS_DIR / current_image.replace("/renders/", "")
        if local_file.exists():
            uploaded_url = fal_client.upload_file(str(local_file))
        else:
            raise HTTPException(400, "Scene image file not found")
    else:
        uploaded_url = current_image
    
    aspect = state["project"]["aspect"]
    style = state["project"]["style_preset"]
    
    # v1.6.3: CRITICAL - Scene decors must NEVER contain people
    no_people = "no people, no person, no human, no figure, no silhouette, no character, no faces, no hands, no body"
    
    # Build full prompt with no-people constraint
    full_prompt = ", ".join(style_tokens(style) + [edit_prompt, no_people])
    
    # Call img2img
    editor = locked_editor_key(state)
    result_url = call_img2img_editor(editor, full_prompt, [uploaded_url], aspect, state)
    
    # v1.5.9.1: Save locally with friendly name
    scene_num = scene_id.replace("scene_", "")
    local_url = download_image_locally(result_url, project_id, f"{scene_id}_edit", state=state, friendly_name=f"Sce{scene_num}_Edit")

    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_cm = fresh_state.get("cast_matrix") or {}
        fresh_scenes = fresh_cm.get("scenes") or []
        fresh_scene = next((s for s in fresh_scenes if s.get("scene_id") == scene_id), None)
        if fresh_scene:
            fresh_scene["decor_refs"] = [local_url]
            save_project(fresh_state)

    return {"scene_id": scene_id, "image_url": local_url}

# v1.6.1: Update scene wardrobe
@app.patch("/api/project/{project_id}/castmatrix/scene/{scene_id}/wardrobe")
def api_castmatrix_update_wardrobe(project_id: str, scene_id: str, payload: Dict[str,Any]):
    """Update scene-specific wardrobe/costume description."""
    state = load_project(project_id)

    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    wardrobe = payload.get("wardrobe", "").strip()
    scene["wardrobe"] = wardrobe
    save_project(state)
    
    print(f"[INFO] Updated wardrobe for {scene_id}: {wardrobe[:50]}..." if wardrobe else f"[INFO] Cleared wardrobe for {scene_id}")
    return {"scene_id": scene_id, "wardrobe": wardrobe}

# v1.6.2: Toggle scene decor lock
@app.patch("/api/project/{project_id}/castmatrix/scene/{scene_id}/decor_lock")
def api_castmatrix_scene_decor_lock(project_id: str, scene_id: str, payload: Dict[str,Any]):
    """Lock/unlock scene decor to prevent re-rendering."""
    state = load_project(project_id)
    
    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    locked = payload.get("locked", False)
    scene["decor_locked"] = locked
    save_project(state)
    
    print(f"[INFO] Scene {scene_id} decor {'locked' if locked else 'unlocked'}")
    return {"scene_id": scene_id, "decor_locked": locked}

# v1.6.2: Toggle scene wardrobe lock
@app.patch("/api/project/{project_id}/castmatrix/scene/{scene_id}/wardrobe_lock")
def api_castmatrix_scene_wardrobe_lock(project_id: str, scene_id: str, payload: Dict[str,Any]):
    """Lock/unlock scene wardrobe to prevent editing."""
    state = load_project(project_id)
    
    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    locked = payload.get("locked", False)
    scene["wardrobe_locked"] = locked
    save_project(state)
    
    print(f"[INFO] Scene {scene_id} wardrobe {'locked' if locked else 'unlocked'}")
    return {"scene_id": scene_id, "wardrobe_locked": locked}

# v1.6.2: Generate wardrobe preview image (cast ref_a + decor + wardrobe)
# v1.6.6: Refactored to use _generate_wardrobe_ref_internal helper
@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/wardrobe_ref")
def api_castmatrix_scene_wardrobe_ref(project_id: str, scene_id: str):
    """Generate a wardrobe preview: lead cast ref_a composited with scene decor and wardrobe."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)
    
    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    wardrobe = scene.get("wardrobe", "").strip()
    if not wardrobe:
        raise HTTPException(400, "Scene has no wardrobe defined")
    
    scene_num = scene_id.replace("scene_", "")
    local_path = _generate_wardrobe_ref_internal(project_id, scene_id, state, scene, wardrobe, scene_num)
    
    if not local_path:
        raise HTTPException(400, "No cast reference available for wardrobe preview")
    
    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_scene = next((s for s in fresh_state.get("cast_matrix", {}).get("scenes", []) if s.get("scene_id")==scene_id), None)
        if fresh_scene:
            fresh_scene["wardrobe_ref"] = local_path
        save_project(fresh_state)
    
    print(f"[INFO] Generated wardrobe preview for {scene_id}")
    return {"scene_id": scene_id, "wardrobe_ref": local_path}
@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/import")
async def api_castmatrix_import_scene(project_id: str, scene_id: str, file: UploadFile = File(...)):
    """Import custom image for scene decor."""
    state = load_project(project_id)
    
    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")
    
    # v1.5.9.1: Save uploaded file to project folder
    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.split(".")[-1].lower()
    
    renders_dir = get_project_renders_dir(state)
    scene_num = scene_id.replace("scene_", "")
    local_filename = f"Sce{scene_num}_Import{ext}"
    local_path = renders_dir / local_filename
    local_path.write_bytes(await file.read())
    
    # URL relative to DATA
    rel_path = local_path.relative_to(DATA)
    local_url = f"/renders/{rel_path.as_posix()}"
    scene["decor_refs"] = [local_url]
    save_project(state)
    
    return {"scene_id": scene_id, "image_url": local_url}

@app.post("/api/project/{project_id}/castmatrix/scene/{scene_id}/generate")
def api_castmatrix_generate_scene(project_id: str, scene_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    cast_id = (payload.get("cast_id") or "").strip()
    if not cast_id:
        raise HTTPException(400, "Missing cast_id")

    cm = state.get("cast_matrix") or {}
    scenes = cm.get("scenes") or []
    scene = next((s for s in scenes if s.get("scene_id")==scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    # need canonical ref
    char_refs = (cm.get("character_refs") or {}).get(cast_id)
    if not char_refs or not char_refs.get("ref_a"):
        raise HTTPException(400, "Missing character canonical refs. Generate them first.")

    style = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    editor = locked_editor_key(state)  # v1.11: hard-locked by project image_model_choice

    # v1.6.3: CRITICAL - Scene decors must NEVER contain people
    no_people = "empty location, no people, no person, no human, no figure, no silhouette, no character, no faces, no hands, no body, uninhabited, deserted, vacant space"
    
    # 4 decor refs via T2I (cheap plates)
    base_prompt = ", ".join(style_tokens(style) + [
        scene["prompt"],
        no_people,
        "no text",
        "no watermark",
        ])

    image_size = "landscape_16_9" if aspect=="horizontal" else ("portrait_16_9" if aspect=="vertical" else "square_hd")

    decor_prompts = [
        base_prompt + ", wide establishing shot",
    ]

    decor_refs = []
    for dp in decor_prompts:
        # v1.5.9.1: Use retry helper
        url, _model_name = call_t2i_with_retry(state, dp, image_size)
        decor_refs.append(url)

    # decor_2: same room, different viewpoint (img2img off decor_1)
    decor2_prompt = base_prompt + ", same room, different camera angle, different framing, consistent architecture, consistent lighting"
    decor_2 = call_img2img_editor(editor, decor2_prompt, [decor_refs[0]], aspect)
    decor_refs.append(decor_2)

# ========= API: Build sequences =========
@app.post("/api/project/{project_id}/sequences/build")
def api_build_sequences(project_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)
    llm = payload.get("llm","claude")

    if not state.get("audio_dna"): raise HTTPException(400, "AudioDNA missing. Upload audio first.")
    if not state.get("cast"): raise HTTPException(400, "Cast missing. Add at least 1 cast member first.")

    meta = (state.get("audio_dna") or {}).get("meta") or {}
    duration_sec = meta.get("duration_sec")
    seq_count, target_shots = target_sequences_and_shots(duration_sec)
    bpm = meta.get("bpm")
    beat_grid = build_beat_grid(float(duration_sec or 180.0), int(bpm) if bpm else None)

    # Extract story and lyrics info
    story_arc = state.get("audio_dna", {}).get("story_arc", {})
    lyrics = state.get("audio_dna", {}).get("lyrics", [])
    structure = state.get("audio_dna", {}).get("structure", [])
    
    # Build cast info with roles
    cast_info = []
    for c in state["cast"]:
        role = c.get("role", "extra")
        cast_info.append({
            "cast_id": c["cast_id"],
            "role": role,
            "name": c.get("name", ""),
            "wardrobe": c.get("prompt_extra", ""),  # v1.5.9.1: Include wardrobe/costume hints
            "role_description": "PROTAGONIST - main focus, most screen time" if role == "lead" 
                else "SUPPORTING - secondary focus, reacts to lead, some solo moments" if role == "supporting"
                else "BACKGROUND/EXTRA - atmosphere, crowd, brief appearances"
        })

    style = state["project"]["style_preset"]
    schema_hint = '''{ 
        "story_summary": "One paragraph summary of the visual narrative arc for this song",
        "sequences": [ { 
            "sequence_id":"seq_01",
            "label":"Scene Title",
            "start":0.0,
            "end":12.3,
            "structure_type":"intro|verse|prechorus|chorus|bridge|breakdown|outro|instrumental",
            "energy":0.5,
            "cast":["lead_1"],
            "arc_start":"Emotional/visual state at start",
            "arc_end":"Emotional/visual state at end",
            "description":"What happens, what changes, connection to lyrics",
            "lyrics_reference":"Key lyric line this sequence visualizes",
            "start_frame_prompt":"...",
            "end_frame_prompt":"..." 
        } ] 
    }'''

    system = (
        "Return ONLY valid JSON. No prose. No markdown. No code fences.\n"
        "Your entire response MUST be a single JSON object.\n\n"
        f"TASK: Create a visual storyboard for a {duration_sec}s music video with {seq_count} sequences.\n\n"
        "CRITICAL RULES:\n"
        "1. LEAD cast members are the PROTAGONIST - they appear in MOST sequences, especially choruses\n"
        "2. SUPPORTING cast members are SECONDARY - they appear in verses and bridges, interact with lead\n"
        "3. EXTRA cast members are BACKGROUND - brief appearances, crowd shots, atmosphere\n"
        "4. Each sequence MUST connect to the song's LYRICS and STORY - reference specific lines!\n"
        "5. The visual narrative must follow the song's emotional arc (intro→build→climax→resolution)\n"
        "6. Sequences must match the song STRUCTURE - intro sequences feel like intros, choruses are high energy\n"
        f"7. TIMING IS CRITICAL: First sequence starts at 0.0, last sequence ends at EXACTLY {duration_sec}. NO sequence may end after {duration_sec}!\n"
        "8. Energy levels should follow the song dynamics\n\n"
        f"AUDIO DURATION: {duration_sec} seconds. The final sequence MUST end at {duration_sec}, not before, not after.\n\n"
        f"Schema:\n{schema_hint}\n"
    )

    user = json.dumps({
        "project": state["project"],
        "style_notes": style_script_notes(style),
        "song_story": story_arc,
        "song_structure": structure,
        "lyrics_preview": " | ".join([l.get("text","") for l in lyrics[:20]]) if lyrics else "No lyrics available",
        "audio_meta": meta,
        "beat_grid": beat_grid,  # Beat grid dict
        "targets": {"sequence_count": seq_count, "target_shots": target_shots, "duration_sec": duration_sec},
        "cast": cast_info,
    }, ensure_ascii=False)

    # v1.6.1: Use fallback-enabled LLM call with automatic cost tracking
    sb = call_llm_json(system, user, preferred=llm, state=state)
    
    # v1.5.9.1: Save raw LLM response for debugging/optimization
    save_llm_response(state, "sequences_build", {"request": {"system": system[:500], "user": user[:500]}, "response": sb})
    
    sequences = sb.get("sequences")
    if not isinstance(sequences, list) or not sequences:
        raise HTTPException(502, f"LLM returned invalid sequences: {sb}")

    # Store story summary
    story_summary = sb.get("story_summary", "")

    valid_cast = {c["cast_id"] for c in state["cast"]}
    cleaned = []
    for i, seq in enumerate(sequences, start=1):
        sequence_id = seq.get("sequence_id") or f"seq_{i:02d}"
        cleaned.append({
            "sequence_id": sequence_id,
            "label": (seq.get("label") or "").strip() or sequence_id,
            "start": safe_float(seq.get("start", 0.0)),
            "end": safe_float(seq.get("end", 0.0)),
            "structure_type": normalize_structure_type(seq.get("structure_type","verse")),
            "energy": float(clamp(safe_float(seq.get("energy",0.5)), 0.0, 1.0)),
            "cast": [cid for cid in (seq.get("cast") or []) if cid in valid_cast],
            "arc_start": (seq.get("arc_start") or "").strip(),
            "arc_end": (seq.get("arc_end") or "").strip(),
            "description": (seq.get("description") or "").strip(),
            "lyrics_reference": (seq.get("lyrics_reference") or "").strip(),
            "start_frame_prompt": (seq.get("start_frame_prompt") or "").strip(),
            "end_frame_prompt": (seq.get("end_frame_prompt") or "").strip(),
        })

    state["storyboard"]["sequences"] = cleaned
    state["storyboard"]["shots"] = []
    state["storyboard"]["story_summary"] = story_summary
    
    # v1.5.2: Cap sequences to actual audio duration
    actual_duration = float(duration_sec or 180.0)
    final_sequences = []
    for seq in cleaned:
        # Skip sequences that start after audio ends
        if seq["start"] >= actual_duration:
            print(f"[WARN] Skipping sequence {seq['sequence_id']} - starts after audio ends ({seq['start']} >= {actual_duration})")
            continue
        # Cap end time to audio duration
        if seq["end"] > actual_duration:
            print(f"[INFO] Capping sequence {seq['sequence_id']} end from {seq['end']} to {actual_duration}")
            seq["end"] = actual_duration
        final_sequences.append(seq)
    
    state["storyboard"]["sequences"] = final_sequences
    save_project(state)
    return {"sequences": final_sequences, "story_summary": story_summary, "targets": {"sequence_count": seq_count, "target_shots": target_shots}, "llm": llm}

# ========= API: Repair Timeline =========
@app.post("/api/project/{project_id}/sequences/repair")
def api_repair_sequences(project_id: str):
    """v1.5.2: Fix sequences that exceed audio duration without regenerating."""
    state = load_project(project_id)
    
    meta = (state.get("audio_dna") or {}).get("meta") or {}
    actual_duration = float(meta.get("duration_sec") or 180.0)
    
    sequences = state.get("storyboard", {}).get("sequences", [])
    if not sequences:
        raise HTTPException(400, "No sequences to repair")
    
    repaired = []
    removed = []
    capped = []
    
    for seq in sequences:
        seq_id = seq.get("sequence_id", "unknown")
        start = float(seq.get("start", 0))
        end = float(seq.get("end", 0))
        
        # Skip sequences that start after audio ends
        if start >= actual_duration:
            removed.append(seq_id)
            continue
        
        # Cap end time to audio duration
        if end > actual_duration:
            seq["end"] = actual_duration
            capped.append(seq_id)
        
        # Fix start >= end
        if seq["start"] >= seq["end"]:
            removed.append(seq_id)
            continue
            
        repaired.append(seq)
    
    # Also repair shots that reference removed sequences or exceed duration
    shots = state.get("storyboard", {}).get("shots", [])
    valid_seq_ids = {s["sequence_id"] for s in repaired}
    repaired_shots = []
    
    for shot in shots:
        shot_start = float(shot.get("start", 0))
        shot_end = float(shot.get("end", 0))
        
        # Skip shots from removed sequences
        if shot.get("sequence_id") not in valid_seq_ids:
            continue
        
        # Skip shots that start after audio ends
        if shot_start >= actual_duration:
            continue
            
        # Cap shot end time
        if shot_end > actual_duration:
            shot["end"] = actual_duration
        
        # Skip invalid shots
        if shot["start"] >= shot["end"]:
            continue
            
        repaired_shots.append(shot)
    
    state["storyboard"]["sequences"] = repaired
    state["storyboard"]["shots"] = repaired_shots
    save_project(state)
    
    return {
        "repaired_sequences": len(repaired),
        "removed_sequences": removed,
        "capped_sequences": capped,
        "repaired_shots": len(repaired_shots),
        "audio_duration": actual_duration
    }

# ========= API: Expand sequences to shots =========
@app.post("/api/project/{project_id}/shots/expand_all")
def api_expand_all(project_id: str):
    state = load_project(project_id)
    seqs = state.get("storyboard", {}).get("sequences", [])
    if not seqs: raise HTTPException(400, "No sequences. Build sequences first.")

    meta = (state.get("audio_dna") or {}).get("meta") or {}
    duration_sec = float(meta.get("duration_sec") or 180.0)
    valid_cast = {c["cast_id"] for c in state.get("cast", []) if c.get("cast_id")}
    style = state["project"]["style_preset"]

    # v1.6.5: Build name-to-id mapping for resolving LLM responses that use names instead of IDs
    name_to_id = {}
    for c in state.get("cast", []):
        if c.get("name"):
            name_to_id[c["name"].lower().strip()] = c["cast_id"]
        if c.get("cast_id"):
            name_to_id[c["cast_id"].lower()] = c["cast_id"]

    # v1.5.3: Build cast info with roles and impact for shot distribution
    cast_info = []
    for c in state.get("cast", []):
        role = c.get("role", "extra")
        impact = c.get("impact", 0.1 if role == "extra" else (0.5 if role == "supporting" else 0.7))
        cast_info.append({
            "cast_id": c["cast_id"],
            "name": c.get("name", ""),
            "role": role.upper(),
            "impact": f"{int(impact*100)}%",
            "wardrobe": c.get("prompt_extra", ""),  # v1.5.9.1: Include wardrobe/costume hints
            "usage": "MUST appear in most shots" if role == "lead" else (
                "Should appear in ~half the shots" if role == "supporting" else
                "Should appear in at least 1-2 shots total"
            )
        })

    all_shots: List[Dict[str,Any]] = []
    for seq in seqs:
        # v1.6.5: Updated schema to include per-shot wardrobe
        schema_hint = '{ "shots": [ { "shot_id":"seq_01_sh01","start":0.0,"end":1.2,"energy":0.0,"structure_type":"verse","cast":["lead_1"],"wardrobe":{"lead_1":"specific wardrobe for this shot"},"intent":"...","camera_language":"...","environment":"...","symbolic_elements":["..."],"prompt_base":"..." } ] }'
        system = (
            "Return ONLY valid JSON. No prose. No markdown.\n"
            "Expand ONE sequence into 5 to 8 shots.\n"
            "Shots must fit within the sequence start/end. No gaps, no overlaps.\n"
            "SHOT DURATION: Each shot should be 2-5 seconds. NEVER exceed 5 seconds per shot.\n"
            "CRITICAL CAST RULES:\n"
            "- LEAD cast members appear in MOST shots (70%+)\n"
            "- SUPPORTING cast members appear in about HALF the shots (50%)\n"
            "- EXTRA cast members MUST appear in at least 1-2 shots across the video\n"
            "- EVERY cast member must appear somewhere in the video!\n"
            "- Use the cast[] array to specify which cast_ids appear in each shot\n"
            "WARDROBE PER SHOT (v1.6.5):\n"
            "- Use the wardrobe object to specify costume/clothing for EACH cast member in EACH shot\n"
            "- Key is cast_id, value is the wardrobe description for that character in this specific shot\n"
            "- Wardrobe can change between shots (e.g., 'disheveled' in verse, 'formal suit' in chorus)\n"
            "- DO NOT put wardrobe in prompt_base, use the wardrobe field instead\n\n"
            f"Schema hint:\n{schema_hint}\n"
        )
        user = json.dumps({
            "sequence": seq,
            "duration_sec": duration_sec,
            "style_notes": style_script_notes(style),
            "cast": cast_info,  # v1.5.3: Include full cast info
        }, ensure_ascii=False)

        llm = (state.get("project") or {}).get("llm","claude")
        # v1.6.1: Use fallback-enabled LLM call with automatic cost tracking
        sb = call_llm_json(system, user, preferred=llm, state=state)
        
        # v1.5.9.1: Save raw LLM response
        save_llm_response(state, f"shots_expand_{seq['sequence_id']}", {"request": {"user": user[:500]}, "response": sb})
        
        shots = sb.get("shots")
        if not isinstance(shots, list) or not shots:
            continue

        for j, sh in enumerate(shots, start=1):
            shot_id = sh.get("shot_id") or f"{seq['sequence_id']}_sh{j:02d}"
            start = safe_float(sh.get("start", seq["start"]))
            end = safe_float(sh.get("end", seq["end"]))
            
            # v1.5.3: Warn about long shots but don't cap (would create gaps)
            duration = end - start
            if duration > 5.0:
                print(f"[WARN] Shot {shot_id} is {duration:.1f}s (>5s recommended)")
            
            # v1.6.5: Resolve cast names/ids to valid cast_ids
            resolved_cast = []
            for cid in (sh.get("cast") or []):
                cid_lower = str(cid).lower().strip()
                if cid_lower in name_to_id:
                    resolved_id = name_to_id[cid_lower]
                    if resolved_id not in resolved_cast:
                        resolved_cast.append(resolved_id)
                        print(f"[INFO] Including cast name in prompt: {cid}")

            # v1.6.5: Process wardrobe per cast member
            raw_wardrobe = sh.get("wardrobe") or {}
            resolved_wardrobe = {}
            if isinstance(raw_wardrobe, dict):
                for wk, wv in raw_wardrobe.items():
                    # Resolve wardrobe key to valid cast_id
                    wk_lower = str(wk).lower().strip()
                    if wk_lower in name_to_id:
                        resolved_id = name_to_id[wk_lower]
                        resolved_wardrobe[resolved_id] = str(wv).strip()

            all_shots.append({
                "shot_id": shot_id,
                "sequence_id": seq["sequence_id"],
                "start": start,
                "end": end,
                "structure_type": normalize_structure_type(sh.get("structure_type", seq.get("structure_type","verse"))),
                "energy": float(clamp(safe_float(sh.get("energy", seq.get("energy",0.5))), 0.0, 1.0)),
                "cast": resolved_cast,
                "wardrobe": resolved_wardrobe,  # v1.6.5: Per-shot wardrobe
                "intent": (sh.get("intent") or "").strip(),
                "camera_language": (sh.get("camera_language") or "").strip(),
                "environment": (sh.get("environment") or "").strip(),
                "symbolic_elements": sh.get("symbolic_elements") if isinstance(sh.get("symbolic_elements"), list) else [],
                "prompt_base": (sh.get("prompt_base") or "").strip(),
                "render": {"status":"none","image_url":None,"model":None,"error":None},
            })

    state["storyboard"]["shots"] = all_shots
    save_project(state)
    return {"shots_count": len(all_shots), "shots": all_shots}


# ========= API: Expand selected sequence to shots =========
@app.post("/api/project/{project_id}/shots/expand_sequence")
def api_expand_sequence(project_id: str, payload: Dict[str,Any]):
    state = load_project(project_id)
    seq_id = (payload.get("sequence_id") or "").strip()
    if not seq_id:
        raise HTTPException(400, "Missing sequence_id")
    seqs = state.get("storyboard", {}).get("sequences", [])
    seq = next((s for s in seqs if s.get("sequence_id")==seq_id), None)
    if not seq:
        raise HTTPException(404, "Sequence not found")

    meta = (state.get("audio_dna") or {}).get("meta") or {}
    duration_sec = float(meta.get("duration_sec") or 180.0)
    valid_cast = {c["cast_id"] for c in state.get("cast", []) if c.get("cast_id")}
    style = state["project"]["style_preset"]

    # v1.6.5: Build name-to-id mapping for resolving LLM responses that use names instead of IDs
    name_to_id = {}
    for c in state.get("cast", []):
        if c.get("name"):
            name_to_id[c["name"].lower().strip()] = c["cast_id"]
        if c.get("cast_id"):
            name_to_id[c["cast_id"].lower()] = c["cast_id"]

    # v1.5.3: Build cast info with roles and impact
    cast_info = []
    for c in state.get("cast", []):
        role = c.get("role", "extra")
        impact = c.get("impact", 0.1 if role == "extra" else (0.5 if role == "supporting" else 0.7))
        cast_info.append({
            "cast_id": c["cast_id"],
            "name": c.get("name", ""),
            "role": role.upper(),
            "impact": f"{int(impact*100)}%",
        })

    # v1.6.5: Updated schema to include per-shot wardrobe
    schema_hint = '{ "shots": [ { "shot_id":"seq_01_sh01","start":0.0,"end":1.2,"energy":0.0,"structure_type":"verse","cast":["lead_1"],"wardrobe":{"lead_1":"specific wardrobe for this shot"},"intent":"...","camera_language":"...","environment":"...","symbolic_elements":["..."],"prompt_base":"..." } ] }'
    system = (
        "Return ONLY valid JSON. No prose. No markdown.\n"
        "Expand ONE sequence into 5 to 8 shots.\n"
        "Shots must fit within the sequence start/end. No gaps, no overlaps.\n"
        "SHOT DURATION: Each shot should be 2-5 seconds. NEVER exceed 5 seconds per shot.\n"
        "WARDROBE PER SHOT (v1.6.5):\n"
        "- Use the wardrobe object to specify costume/clothing for EACH cast member in EACH shot\n"
        "- Key is cast_id, value is the wardrobe description for that character in this specific shot\n"
        "- Wardrobe can change between shots (e.g., 'disheveled' in verse, 'formal suit' in chorus)\n"
        "- DO NOT put wardrobe in prompt_base, use the wardrobe field instead\n\n"
        f"Schema hint:\n{schema_hint}\n"
    )

    user = json.dumps({
        "sequence": seq,
        "duration_sec": duration_sec,
        "style_notes": style_script_notes(style),
        "cast": cast_info,
    }, ensure_ascii=False)

    llm = (state.get("project") or {}).get("llm","claude")
    # v1.6.1: Use fallback-enabled LLM call with automatic cost tracking
    sb = call_llm_json(system, user, preferred=llm, state=state)
    shots = sb.get("shots")
    if not isinstance(shots, list) or not shots:
        raise HTTPException(502, "LLM returned invalid shots")

    all_shots = [s for s in (state.get("storyboard", {}) or {}).get("shots", []) if s.get("sequence_id") != seq_id]
    for j, sh in enumerate(shots, start=1):
        shot_id = sh.get("shot_id") or f"{seq_id}_sh{j:02d}"
        start = safe_float(sh.get("start", seq["start"]))
        end = safe_float(sh.get("end", seq["end"]))

        # v1.5.3: Warn about long shots
        duration = end - start
        if duration > 5.0:
            print(f"[WARN] Shot {shot_id} is {duration:.1f}s (>5s recommended)")

        # v1.6.5: Resolve cast names/ids to valid cast_ids
        resolved_cast = []
        for cid in (sh.get("cast") or []):
            cid_lower = str(cid).lower().strip()
            if cid_lower in name_to_id:
                resolved_id = name_to_id[cid_lower]
                if resolved_id not in resolved_cast:
                    resolved_cast.append(resolved_id)
                    print(f"[INFO] Including cast name in prompt: {cid}")

        # v1.6.5: Process wardrobe per cast member
        raw_wardrobe = sh.get("wardrobe") or {}
        resolved_wardrobe = {}
        if isinstance(raw_wardrobe, dict):
            for wk, wv in raw_wardrobe.items():
                wk_lower = str(wk).lower().strip()
                if wk_lower in name_to_id:
                    resolved_id = name_to_id[wk_lower]
                    resolved_wardrobe[resolved_id] = str(wv).strip()

        all_shots.append({
            "shot_id": shot_id,
            "sequence_id": seq_id,
            "start": start,
            "end": end,
            "structure_type": normalize_structure_type(sh.get("structure_type", seq.get("structure_type","verse"))),
            "energy": float(clamp(safe_float(sh.get("energy", seq.get("energy",0.5))), 0.0, 1.0)),
            "cast": resolved_cast,
            "wardrobe": resolved_wardrobe,  # v1.6.5: Per-shot wardrobe
            "intent": (sh.get("intent") or "").strip(),
            "camera_language": (sh.get("camera_language") or "").strip(),
            "environment": (sh.get("environment") or "").strip(),
            "symbolic_elements": sh.get("symbolic_elements") if isinstance(sh.get("symbolic_elements"), list) else [],
            "prompt_base": (sh.get("prompt_base") or "").strip(),
            "render": {"status":"none","image_url":None,"model":None,"error":None},
        })

    state["storyboard"]["shots"] = all_shots
    save_project(state)
    return {"sequence_id": seq_id, "shots_count": len([s for s in all_shots if s.get("sequence_id")==seq_id]), "shots": [s for s in all_shots if s.get("sequence_id")==seq_id]}

# ========= API: Tighten timing =========
@app.post("/api/project/{project_id}/shots/tighten")
def api_tighten(project_id: str):
    state = load_project(project_id)
    shots = state.get("storyboard", {}).get("shots", [])
    if not shots: raise HTTPException(400, "No shots. Expand first.")

    by_seq: Dict[str, List[Dict[str,Any]]] = {}
    for sh in shots:
        by_seq.setdefault(sh["sequence_id"], []).append(sh)

    for _, arr in by_seq.items():
        arr.sort(key=lambda x: x["start"])
        for i in range(1, len(arr)):
            prev, cur = arr[i-1], arr[i]
            if cur["start"] < prev["end"]:
                cur["start"] = prev["end"]
            if cur["end"] < cur["start"]:
                cur["end"] = cur["start"] + 0.1
        for i in range(len(arr)-1):
            a, b = arr[i], arr[i+1]
            if b["start"] - a["end"] <= 0.06:
                a["end"] = b["start"]

    save_project(state)
    return {"ok": True, "shots_count": len(shots)}

# ========= API: Render shot =========
@app.post("/api/project/{project_id}/shot/{shot_id}/render")
def api_render_shot(project_id: str, shot_id: str, payload: Dict[str, Any] = None):
    """v1.4: Render shot using img2img with scene decor + cast reference images (both A and B), save locally."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)

    # v1.6.5: Get optional negative prompt override
    payload = payload or {}
    negative_prompt_override = payload.get("negative_prompt", "").strip()

    shots = state.get("storyboard", {}).get("shots", [])
    shot = next((s for s in shots if s.get("shot_id")==shot_id), None)
    if not shot:
        raise HTTPException(404, "Shot not found")

    prompt = build_prompt(state, shot)
    aspect = state["project"]["aspect"]
    print(f"[INFO] Rendering shot {shot_id}: aspect={aspect}")

    # v1.6.5: Apply negative prompt override if provided
    if negative_prompt_override:
        prompt = f"{prompt}, {negative_prompt_override}"
        print(f"[INFO] Using negative prompt override: {negative_prompt_override[:50]}...")
    
    # v1.6.5: Wardrobe per-shot and per-character (NOT scene-wide)
    # Priority: shot.wardrobe[cast_id] > cast.prompt_extra
    cast_ids = shot.get("cast") or []
    cast_list = state.get("cast", [])

    # v1.6.5: Shot-level wardrobe per character (keyed by cast_id)
    shot_wardrobes = shot.get("wardrobe") or {}  # Dict of {cast_id: "wardrobe description"}

    # Apply wardrobe per cast member
    for cast_id in cast_ids[:2]:
        cast_member = next((c for c in cast_list if c.get("cast_id") == cast_id), None)
        if not cast_member:
            continue

        # v1.6.5: Check shot-level wardrobe for this specific cast member first
        if shot_wardrobes.get(cast_id):
            wardrobe_text = shot_wardrobes[cast_id].strip()
            prompt = f"{prompt}, {cast_member.get('name', cast_id)}: {wardrobe_text}"
            print(f"[INFO] Using shot wardrobe for {cast_id}: {wardrobe_text[:40]}...")
        # Fallback to cast prompt_extra if no shot-level wardrobe
        elif cast_member.get("prompt_extra"):
            prompt = f"{prompt}, {cast_member['prompt_extra']}"
            print(f"[INFO] Using cast prompt_extra for {cast_id}")
    
    # Collect reference images (convert local paths to full URLs for fal.ai)
    ref_images = []
    
    # v1.6.1: Add style lock image for visual consistency
    style_lock_url = state["project"].get("style_lock_image")
    if style_lock_url:
        if not style_lock_url.startswith("/renders/"):
            ref_images.append(style_lock_url)
        else:
            # Upload local file to FAL
            local_file = resolve_render_path(style_lock_url)
            if local_file.exists():
                try:
                    uploaded_url = fal_client.upload_file(str(local_file))
                    ref_images.append(uploaded_url)
                    print(f"[INFO] Using style lock image for shot render")
                except Exception as e:
                    print(f"[WARN] Failed to upload style lock image: {e}")
    
    # 1. Get scene decor_refs for this shot's sequence
    seq_id = shot.get("sequence_id")
    seq_idx = None
    if seq_id:
        sequences = state.get("storyboard", {}).get("sequences", [])
        seq_idx = next((i for i, s in enumerate(sequences) if s.get("sequence_id") == seq_id), None)

    if seq_id and seq_idx is not None:
        scenes = state.get("cast_matrix", {}).get("scenes", [])
        if seq_idx < len(scenes):
            scene = scenes[seq_idx]
            decor_refs = scene.get("decor_refs") or []
            for dref in decor_refs[:1]:  # Use first scene render
                if dref and not dref.startswith("/renders/"):
                    ref_images.append(dref)
                elif dref and dref.startswith("/renders/"):
                    local_file = resolve_render_path(dref)
                    if local_file.exists():
                        try:
                            uploaded_url = fal_client.upload_file(str(local_file))
                            ref_images.append(uploaded_url)
                        except:
                            pass
    
    # 2. v1.6.1: Get BOTH cast member reference images (ref_a and ref_b) - use resolve_render_path
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    for cast_id in cast_ids[:2]:
        refs = char_refs.get(cast_id, {})
        # Add ref_a
        if refs.get("ref_a"):
            ref_url = refs["ref_a"]
            if ref_url and not ref_url.startswith("/renders/"):
                ref_images.append(ref_url)
            elif ref_url and ref_url.startswith("/renders/"):
                local_file = resolve_render_path(ref_url)
                if local_file.exists():
                    try:
                        uploaded_url = fal_client.upload_file(str(local_file))
                        ref_images.append(uploaded_url)
                        print(f"[INFO] Uploaded cast ref_a for {cast_id}")
                    except Exception as e:
                        print(f"[WARN] Failed to upload cast ref_a: {e}")
        # Add ref_b
        if refs.get("ref_b"):
            ref_url = refs["ref_b"]
            if ref_url and not ref_url.startswith("/renders/"):
                ref_images.append(ref_url)
            elif ref_url and ref_url.startswith("/renders/"):
                local_file = resolve_render_path(ref_url)
                if local_file.exists():
                    try:
                        uploaded_url = fal_client.upload_file(str(local_file))
                        ref_images.append(uploaded_url)
                        print(f"[INFO] Uploaded cast ref_b for {cast_id}")
                    except Exception as e:
                        print(f"[WARN] Failed to upload cast ref_b: {e}")
    
    img_url = None
    model_name = "unknown"
    
    # If we have reference images, use img2img; otherwise fallback to t2i
    if ref_images:
        editor = locked_editor_key(state)
        try:
            img_url = call_img2img_editor(editor, prompt, ref_images, aspect)
            model_name = editor
            track_cost(f"fal-ai/{editor}", 1, state=state)  # v1.4.9: Track cost to state
        except Exception as e:
            print(f"[WARN] img2img failed, falling back to t2i: {e}")
            ref_images = []  # Clear to trigger t2i fallback
    
    if not img_url:
        # Fallback to t2i
        image_size = "landscape_16_9" if aspect=="horizontal" else ("portrait_16_9" if aspect=="vertical" else "square_hd")
        endpoint, payload, model_name = t2i_endpoint_and_payload(state, prompt, image_size)
        
        r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        track_cost(f"fal-ai/{model_name}", 1, state=state)  # v1.4.9: Track cost to state
        
        if r.status_code >= 300:
            shot["render"] = {"status":"error","image_url":None,"model":model_name,"error":r.text}
            save_project(state)
            return {"error":"fal t2i failed","status":r.status_code,"body":r.text}
        
        out = r.json()
        if isinstance(out.get("images"), list) and out["images"]:
            img_url = out["images"][0].get("url")

    # v1.5.9.1: Save image locally with friendly name
    if img_url:
        # Parse shot_id (format: seq_01_sh01) to Sce01_Sho01
        parts = shot_id.split("_")
        if len(parts) >= 4:
            friendly_name = f"Sce{parts[1]}_Sho{parts[3]}"
        else:
            friendly_name = shot_id
        img_url = download_image_locally(img_url, project_id, shot_id, state=state, friendly_name=friendly_name)

    render_result = {
        "status":"done" if img_url else "error",
        "image_url": img_url,
        "model": model_name,
        "ref_images_used": len(ref_images),
        "error": None if img_url else "No image url found"
    }

    # v1.6.5: Thread-safe save - reload state, update shot, save atomically
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_shots = fresh_state.get("storyboard", {}).get("shots", [])
        fresh_shot = next((s for s in fresh_shots if s.get("shot_id") == shot_id), None)
        if fresh_shot:
            fresh_shot["render"] = render_result
            save_project(fresh_state)

    return {"shot_id": shot_id, "prompt": prompt, "image_url": img_url, "ref_images_used": len(ref_images), "result": render_result}


# v1.5.3: Edit a rendered shot with custom prompt and extra cast refs
@app.post("/api/project/{project_id}/shot/{shot_id}/edit")
def api_edit_shot(project_id: str, shot_id: str, payload: Dict[str, Any]):
    """Edit a rendered shot using img2img with custom prompt and extra cast references."""
    state = load_project(project_id)
    require_key("FAL_KEY", FAL_KEY)
    
    shots = state.get("storyboard", {}).get("shots", [])
    shot = next((s for s in shots if s.get("shot_id") == shot_id), None)
    if not shot:
        raise HTTPException(404, "Shot not found")
    
    if not shot.get("render", {}).get("image_url"):
        raise HTTPException(400, "Shot has no render to edit. Render first.")
    
    edit_prompt = payload.get("edit_prompt", "").strip()
    extra_cast = payload.get("extra_cast", [])  # List of cast_ids to add refs from
    ref_image = payload.get("ref_image")  # v1.5.4: Optional reference image URL from another shot
    
    # Get the current rendered image
    current_render_url = shot["render"]["image_url"]
    aspect = state["project"]["aspect"]
    
    # Build reference images list
    ref_images = []
    
    # 1. Upload current render as primary reference
    if current_render_url.startswith("/renders/"):
        local_file = RENDERS_DIR / current_render_url.replace("/renders/", "")
        if local_file.exists():
            try:
                uploaded_url = fal_client.upload_file(str(local_file))
                ref_images.append(uploaded_url)
                print(f"[INFO] Uploaded current render for editing")
            except Exception as e:
                print(f"[WARN] Failed to upload current render: {e}")
    else:
        ref_images.append(current_render_url)
    
    # v1.5.4: Add reference image from another shot if provided
    if ref_image:
        if ref_image.startswith("/renders/"):
            local_file = RENDERS_DIR / ref_image.replace("/renders/", "")
            if local_file.exists():
                try:
                    uploaded_url = fal_client.upload_file(str(local_file))
                    ref_images.append(uploaded_url)
                    print(f"[INFO] Uploaded reference image for editing")
                except Exception as e:
                    print(f"[WARN] Failed to upload reference image: {e}")
        else:
            ref_images.append(ref_image)
    
    # 2. Add extra cast refs (both A and B for each)
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    for cast_id in extra_cast:
        refs = char_refs.get(cast_id, {})
        for ref_type in ["ref_a", "ref_b"]:
            ref_url = refs.get(ref_type)
            if ref_url:
                if ref_url.startswith("/renders/"):
                    local_file = RENDERS_DIR / ref_url.replace("/renders/", "")
                    if local_file.exists():
                        try:
                            uploaded_url = fal_client.upload_file(str(local_file))
                            ref_images.append(uploaded_url)
                            print(f"[INFO] Uploaded {cast_id} {ref_type} for editing")
                        except:
                            pass
                else:
                    ref_images.append(ref_url)
    
    # Build the edit prompt
    # Combine original shot context with edit instruction
    base_prompt = build_prompt(state, shot)
    if edit_prompt:
        full_prompt = f"{base_prompt}, {edit_prompt}"
    else:
        full_prompt = base_prompt
    
    # Add cast names from extra_cast to prompt
    cast_list = state.get("cast", [])
    for cast_id in extra_cast:
        cast_member = next((c for c in cast_list if c.get("cast_id") == cast_id), None)
        if cast_member:
            name = cast_member.get("name", "")
            if name:
                full_prompt = f"{full_prompt}, {name} visible in scene"
            if cast_member.get("prompt_extra"):
                full_prompt = f"{full_prompt}, {cast_member['prompt_extra']}"
    
    # Call img2img
    editor = locked_editor_key(state)
    try:
        img_url = call_img2img_editor(editor, full_prompt, ref_images, aspect)
        track_cost(f"fal-ai/{editor}", 1, state=state)
    except Exception as e:
        raise HTTPException(502, f"Edit failed: {str(e)}")
    
    # v1.5.9.1: Save locally with friendly name
    if img_url:
        parts = shot_id.split("_")
        if len(parts) >= 4:
            friendly_name = f"Sce{parts[1]}_Sho{parts[3]}_Edit"
        else:
            friendly_name = f"{shot_id}_edit"
        img_url = download_image_locally(img_url, project_id, f"{shot_id}_edit", state=state, friendly_name=friendly_name)
    
    # v1.6.5: Thread-safe save - reload state, update shot, save atomically
    render_result = {
        "status": "done" if img_url else "error",
        "image_url": img_url,
        "model": editor,
        "ref_images_used": len(ref_images),
        "edit_prompt": edit_prompt,
        "extra_cast": extra_cast,
        "error": None if img_url else "Edit failed"
    }

    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        fresh_shots = fresh_state.get("storyboard", {}).get("shots", [])
        fresh_shot = next((s for s in fresh_shots if s.get("shot_id") == shot_id), None)
        if fresh_shot:
            fresh_shot["render"] = render_result
            save_project(fresh_state)

    return {
        "shot_id": shot_id,
        "prompt": full_prompt,
        "image_url": img_url,
        "ref_images_used": len(ref_images),
        "edit_prompt": edit_prompt,
        "extra_cast": extra_cast
    }


# ========= API: Video Export =========
def update_export_status(project_id: str, status: str, current: int = 0, total: int = 0, message: str = ""):
    """v1.5.9.1: Update export status for polling."""
    EXPORT_STATUS[project_id] = {
        "status": status,  # "idle", "processing", "done", "error"
        "current": current,
        "total": total,
        "message": message,
        "updated_at": time.time()
    }

@app.get("/api/project/{project_id}/export/status")
def api_export_status(project_id: str):
    """v1.5.9.1: Get export status for polling."""
    status = EXPORT_STATUS.get(project_id, {"status": "idle", "current": 0, "total": 0, "message": ""})
    return status

@app.post("/api/project/{project_id}/video/export")
def api_export_video(project_id: str, payload: Dict[str, Any] = {}):
    """v1.5.3: Export storyboard as video with FFmpeg xfade at scene transitions."""
    import subprocess
    import shutil
    
    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "FFmpeg not found. Install FFmpeg and add to PATH.")
    
    state = load_project(project_id)
    shots = state.get("storyboard", {}).get("shots", [])
    sequences = state.get("storyboard", {}).get("sequences", [])
    
    if not shots:
        raise HTTPException(400, "No shots to export")
    
    # Get rendered shots only
    rendered_shots = [s for s in shots if s.get("render", {}).get("image_url")]
    if not rendered_shots:
        raise HTTPException(400, "No rendered shots. Render shots first.")
    
    # Sort by start time
    rendered_shots.sort(key=lambda s: float(s.get("start", 0)))
    
    # Get audio file
    audio_path = state.get("audio_file_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(400, "Audio file not found")
    
    # Settings
    fade_duration = float(payload.get("fade_duration", 0.5))
    fps = int(payload.get("fps", 30))
    resolution = payload.get("resolution", "1920x1080")
    
    # Build sequence lookup
    seq_ids = [seq.get("sequence_id") for seq in sequences]
    
    # v1.5.9.1: Use project folder for temp and output
    video_dir = get_project_video_dir(state)
    temp_dir = video_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Output path in project video folder
    project_title = sanitize_filename(state.get("project", {}).get("title", "video"), 30)
    output_path = video_dir / f"{project_title}_export.mp4"
    
    try:
        # Step 1: Create video clip for each shot
        clip_paths = []
        skipped = []
        total_shots = len(rendered_shots)
        print(f"[INFO] Processing {total_shots} rendered shots...")
        update_export_status(project_id, "processing", 0, total_shots, f"Starting export of {total_shots} shots...")
        
        for i, shot in enumerate(rendered_shots):
            img_url = shot["render"]["image_url"]
            # v1.5.9.1: Handle both legacy and new folder structures
            if img_url.startswith("/renders/"):
                rel_path = img_url[9:]  # Strip /renders/
                if rel_path.startswith("projects/"):
                    img_path = DATA / rel_path
                else:
                    img_path = RENDERS_DIR / rel_path
            else:
                img_path = Path(img_url)
            
            if not img_path.exists():
                print(f"[WARN] Shot {shot.get('shot_id')} image not found: {img_path}")
                skipped.append(shot.get('shot_id', f'idx_{i}'))
                continue
            
            duration = float(shot.get("end", 0)) - float(shot.get("start", 0))
            if duration <= 0:
                print(f"[WARN] Shot {shot.get('shot_id')} has invalid duration: {duration}")
                skipped.append(shot.get('shot_id', f'idx_{i}'))
                continue
            
            clip_path = temp_dir / f"clip_{i:03d}.mp4"
            
            # Parse resolution (e.g., "1920x1080" -> width=1920, height=1080)
            res_parts = resolution.split("x")
            width = res_parts[0]
            height = res_parts[1] if len(res_parts) > 1 else res_parts[0]
            
            # Create video from image with duration
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(img_path),
                "-t", str(duration),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                str(clip_path)
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                clip_paths.append({
                    "path": clip_path,
                    "shot": shot,
                    "duration": duration,
                    "seq_id": shot.get("sequence_id", "")
                })
                print(f"[INFO] Created clip {i+1}/{total_shots}: {shot.get('shot_id')} ({duration:.1f}s)")
                update_export_status(project_id, "processing", i+1, total_shots, f"Created clip {i+1}/{total_shots}: {shot.get('shot_id')}")
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed to create clip for {shot.get('shot_id')}: {e.stderr[:200] if e.stderr else str(e)}")
                skipped.append(shot.get('shot_id', f'idx_{i}'))
        
        print(f"[INFO] Created {len(clip_paths)} clips, skipped {len(skipped)}: {skipped[:5]}{'...' if len(skipped) > 5 else ''}")
        
        if not clip_paths:
            update_export_status(project_id, "error", 0, 0, "No clips created")
            raise HTTPException(500, "No clips created")
        
        # Calculate expected total duration
        expected_duration = sum(c["duration"] for c in clip_paths)
        print(f"[INFO] Expected video duration: {expected_duration:.1f}s from {len(clip_paths)} clips")
        update_export_status(project_id, "processing", total_shots, total_shots, f"Concatenating {len(clip_paths)} clips...")
        
        # Step 2: Use concat demuxer (simpler and more reliable)
        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for clip in clip_paths:
                # FFmpeg concat format requires forward slashes
                clip_path_str = str(clip["path"]).replace("\\", "/")
                f.write(f"file '{clip_path_str}'\n")
        
        print(f"[INFO] Concat file created with {len(clip_paths)} entries")
        
        # Step 3: Concat all clips and add audio
        final_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            str(output_path)
        ]
        
        print(f"[INFO] Running final export...")
        result = subprocess.run(final_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[ERROR] FFmpeg failed: {result.stderr}")
            raise HTTPException(500, f"FFmpeg export failed: {result.stderr[:500]}")
        
        # Calculate scene transitions for info
        scene_transitions = sum(1 for i in range(1, len(clip_paths)) if clip_paths[i-1]["seq_id"] != clip_paths[i]["seq_id"])
        
        # Calculate total duration
        total_duration = sum(c["duration"] for c in clip_paths)
        
        # Cleanup temp files
        for clip in clip_paths:
            try:
                clip["path"].unlink()
            except:
                pass
        try:
            concat_file.unlink()
        except:
            pass
        try:
            temp_dir.rmdir()
        except:
            pass
        
        # Return video URL
        # v1.5.9.1: Return path relative to DATA for serve_render
        rel_path = output_path.relative_to(DATA)
        video_url = f"/renders/{rel_path.as_posix()}"
        
        update_export_status(project_id, "done", total_shots, total_shots, f"Export complete: {len(clip_paths)} clips, {total_duration:.1f}s")
        
        return {
            "video_url": video_url,
            "shots_exported": len(clip_paths),
            "duration_sec": total_duration,
            "scene_transitions": scene_transitions
        }
        
    except subprocess.CalledProcessError as e:
        update_export_status(project_id, "error", 0, 0, f"FFmpeg error: {str(e)[:100]}")
        raise HTTPException(500, f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
    except Exception as e:
        update_export_status(project_id, "error", 0, 0, f"Export failed: {str(e)[:100]}")
        raise HTTPException(500, f"Export failed: {str(e)}")