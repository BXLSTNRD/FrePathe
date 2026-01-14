import os, json, time, uuid, asyncio, threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

import requests
import fal_client
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jsonschema import validate, ValidationError, Draft202012Validator

# ========= v1.6.9: Import Services =========
from services.config import (
    VERSION,
    PROJECT_LOCKS, PROJECT_LOCKS_LOCK, get_project_lock,
    BASE, DATA, PROJECTS_DIR, UPLOADS_DIR, RENDERS_DIR, DEBUG_DIR,
    FAL_KEY, OPENAI_KEY, CLAUDE_KEY,
    FAL_AUDIO, FAL_WHISPER,
    FAL_NANOBANANA, FAL_NANOBANANA_EDIT,
    FAL_SEEDREAM45, FAL_SEEDREAM45_EDIT,
    FAL_FLUX2, FAL_FLUX2_EDIT,
    API_COSTS, MODEL_TO_ENDPOINT, SESSION_COST, PRICING_LOADED,
    RENDER_SEMAPHORE, EXPORT_STATUS,
    require_key, fal_headers, now_iso, clamp, safe_float,
    retry_on_502, track_cost, fetch_live_pricing, log_llm_call,
    locked_render_models, locked_editor_key, locked_model_key,
)
from services.project_service import (
    sanitize_filename,
    get_project_folder, get_project_renders_dir, get_project_audio_dir,
    get_project_video_dir, get_project_llm_dir, save_llm_response,
    download_image_locally,
    validate_against_schema, validate_shot, validate_sequence, validate_project_state,
    project_path, load_project, recover_orphaned_renders, save_project, new_project,
    list_projects, delete_project,
    normalize_structure_type,
)
from services.audio_service import (
    get_audio_duration_librosa, get_audio_duration_mutagen, get_audio_duration,
    get_audio_bpm_librosa, build_beat_grid, snap_to_grid,
    normalize_audio_understanding,
)
from services.cast_service import (
    find_cast, cast_ref_urls, get_cast_refs_for_shot, get_lead_cast_ref,
    create_cast_visual_dna, update_cast_properties, update_cast_lora,
    delete_cast_from_state, set_character_refs, get_character_refs,
    check_style_lock, get_style_lock_image, set_style_lock, clear_style_lock,
    get_scene_by_id, get_scene_for_shot, get_scene_decor_refs, get_scene_wardrobe,
    get_identity_url,
)
from services.render_service import (
    model_to_endpoint, call_txt2img, call_img2img_editor,
    resolve_render_path, build_shot_prompt, get_shot_ref_images,
    update_shot_render, get_pending_shots, get_render_stats,
    t2i_endpoint_and_payload, call_t2i_with_retry, energy_tokens, build_prompt,
    save_fal_debug,
)
from services.storyboard_service import (
    target_sequences_and_shots,
    create_sequence, find_sequence, update_sequence,
    create_shot, find_shot, update_shot, delete_shot, get_shots_for_sequence,
    repair_timeline, validate_shots_coverage, get_cast_coverage,
)
from services.export_service import (
    update_export_status, get_export_status,
    check_ffmpeg, export_video,
)
from services.llm_service import (
    extract_json_object, call_openai_json, call_claude_json,
    CLAUDE_MODEL_CASCADE, call_llm_json,
    load_prompt, save_llm_debug,
)
from services.styles import (
    STYLE_PRESETS, style_tokens, style_script_notes,
    get_style_label, list_styles, get_style_options_html,
)
from services.ui_service import (
    TEMPLATES_DIR, STATIC_DIR, INDEX_HTML_PATH, STYLE_CSS_PATH, APP_JS_PATH, LOGO_PATH,
    DEFAULT_AUDIO_PROMPT, build_index_html, get_app_js_content, get_media_type,
)

# v1.7.0: All config, audio functions, and utilities now imported from services.
# Project folder system: sanitize_filename, get_project_folder, get_project_renders_dir,
#   get_project_audio_dir, get_project_video_dir, get_project_llm_dir, save_llm_response,
#   download_image_locally from services.project_service
# Schema validation: validate_against_schema, validate_shot, validate_sequence,
#   validate_project_state from services.project_service
# Audio: build_beat_grid, snap_to_grid, get_audio_duration, get_audio_bpm_librosa
#   from services.audio_service
# Storyboard: target_sequences_and_shots from services.storyboard_service
# Config: FAL_KEY, OPENAI_KEY, CLAUDE_KEY, FAL_AUDIO, FAL_WHISPER, FAL_* endpoints,
#   clamp, require_key, fal_headers, now_iso, log_llm_call, track_cost from services.config
# v1.7.0: UI helpers imported from services.ui_service (DEFAULT_AUDIO_PROMPT, build_index_html, etc.)

# v1.6.9: build_beat_grid imported from services.audio_service
# v1.6.9: STYLE_PRESETS, style_tokens, style_script_notes imported from services.styles

# ========= App =========
app = FastAPI()

# v1.4.2: Fetch live pricing on startup
@app.on_event("startup")
async def startup_event():
    fetch_live_pricing()

# v1.6.9: now_iso, require_key, fal_headers imported from services.config
# v1.6.9: call_img2img_editor imported from services.render_service

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
    
    result_url = call_img2img_editor(editor, prompt, [ref_url], aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note="wardrobe")
    
    # Store as wardrobe_ref
    scene_title = sanitize_filename(scene.get("title", scene_id), 20)
    local_path = download_image_locally(result_url, project_id, f"scene_{scene_id}_wardrobe", state=state, friendly_name=f"Sce{scene_num}_{scene_title}_Wardrobe")
    
    return local_path

# v1.6.9: safe_float imported from services.config
# v1.6.9: normalize_structure_type imported from services.project_service

# ========= Persistence (v1.6.9: now imported from services.project_service) =========
# project_path, load_project, recover_orphaned_renders, save_project, new_project
# are all imported from services.project_service
# locked_render_models, locked_editor_key, locked_model_key imported from services.config

# v1.6.9: t2i_endpoint_and_payload, call_t2i_with_retry imported from services.render_service
# v1.6.9: normalize_audio_understanding imported from services.audio_service
# v1.6.9: LLM functions imported from services.llm_service
#   extract_json_object, call_openai_json, call_claude_json,
#   CLAUDE_MODEL_CASCADE, call_llm_json

# v1.6.9: Cast helpers imported from services.cast_service
# v1.6.9: get_identity_url imported from services.cast_service
# v1.6.9: energy_tokens, build_prompt imported from services.render_service
# v1.7.0: UI helpers imported from services.ui_service

@app.get("/static/style.css")
def static_css():
    from fastapi.responses import FileResponse
    return FileResponse(str(STYLE_CSS_PATH), media_type="text/css")

@app.get("/static/app.js")
def static_js():
    from fastapi.responses import Response
    return Response(content=get_app_js_content(), media_type="application/javascript")

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
    
    return FileResponse(str(file_path), media_type=get_media_type(filepath))

# v1.6.9: resolve_render_path imported from services.render_service

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
            whisper_payload = {
                "audio_url": audio_url,
                "task": "transcribe",
                "language": "en",  # Auto-detect if empty
                "chunk_level": "segment",
                "version": "3"
            }
            whisper_r = requests.post(FAL_WHISPER, headers=fal_headers(), json=whisper_payload, timeout=300)
            
            if whisper_r.status_code < 300:
                whisper_data = whisper_r.json()
                whisper_transcript = whisper_data.get("text", "")
                # Log Whisper call
                save_fal_debug("whisper", FAL_WHISPER, whisper_payload, whisper_data, project_id)
                # Track Whisper cost
                duration_for_cost = local_duration or 180
                track_cost("fal-ai/whisper", int(duration_for_cost), state=state)
                print(f"[INFO] Whisper transcription complete: {len(whisper_transcript)} chars")
            else:
                print(f"[WARN] Whisper failed: {whisper_r.status_code}")
        except Exception as e:
            print(f"[WARN] Whisper error: {e}")

    audio_payload = {"audio_url":audio_url, "prompt":prompt}
    r = requests.post(FAL_AUDIO, headers=fal_headers(), json=audio_payload, timeout=300)
    # v1.5.1: Track cost based on duration ($0.01 per 5 seconds)
    duration_for_cost = local_duration or 180  # Fallback to 3 min estimate
    audio_cost_units = max(1, int(duration_for_cost / 5))  # 5-second units
    track_cost("fal-ai/audio-understanding", audio_cost_units, state=state)
    
    if r.status_code >= 300:
        return JSONResponse({"error":"fal audio-understanding failed","status":r.status_code,"body":r.text}, status_code=502)

    raw = r.json()
    # Log audio understanding call
    save_fal_debug("audio_understanding", FAL_AUDIO, audio_payload, raw, project_id)
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

# v1.7.0: Manually update lyrics (for hallucinated transcriptions)
@app.patch("/api/project/{project_id}/audio/lyrics")
def api_update_lyrics(project_id: str, payload: Dict[str, Any]):
    """Manually update lyrics when auto-transcription fails."""
    state = load_project(project_id)
    
    new_lyrics = payload.get("lyrics", "").strip()
    if not new_lyrics:
        raise HTTPException(400, "Lyrics cannot be empty")
    
    audio_dna = state.get("audio_dna")
    if not audio_dna:
        raise HTTPException(400, "No audio DNA found")
    
    # Update lyrics - convert to list format
    lines = [l.strip() for l in new_lyrics.split("\n") if l.strip()]
    audio_dna["lyrics"] = [{"text": line} for line in lines]
    audio_dna["lyrics_source"] = "manual"
    
    # Also store raw text for display
    audio_dna["lyrics_text"] = new_lyrics
    
    print(f"[INFO] Lyrics updated manually: {len(lines)} lines")
    
    state["audio_dna"] = audio_dna
    save_project(state)
    
    return {"lyrics_count": len(lines), "source": "manual"}

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

    # v1.7.0: Style consistency instruction - tell AI to match style, not add the person
    style_instruction = "match the artistic style and color palette of the second reference image, do not include or blend the person from that reference, " if style_lock_url else ""
    
    prompt_a = f"{base_style}, {extra_prefix}{style_instruction}full body, standing, three-quarter view, slight angle, neutral pose, clean background, consistent identity, {negatives}"
    prompt_b = f"{base_style}, {extra_prefix}{style_instruction}portrait close-up, head and shoulders, three-quarter view, slight angle from side, neutral expression, clean background, consistent identity, {negatives}"

    # v1.7.0: Generate refs and track costs
    ref_a_url = call_img2img_editor(editor, prompt_a, ref_images, aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note="cast_ref_a")
    ref_b_url = call_img2img_editor(editor, prompt_b, ref_images, aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note="cast_ref_b")

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

        # v1.7.0: Track costs to fresh state (2 renders done, 2 separate entries)
        editor_cost = API_COSTS.get(f"fal-ai/{editor}", 0.04)
        if "costs" not in fresh_state:
            fresh_state["costs"] = {"total": 0.0, "calls": []}
        fresh_state["costs"]["total"] = round(fresh_state["costs"].get("total", 0) + (editor_cost * 2), 4)
        fresh_state["costs"]["calls"].append({"model": f"fal-ai/{editor}", "cost": round(editor_cost, 4), "ts": time.time(), "note": "ref_a"})
        fresh_state["costs"]["calls"].append({"model": f"fal-ai/{editor}", "cost": round(editor_cost, 4), "ts": time.time(), "note": "ref_b"})

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

    new_url = call_img2img_editor(editor, prompt, [refs[0]], aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note=f"cast_ref_{ref_type}")
    
    # v1.5.9.1: Store with friendly name in project folder
    cast_name = sanitize_filename(cast.get("name", cast_id), 20)
    local_path = download_image_locally(new_url, project_id, f"cast_{cast_id}_ref_{ref_type}", state=state, friendly_name=f"Cast_{cast_name}_Ref{ref_type.upper()}")
    
    # v1.6.5: Thread-safe save with lock
    with get_project_lock(project_id):
        fresh_state = load_project(project_id)
        char_refs = fresh_state.setdefault("cast_matrix", {}).setdefault("character_refs", {}).setdefault(cast_id, {})
        char_refs[f"ref_{ref_type}"] = local_path

        # v1.7.0: Track cost to fresh state
        editor_cost = API_COSTS.get(f"fal-ai/{editor}", 0.04)
        if "costs" not in fresh_state:
            fresh_state["costs"] = {"total": 0.0, "calls": []}
        fresh_state["costs"]["total"] = round(fresh_state["costs"].get("total", 0) + editor_cost, 4)
        fresh_state["costs"]["calls"].append({"model": f"fal-ai/{editor}", "cost": round(editor_cost, 4), "ts": time.time(), "note": f"ref_{ref_type}"})

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
    track_cost(f"fal-ai/{model_name}", 1, state=state, note="scene_decor")
    
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
        track_cost(f"fal-ai/{alt_model}", 1, state=state, note="scene_decor_alt")
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
    track_cost(f"fal-ai/{model}", 1, state=state, note="scene_decor_gen")

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
    result_url = call_img2img_editor(editor, full_prompt, [uploaded_url], aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note="scene_decor_edit")
    
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
        url, model_name = call_t2i_with_retry(state, dp, image_size)
        track_cost(f"fal-ai/{model_name}", 1, state=state, note="scene_decor_t2i")
        decor_refs.append(url)

    # decor_2: same room, different viewpoint (img2img off decor_1)
    decor2_prompt = base_prompt + ", same room, different camera angle, different framing, consistent architecture, consistent lighting"
    decor_2 = call_img2img_editor(editor, decor2_prompt, [decor_refs[0]], aspect, project_id)
    track_cost(f"fal-ai/{editor}", 1, state=state, note="scene_decor_i2i")
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
            # Add decor ref
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
                            print(f"[INFO] Added decor ref for scene {seq_idx}")
                        except:
                            pass
            
            # v1.7.0: Add wardrobe_ref for outfit consistency
            wardrobe_ref = scene.get("wardrobe_ref")
            if wardrobe_ref:
                if not wardrobe_ref.startswith("/renders/"):
                    ref_images.append(wardrobe_ref)
                    print(f"[INFO] Added wardrobe ref (external URL)")
                else:
                    local_file = resolve_render_path(wardrobe_ref)
                    if local_file.exists():
                        try:
                            uploaded_url = fal_client.upload_file(str(local_file))
                            ref_images.append(uploaded_url)
                            print(f"[INFO] Added wardrobe ref for scene {seq_idx}")
                        except Exception as e:
                            print(f"[WARN] Failed to upload wardrobe ref: {e}")
    
    # 2. v1.7.0: Select ref_a (full body) or ref_b (close-up) based on shot's camera_language
    camera_lang = (shot.get("camera_language") or "").lower()
    use_closeup = any(kw in camera_lang for kw in ["close-up", "closeup", "close up", "portrait", "head shot", "headshot", "face", "eyes"])
    ref_key = "ref_b" if use_closeup else "ref_a"
    print(f"[INFO] Shot {shot_id} cast={cast_ids}, camera='{camera_lang}' -> using {ref_key}")
    
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    print(f"[DEBUG] Available char_refs: {list(char_refs.keys())}")
    
    for cast_id in cast_ids[:2]:
        refs = char_refs.get(cast_id, {})
        if not refs:
            print(f"[WARN] No refs found for cast_id={cast_id}")
            continue
            
        ref_url = refs.get(ref_key) or refs.get("ref_a")  # Fallback to ref_a if ref_b missing
        if not ref_url:
            print(f"[WARN] No {ref_key} or ref_a URL for cast_id={cast_id}")
            continue
            
        print(f"[DEBUG] Cast {cast_id} {ref_key} URL: {ref_url[:60]}...")
        
        if not ref_url.startswith("/renders/"):
            ref_images.append(ref_url)
            print(f"[INFO] Using external URL for cast {cast_id}")
        else:
            local_file = resolve_render_path(ref_url)
            if local_file.exists():
                try:
                    uploaded_url = fal_client.upload_file(str(local_file))
                    ref_images.append(uploaded_url)
                    print(f"[INFO] Uploaded cast {ref_key} for {cast_id}: {uploaded_url[:60]}...")
                except Exception as e:
                    print(f"[ERROR] Failed to upload cast {ref_key} for {cast_id}: {e}")
            else:
                print(f"[ERROR] Local file not found: {local_file}")
    
    img_url = None
    model_name = "unknown"
    
    # If we have reference images, use img2img; otherwise fallback to t2i
    if ref_images:
        editor = locked_editor_key(state)
        try:
            img_url = call_img2img_editor(editor, prompt, ref_images, aspect, project_id)
            model_name = editor
            track_cost(f"fal-ai/{editor}", 1, state=state, note="shot_render")
        except Exception as e:
            print(f"[WARN] img2img failed, falling back to t2i: {e}")
            ref_images = []  # Clear to trigger t2i fallback
    
    if not img_url:
        # Fallback to t2i
        image_size = "landscape_16_9" if aspect=="horizontal" else ("portrait_16_9" if aspect=="vertical" else "square_hd")
        endpoint, payload, model_name = t2i_endpoint_and_payload(state, prompt, image_size)
        
        r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        track_cost(f"fal-ai/{model_name}", 1, state=state, note="shot_render_t2i")
        
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
        img_url = call_img2img_editor(editor, full_prompt, ref_images, aspect, project_id)
        track_cost(f"fal-ai/{editor}", 1, state=state, note="shot_edit")
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
        print(f"[DEBUG] FFmpeg cmd: {' '.join(final_cmd[:10])}...")
        print(f"[DEBUG] Concat file: {concat_file}")
        print(f"[DEBUG] Audio path: {audio_path}")
        print(f"[DEBUG] Output path: {output_path}")
        
        result = subprocess.run(final_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # Extract actual error from stderr (skip version info)
            stderr_lines = result.stderr.split('\n')
            error_lines = [l for l in stderr_lines if 'error' in l.lower() or 'invalid' in l.lower() or 'no such' in l.lower()]
            error_msg = '\n'.join(error_lines) if error_lines else result.stderr[-500:]
            print(f"[ERROR] FFmpeg failed: {result.stderr}")
            raise HTTPException(500, f"FFmpeg export failed: {error_msg}")
        
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