"""
Fré Pathé v1.7 - Project Service
Handles project CRUD, folder structure, and schema validation.
"""
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import HTTPException
from jsonschema import validate, ValidationError
from PIL import Image

from .config import (
    VERSION,
    PATH_MANAGER,
    BASE,
    DATA,
    now_iso,
    locked_render_models
)


# ========= Thumbnail Generation =========

def create_thumbnail(image_path: Path, size=(400, 400)):
    """Maakt een geoptimaliseerde WebP thumbnail voor de UI."""
    try:
        thumb_path = image_path.with_name(image_path.stem + "_thumb.webp")
        if not thumb_path.exists():
            with Image.open(image_path) as img:
                # Behoud aspect ratio, maar max 400px
                img.thumbnail(size, Image.Resampling.LANCZOS)
                # Sla op als WebP (veel kleiner dan PNG)
                img.save(thumb_path, "WEBP", quality=80)
            return thumb_path
    except Exception as e:
        print(f"[WARN] Thumbnail generatie mislukt voor {image_path.name}: {e}")
    return None


# ========= Filename Sanitization =========

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


# ========= Project Folder System =========

def get_project_folder(state: Dict[str, Any]) -> Path:
    """
    v1.8.0: Wrapper around PATH_MANAGER.get_project_folder()
    Kept for backwards compatibility.
    """
    return PATH_MANAGER.get_project_folder(state)


def get_project_renders_dir(state: Dict[str, Any]) -> Path:
    """v1.8.0: Wrapper around PATH_MANAGER.get_project_renders_dir()"""
    return PATH_MANAGER.get_project_renders_dir(state)


def get_project_audio_dir(state: Dict[str, Any]) -> Path:
    """v1.8.0: Wrapper around PATH_MANAGER.get_project_audio_dir()"""
    return PATH_MANAGER.get_project_audio_dir(state)


def get_project_video_dir(state: Dict[str, Any]) -> Path:
    """v1.8.0: Wrapper around PATH_MANAGER.get_project_video_dir()"""
    return PATH_MANAGER.get_project_video_dir(state)


def get_project_llm_dir(state: Dict[str, Any]) -> Path:
    """v1.8.0: Wrapper around PATH_MANAGER.get_project_llm_dir()"""
    return PATH_MANAGER.get_project_llm_dir(state)


def get_project_director_dir(state: Dict[str, Any]) -> Path:
    """v1.8.0: Wrapper around PATH_MANAGER.get_project_director_dir()"""
    return PATH_MANAGER.get_project_director_dir(state)


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


def save_director_log(state: Dict[str, Any], operation: str, system_prompt: str, user_prompt: str, response: Any) -> Path:
    """Save complete LLM conversation to Director folder for fine-tuning.
    
    Args:
        state: Project state
        operation: Name of operation (e.g., 'generate_storyboard', 'insert_scenes')
        system_prompt: Full system prompt sent to LLM
        user_prompt: Full user prompt/context sent to LLM
        response: Complete LLM response
    """
    director_dir = get_project_director_dir(state)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{operation}_{timestamp}.json"
    filepath = director_dir / filename
    
    log_data = {
        "operation": operation,
        "timestamp": timestamp,
        "project_id": state.get("project_id"),
        "project_title": state.get("project", {}).get("title"),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response": response,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    
    print(f"[DIRECTOR] Saved conversation log: {filepath}")
    return filepath


def download_image_locally(
    url: str, 
    project_id: str, 
    prefix: str, 
    state: Dict[str, Any] = None, 
    friendly_name: str = None
) -> str:
    """
    Download image to project folder with friendly naming.
    If state provided: saves to project folder with friendly name.
    If no state: legacy behavior (saves to global renders folder).
    """
    if not url or url.startswith("/files/") or url.startswith("/renders/"):
        return url
    try:
        ext = ".png"
        if ".jpg" in url or ".jpeg" in url:
            ext = ".jpg"
        elif ".webp" in url:
            ext = ".webp"
        
        # Use project folder if state provided
        if state:
            renders_dir = get_project_renders_dir(state)
            if friendly_name:
                local_filename = f"{friendly_name}{ext}"
            else:
                local_filename = f"{prefix}{ext}"
            local_path = renders_dir / local_filename
            
            # Download
            try:
                r = requests.get(url, timeout=60)
            except requests.exceptions.RequestException as e:
                print(f"[WARN] Download failed (network error): {type(e).__name__}: {e}")
                return url  # Return original URL on network failure
            
            if r.status_code == 200:
                local_path.write_bytes(r.content)
                # Generate thumbnail for faster UI loading
                create_thumbnail(local_path)
            
            # Use PathManager for consistent URL generation
            return PATH_MANAGER.to_url(local_path)
        else:
            # Legacy behavior - save to temp dir
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            local_filename = f"{project_id}_{prefix}_{url_hash}{ext}"
            local_path = PATH_MANAGER.temp_dir / local_filename
            
            if not local_path.exists():
                try:
                    r = requests.get(url, timeout=60)
                except requests.exceptions.RequestException as e:
                    print(f"[WARN] Download failed (network error): {type(e).__name__}: {e}")
                    return url  # Return original URL on network failure
                
                if r.status_code == 200:
                    local_path.write_bytes(r.content)
                    # Generate thumbnail for faster UI loading
                    create_thumbnail(local_path)
            
            return PATH_MANAGER.to_url(local_path)
    except Exception as e:
        print(f"[WARN] Failed to download image locally: {e}")
        return url


# ========= Schema Validation =========

CONTRACTS_DIR = BASE / "Contracts"
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


def validate_against_schema(
    data: Dict[str, Any], 
    schema_name: str, 
    raise_on_error: bool = False
) -> Tuple[bool, Optional[str]]:
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


# ========= Project Persistence =========

def project_path(pid: str) -> Path:
    """
    v1.8.0: Get path to project JSON file in workspace/projects/.
    This is the fallback storage for projects without a custom project_location.
    """
    return PATH_MANAGER.workspace_root / "projects" / f"{pid}.json"


def load_project(pid: str) -> Dict[str, Any]:
    """Load project from disk."""
    p = project_path(pid)
    if not p.exists():
        raise HTTPException(404, "Project not found")
    state = json.loads(p.read_text(encoding="utf-8"))
    
    # Validate on load (non-strict, just warn)
    is_valid, errors = validate_project_state(state, strict=False)
    if not is_valid:
        print(f"[WARN] Project {pid} has validation errors: {errors}")
    
    # Recover orphaned render files
    state = recover_orphaned_renders(state, pid)
    
    # Migrate FAL links to local storage
    state = migrate_fal_to_local(state)
    
    return state


def recover_orphaned_renders(state: Dict[str, Any], pid: str) -> Dict[str, Any]:
    """Find render files on disk that aren't in the JSON and recover them."""
    recovered = 0
    shots = state.get("storyboard", {}).get("shots", [])
    
    for shot in shots:
        shot_id = shot.get("shot_id")
        render = shot.get("render", {})
        
        # Skip if already has a valid render
        if render.get("image_url") and render.get("status") == "done":
            continue
        
        # Look for matching files in project renders directory
        renders_dir = get_project_renders_dir(state)
        
        # v1.8: Parse shot_id (seq_01_sh01) to friendly name (Sce01_Sho01)
        parts = shot_id.split("_")
        friendly_name = None
        if len(parts) >= 4:
            friendly_name = f"Sce{parts[1]}_Sho{parts[3]}"
        
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            # Try 1: Direct shot_id match (seq_07_sh01.png)
            for f in renders_dir.glob(f"{shot_id}*{ext}"):
                if f.exists() and "_thumb" not in f.name:  # Skip thumbnails
                    local_url = PATH_MANAGER.to_url(f)
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
            
            # Try 2: Friendly name (Sce01_Sho01.png)
            if not shot.get("render", {}).get("status") == "done" and friendly_name:
                for f in renders_dir.glob(f"{friendly_name}*{ext}"):
                    if f.exists() and "_thumb" not in f.name:  # Skip thumbnails
                        local_url = PATH_MANAGER.to_url(f)
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
            
            # Try 3: Old format with project prefix (WWT_v1.8.0_seq_01_sh01.png)
            if not shot.get("render", {}).get("status") == "done":
                for f in renders_dir.glob(f"{pid}_{shot_id}*{ext}"):
                    if f.exists() and "_thumb" not in f.name:  # Skip thumbnails
                        local_url = PATH_MANAGER.to_url(f)
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
        renders_dir = get_project_renders_dir(state)
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            for f in renders_dir.glob(f"{pid}_{scene_id}_decor*{ext}"):
                if f.exists():
                    local_url = PATH_MANAGER.to_url(f)
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


def migrate_fal_to_local(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scant de state op FAL links en probeert ze lokaal te trekken."""
    project_id = state["project"]["id"]
    modified = False

    # 1. Check cast refs
    for cast_id, refs in state.get("cast_matrix", {}).get("character_refs", {}).items():
        for key in ["ref_a", "ref_b"]:
            if refs.get(key) and "fal.media" in refs[key]:
                refs[key] = download_image_locally(refs[key], project_id, f"cast_{cast_id}_{key}", state)
                modified = True

    # 3. Check shots
    for shot in state.get("storyboard", {}).get("shots", []):
        img_url = shot.get("render", {}).get("image_url")
        if img_url and "fal.media" in img_url:
            shot["render"]["image_url"] = download_image_locally(img_url, project_id, shot["shot_id"], state)
            modified = True

    if modified:
        print(f"[INFO] Migration completed for {project_id}. Saving local paths.")
        save_project(state, force=True)  # Forceer de save nu de links lokaal zijn
    
    return state


def save_project(state: Dict[str, Any], validate: bool = True, force: bool = False) -> None:
    """
    Save project state.
    Auto-migrates version if mismatch detected.
    """
    pid = state["project"]["id"]
    
    # Version migration - auto-update to current version
    current_project_version = state["project"].get("created_version")
    if current_project_version and current_project_version != VERSION:
        print(f"[MIGRATION] Updating project {pid} from {current_project_version} to {VERSION}")
        state["project"]["created_version"] = VERSION
    
    state["project"]["updated_at"] = now_iso()
    
    # Validate before save
    if validate:
        is_valid, errors = validate_project_state(state, strict=False)
        if not is_valid:
            print(f"[WARN] Saving project {pid} with validation errors: {errors}")
    
    project_path(pid).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), 
        encoding="utf-8"
    )
    
    # Also save to project folder
    try:
        project_folder = get_project_folder(state)
        project_json_path = project_folder / "project.json"
        project_json_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), 
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[WARN] Failed to save to project folder: {e}")


def new_project(
    title: str, 
    style_preset: str, 
    aspect: str, 
    llm: str = "claude", 
    image_model_choice: str = "nanobanana", 
    video_model: str = "none", 
    use_whisper: bool = False
) -> Dict[str, Any]:
    """Create a new project with default structure."""
    pid = str(uuid.uuid4())
    
    state = {
        "project": {
            "id": pid,
            "title": title,
            "style_preset": style_preset,
            "aspect": aspect,
            "llm": (llm or "claude"),
            "image_model_choice": image_model_choice,
            "video_model": video_model,
            "use_whisper": use_whisper,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "created_version": VERSION,
            "render_models": locked_render_models(image_model_choice),
        },
        "audio_dna": None,
        "cast": [],  # v1.8.3: Empty cast array - user uploads create entries
        "storyboard": {"sequences": [], "shots": []},
        "cast_matrix": {
            "character_refs": {},
            "scenes": []
        },
        "cost_tracking": {
            "total_cost_usd": 0.0,
            "calls": []
        }
    }
    
    save_project(state)
    return state


def list_projects() -> List[Dict[str, Any]]:
    """
    v1.8.0: List all projects with metadata.
    Scans workspace/projects/ for JSON files.
    """
    projects = []
    projects_dir = PATH_MANAGER.workspace_root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    for p in projects_dir.glob("*.json"):
        if p.name.startswith("."):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            proj = data.get("project", {})
            projects.append({
                "id": proj.get("id"),
                "title": proj.get("title", "Untitled"),
                "style_preset": proj.get("style_preset"),
                "created_at": proj.get("created_at"),
                "updated_at": proj.get("updated_at"),
                "created_version": proj.get("created_version"),
            })
        except Exception as e:
            print(f"[WARN] Failed to read project {p.name}: {e}")
    
    # Sort by updated_at descending
    projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return projects


def delete_project(pid: str) -> bool:
    """Delete a project and its folder."""
    p = project_path(pid)
    if not p.exists():
        return False
    
    try:
        # Load to get folder path
        state = json.loads(p.read_text(encoding="utf-8"))
        folder = get_project_folder(state)
        
        # Delete JSON file
        p.unlink()
        
        # Delete folder if exists
        if folder.exists():
            import shutil
            shutil.rmtree(folder, ignore_errors=True)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to delete project {pid}: {e}")
        return False


# ========= Utility Functions =========

def safe_float(x, default=0.0) -> float:
    """Safely convert to float."""
    try:
        return float(x)
    except Exception:
        return float(default)


def normalize_structure_type(s: str) -> str:
    """Normalize structure type to standard values."""
    if not s:
        return "verse"
    t = s.strip().lower()
    for k in ["intro", "verse", "prechorus", "chorus", "bridge", "breakdown", "outro", "instrumental"]:
        if t.startswith(k):
            return k
    if t.startswith("pre-chorus") or t.startswith("pre chorus"):
        return "prechorus"
    return "verse"
