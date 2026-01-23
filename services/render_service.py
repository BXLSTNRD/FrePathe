"""
Fré Pathé v1.7 - Render Service
Handles image generation (txt2img, img2img), FAL API calls, and render management.
"""
import requests
import json
import time
import fal_client
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .config import (
    DEBUG_DIR,
    FAL_KEY,
    FAL_NANOBANANA,
    FAL_NANOBANANA_EDIT,
    FAL_SEEDREAM45,
    FAL_SEEDREAM45_EDIT,
    FAL_FLUX2,
    FAL_FLUX2_EDIT,
    MODEL_TO_ENDPOINT,
    fal_headers,
    require_key,
    retry_on_502,
    track_cost,
    PATH_MANAGER,
    locked_model_key,
    locked_editor_key,
)


# ========= Debug Logging =========

def save_fal_debug(
    call_type: str,
    endpoint: str,
    payload: Dict[str, Any],
    response: Any,
    project_id: str = "unknown",
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Save FAL API call for debugging - prompts, image refs, and response."""
    try:
        ts = int(time.time())
        log_file = DEBUG_DIR / f"{project_id}_fal_{ts}.json"
        
        # Extract image URLs from payload for easy inspection
        image_refs = []
        if "image_url" in payload:
            image_refs.append(payload["image_url"])
        if "image_urls" in payload:
            image_refs.extend(payload["image_urls"])
        if "control_images" in payload:
            for ci in payload.get("control_images", []):
                if isinstance(ci, dict) and ci.get("image_url"):
                    image_refs.append(ci["image_url"])
        
        log_data = {
            "timestamp": ts,
            "call_type": call_type,
            "endpoint": endpoint,
            "prompt": payload.get("prompt", ""),
            "image_refs": image_refs,
            "full_payload": payload,
            "response": response,
        }
        if extra:
            log_data["extra"] = extra
            
        log_file.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[DEBUG] Saved FAL call log: {log_file.name}")
    except Exception as e:
        print(f"[WARN] Failed to log FAL call: {e}")


# ========= Model Helpers =========

def model_to_endpoint(model_key: str) -> str:
    """Convert model key to FAL endpoint URL."""
    endpoints = {
        "nanobanana": FAL_NANOBANANA,
        "seedream45": FAL_SEEDREAM45,
        "flux2": FAL_FLUX2,
        "nanobanana_edit": FAL_NANOBANANA_EDIT,
        "seedream45_edit": FAL_SEEDREAM45_EDIT,
        "flux2_edit": FAL_FLUX2_EDIT,
    }
    return endpoints.get(model_key, FAL_NANOBANANA)


# ========= Text-to-Image =========

def call_txt2img(
    model_key: str, 
    prompt: str, 
    aspect: str, 
    state: Dict[str, Any] = None
) -> str:
    """
    Generate image from text prompt using FAL.
    Returns the output image URL.
    """
    require_key("FAL_KEY", FAL_KEY)
    
    # Build aspect ratio parameters
    aspect_ratio = "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1")
    image_size = "landscape_16_9" if aspect == "horizontal" else ("portrait_16_9" if aspect == "vertical" else "square_hd")
    width = 1920 if aspect == "horizontal" else (1080 if aspect == "vertical" else 1024)
    height = 1080 if aspect == "horizontal" else (1920 if aspect == "vertical" else 1024)
    
    endpoint = model_to_endpoint(model_key)
    
    if model_key == "nanobanana":
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "output_format": "png",
            "resolution": "2K",
        }
    elif model_key == "seedream45":
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "width": width,
            "height": height,
            "num_images": 1,
        }
    elif model_key == "flux2":
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_format": "png",
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
        }
    else:
        # Default to nanobanana
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_format": "png",
        }
    
    def do_request():
        try:
            r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        except requests.exceptions.RequestException as e:
            raise HTTPException(502, f"txt2img network error: {type(e).__name__}: {str(e)[:200]}")
        
        if r.status_code >= 500:
            raise HTTPException(502, f"txt2img failed: {r.status_code} {r.text[:500]}")
        elif r.status_code >= 400:
            raise HTTPException(r.status_code, f"txt2img failed: {r.status_code} {r.text[:500]}")
        return r
    
    r = retry_on_502(do_request)()
    out = r.json()
    
    # Extract image URL from response
    img_url = None
    if isinstance(out, dict) and isinstance(out.get("images"), list) and out["images"]:
        img_url = out["images"][0].get("url")
    
    if not img_url:
        raise HTTPException(502, "txt2img returned no image url")
    
    # Log the call
    project_id = (state or {}).get("project", {}).get("id", "unknown")
    save_fal_debug("txt2img", endpoint, payload, {"image_url": img_url}, project_id, {"model_key": model_key})
    
    return img_url


# ========= Image-to-Image =========

def call_img2img_editor(
    editor_key: str,
    prompt: str,
    image_urls: List[str],
    aspect: str,
    project_id: str = "unknown",
    state: Optional[Dict[str, Any]] = None,
    force_single_ref: bool = False,
) -> str:
    """
    Generate image from reference images + prompt using FAL img2img.
    Returns the first output image URL or raises HTTPException.
    
    editor_key: flux2_edit | nanobanana_edit | seedream45_edit
    state: Optional project state for upload caching
    """
    require_key("FAL_KEY", FAL_KEY)

    if not image_urls:
        raise HTTPException(400, "img2img requires at least 1 image_url")

    # Defensive enforcement: if caller requests strict single-ref behavior,
    # ensure we only process one reference image regardless of input.
    if force_single_ref and len(image_urls) > 1:
        print(f"[DEFENSE] force_single_ref enabled: trimming {len(image_urls)} refs to 1")
        image_urls = image_urls[:1]
    
    # Upload local refs to FAL (convert /files/ paths to fal.media URLs)
    # Uses state cache to avoid re-uploading same refs
    uploaded_refs = []
    for ref_url in image_urls:
        try:
            uploaded = upload_local_ref_to_fal(ref_url, state=state)
            uploaded_refs.append(uploaded)
        except Exception as e:
            print(f"[WARN] Skipping ref {ref_url}: upload failed: {e}")
    
    if not uploaded_refs:
        raise HTTPException(400, "All ref images failed to upload")
    
    image_urls = uploaded_refs  # Use uploaded URLs

    # Build aspect ratio parameters
    aspect_ratio = "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1")
    image_size = "landscape_16_9" if aspect == "horizontal" else ("portrait_16_9" if aspect == "vertical" else "square_hd")
    width = 1920 if aspect == "horizontal" else (1080 if aspect == "vertical" else 1024)
    height = 1080 if aspect == "horizontal" else (1920 if aspect == "vertical" else 1024)

    if editor_key == "flux2_edit":
        endpoint = FAL_FLUX2_EDIT
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:4],  # max 4
            "guidance_scale": 2.5,
            "num_inference_steps": 28,
            "output_format": "png",
            "aspect_ratio": aspect_ratio,
        }
    elif editor_key == "nanobanana_edit":
        endpoint = FAL_NANOBANANA_EDIT
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:4],
            "output_format": "png",
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "resolution": "2K",
        }
        print(f"[INFO] NanoBanana img2img: aspect={aspect}, aspect_ratio={aspect_ratio}, image_size={image_size}, ref_count={len(image_urls)}")
    elif editor_key == "seedream45_edit":
        endpoint = FAL_SEEDREAM45_EDIT
        payload = {
            "prompt": prompt,
            "image_urls": image_urls[:10],  # max 10
            "num_images": 1,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "width": width,
            "height": height,
        }
        print(f"[INFO] Seedream img2img: aspect={aspect}, {width}x{height}, ref_count={len(image_urls)}")
    else:
        raise HTTPException(400, f"Unknown img2img_editor: {editor_key}")

    def do_request():
        try:
            r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        except requests.exceptions.RequestException as e:
            raise HTTPException(502, f"img2img network error: {type(e).__name__}: {str(e)[:200]}")
        
        if r.status_code >= 500:
            raise HTTPException(502, f"img2img editor failed: {r.status_code} {r.text[:500]}")
        elif r.status_code >= 400:
            raise HTTPException(r.status_code, f"img2img editor failed: {r.status_code} {r.text[:500]}")
        return r
    
    r = retry_on_502(do_request)()
    out = r.json()
    
    img_url = None
    if isinstance(out, dict) and isinstance(out.get("images"), list) and out["images"]:
        img_url = out["images"][0].get("url")

    if not img_url:
        raise HTTPException(502, "img2img editor returned no image url")

    # Log the call
    save_fal_debug("img2img", endpoint, payload, {"image_url": img_url}, project_id, {"editor_key": editor_key, "ref_count": len(image_urls)})

    return img_url


# ========= Render Path Resolution =========

def resolve_render_path(url_or_path: str, state: Optional[Dict[str, Any]] = None) -> Path:
    """Resolve /renders/ URL or path to actual file path."""
    # v1.8.5: Use PATH_MANAGER with state for migrated project paths
    if url_or_path.startswith("/"):
        # It's a URL path - use PATH_MANAGER to convert
        return PATH_MANAGER.from_url(url_or_path, state)
    else:
        # It's a relative path - resolve relative to workspace root
        return PATH_MANAGER.workspace_root / url_or_path


# ========= Shot Render Helpers =========

def build_shot_prompt(
    shot: Dict[str, Any],
    state: Dict[str, Any],
    style_tokens: List[str],
    scene: Optional[Dict[str, Any]] = None
) -> str:
    """Build the full prompt for rendering a shot."""
    prompt_parts = []
    
    # 1. Style tokens
    prompt_parts.extend(style_tokens)
    
    # 2. Base prompt from shot
    if shot.get("prompt_base"):
        prompt_parts.append(shot["prompt_base"])
    
    # 3. Environment from shot
    if shot.get("environment"):
        prompt_parts.append(shot["environment"])
    
    # 4. Camera language
    if shot.get("camera_language"):
        prompt_parts.append(shot["camera_language"])
    
    # 5. Intent
    if shot.get("intent"):
        prompt_parts.append(shot["intent"])
    
    # 6. Scene context
    if scene and scene.get("prompt"):
        prompt_parts.append(scene["prompt"][:100])  # Truncate
    
    # 7. Wardrobe from shot or scene
    wardrobe = shot.get("wardrobe", {})
    if isinstance(wardrobe, dict):
        # Per-cast wardrobe
        wardrobe_texts = [v for v in wardrobe.values() if v]
        if wardrobe_texts:
            prompt_parts.append(", ".join(wardrobe_texts[:2]))  # First 2
    elif scene and scene.get("wardrobe"):
        prompt_parts.append(scene["wardrobe"])
    
    # 7b. Decor alternative from scene
    if scene and scene.get("decor_alt"):
        prompt_parts.append(scene["decor_alt"])
    
    # 8. Standard quality tokens
    prompt_parts.extend(["high quality", "detailed", "consistent identity"])
    
    # Clean and join
    prompt = ", ".join(p.strip() for p in prompt_parts if p and p.strip())
    return prompt


def upload_local_ref_to_fal(url: str, state: Optional[Dict[str, Any]] = None) -> str:
    """
    Upload local /files/ URL to FAL if needed. Returns FAL URL or original.
    Uses persistent cache in project state (survives reloads).
    Cache is stored in project.fal_upload_cache for persistence.
    """
    if not url:
        return url
    
    # Already a FAL URL or external URL
    if "fal.media" in url or (url.startswith("http") and not url.startswith("/files/")):
        return url
    
    # Check persistent cache first (survives project reloads)
    if state:
        cache = state.get("project", {}).get("fal_upload_cache", {})
        if url in cache:
            cached_fal_url = cache[url]
            # Verify cached URL still works (FAL URLs expire after ~24h)
            try:
                test = requests.head(cached_fal_url, timeout=5)
                if test.status_code < 400:
                    print(f"[CACHE] Using cached FAL URL for: {Path(url).name}")
                    return cached_fal_url
                else:
                    print(f"[CACHE] Cached URL expired, re-uploading: {Path(url).name}")
            except:
                print(f"[CACHE] Cache validation failed, re-uploading: {Path(url).name}")
    
    # Local /files/ path needs upload
    if url.startswith("/files/"):
        try:
            # v1.8.5: from_url now checks project folder when state provided
            local_path = PATH_MANAGER.from_url(url, state)
            
            if not local_path.exists():
                print(f"[WARN] Ref image not found: {local_path}")
                return url
            
            print(f"[INFO] Uploading ref to FAL: {local_path.name}")
            fal_url = fal_client.upload_file(str(local_path))
            
            # Cache the result persistently in project state
            if state:
                if "fal_upload_cache" not in state["project"]:
                    state["project"]["fal_upload_cache"] = {}
                state["project"]["fal_upload_cache"][url] = fal_url
                # Mark project as modified (will be saved)
                state["_cache_modified"] = True
            
            return fal_url
        except Exception as e:
            print(f"[ERROR] FAL upload failed for {url}: {e}")
            return url  # Return original, let FAL handle the error
    
    return url


def prewarm_fal_upload_cache(state: Dict[str, Any]) -> int:
    """
    Pre-upload ALL cast refs and scene decors to FAL before rendering starts.
    Returns number of new uploads performed.
    Call this once at render session start to avoid upload delays per shot.
    """
    uploads = 0
    to_upload = []
    
    # Collect all unique ref URLs that need uploading
    # Note: Style lock excluded - only used for cast ref generation, not shot rendering
    
    # 1. All cast refs (ref_a and ref_b)
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    for cast_id, refs in char_refs.items():
        for key in ["ref_a", "ref_b"]:
            ref_url = refs.get(key)
            if ref_url and ref_url.startswith("/files/") and ref_url not in to_upload:
                to_upload.append(ref_url)
    
    # 3. All scene decors
    scenes = state.get("cast_matrix", {}).get("scenes", [])
    for scene in scenes:
        decor_refs = scene.get("decor_refs", [])
        for decor in decor_refs:
            if decor and decor.startswith("/files/") and decor not in to_upload:
                to_upload.append(decor)
        
        # Wardrobe refs
        wardrobe_ref = scene.get("wardrobe_ref")
        if wardrobe_ref and wardrobe_ref.startswith("/files/") and wardrobe_ref not in to_upload:
            to_upload.append(wardrobe_ref)
    
    # Upload all
    if to_upload:
        print(f"[PREWARM] Pre-uploading {len(to_upload)} refs to FAL...")
        for ref_url in to_upload:
            # This will use cache if already uploaded, or upload if new
            fal_url = upload_local_ref_to_fal(ref_url, state=state)
            if fal_url != ref_url and "fal.media" in fal_url:
                uploads += 1
        print(f"[PREWARM] Complete: {uploads} new uploads, {len(to_upload)-uploads} from cache")
    
    return uploads


def get_shot_ref_images(
    shot: Dict[str, Any],
    state: Dict[str, Any],
    scene: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Get all reference images for rendering a shot."""
    refs = []
    
    # Note: Style lock is NOT included - it's only for cast ref generation
    
    # 1. Cast refs (ref_a for each cast member)
    cast_ids = shot.get("cast", [])
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    for cid in cast_ids:
        ref_a = char_refs.get(cid, {}).get("ref_a")
        if ref_a and ref_a not in refs:
            refs.append(ref_a)
    
    # 3. Scene decor
    if scene:
        decor = scene.get("decor_refs", [])
        if decor and decor[0] and decor[0] not in refs:
            refs.append(decor[0])
        
        # Wardrobe ref
        wardrobe_ref = scene.get("wardrobe_ref")
        if wardrobe_ref and wardrobe_ref not in refs:
            refs.append(wardrobe_ref)
    
    return refs


# ========= Render Status =========

def update_shot_render(
    shot: Dict[str, Any],
    status: str,
    image_url: Optional[str] = None,
    model: Optional[str] = None,
    error: Optional[str] = None,
    ref_images_used: int = 0
) -> Dict[str, Any]:
    """Update shot render status."""
    shot["render"] = {
        "status": status,
        "image_url": image_url,
        "model": model,
        "ref_images_used": ref_images_used,
        "error": error,
    }
    return shot["render"]


def get_pending_shots(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get all shots that need rendering."""
    shots = state.get("storyboard", {}).get("shots", [])
    pending = []
    
    for shot in shots:
        render = shot.get("render", {})
        status = render.get("status", "none")
        if status not in ("done", "rendering"):
            pending.append(shot)
    
    return pending


def get_render_stats(state: Dict[str, Any]) -> Dict[str, Any]:
    """Get rendering statistics for a project."""
    shots = state.get("storyboard", {}).get("shots", [])
    
    total = len(shots)
    done = sum(1 for s in shots if s.get("render", {}).get("status") == "done")
    failed = sum(1 for s in shots if s.get("render", {}).get("status") == "error")
    pending = total - done - failed
    
    return {
        "total": total,
        "done": done,
        "failed": failed,
        "pending": pending,
        "progress": round(done / total * 100, 1) if total > 0 else 0,
    }


# ========= T2I Helpers (v1.6.9) =========

def t2i_endpoint_and_payload(state: Dict[str, Any], prompt: str, image_size: str) -> tuple:
    """
    Return (endpoint, payload, model_name) for the locked T2I model.
    """
    rm = (state.get("project") or {}).get("render_models") or {}
    model = (rm.get("image_model") or "fal-ai/nano-banana-pro").strip().lower()

    if model == "fal-ai/flux-2":
        return (FAL_FLUX2, {"prompt": prompt, "image_size": image_size}, "fal-ai/flux-2")
    if model == "fal-ai/bytedance/seedream/v4.5/text-to-image":
        return (FAL_SEEDREAM45, {"prompt": prompt, "image_size": image_size}, "fal-ai/bytedance/seedream/v4.5/text-to-image")

    # nano-banana-pro
    aspect = (state.get("project") or {}).get("aspect") or "horizontal"
    aspect_ratio = "16:9" if aspect == "horizontal" else ("9:16" if aspect == "vertical" else "1:1")
    return (FAL_NANOBANANA, {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": "1K"}, "fal-ai/nano-banana-pro")


def call_t2i_with_retry(state: Dict[str, Any], prompt: str, image_size: str) -> tuple:
    """v1.6.1: Call T2I endpoint with retry on 5xx. Returns (image_url, model_name)."""
    endpoint, payload, model_name = t2i_endpoint_and_payload(state, prompt, image_size)
    
    def do_request():
        try:
            r = requests.post(endpoint, headers=fal_headers(), json=payload, timeout=300)
        except requests.exceptions.RequestException as e:
            raise HTTPException(502, f"T2I network error: {type(e).__name__}: {str(e)[:200]}")
        
        if r.status_code >= 500:
            raise HTTPException(502, f"T2I failed: {r.status_code} {r.text[:500]}")
        elif r.status_code >= 400:
            raise HTTPException(r.status_code, f"T2I failed: {r.status_code} {r.text[:500]}")
        out = r.json()
        if isinstance(out.get("images"), list) and out["images"] and out["images"][0].get("url"):
            return out["images"][0]["url"]
        raise HTTPException(502, "T2I returned no image url")
    
    url = retry_on_502(do_request)()
    
    # Log the call
    project_id = (state or {}).get("project", {}).get("id", "unknown")
    save_fal_debug("t2i_shot", endpoint, payload, {"image_url": url}, project_id, {"model_name": model_name})
    
    return url, model_name


# ========= Prompt Helpers (v1.6.9) =========

def energy_tokens(energy: float) -> list:
    """Get prompt tokens based on energy level (0.0-1.0)."""
    e = float(energy or 0.5)
    if e <= 0.3:
        return ["quiet", "minimal motion", "slow camera"]
    if e <= 0.7:
        return ["steady motion", "medium intensity"]
    return ["high intensity", "aggressive motion", "dramatic lighting"]


def build_prompt(state: Dict[str, Any], shot: Dict[str, Any]) -> str:
    """Build a complete render prompt from state and shot data."""
    from .styles import style_tokens  # Import here to avoid circular imports
    
    st = state["project"]["style_preset"]
    aspect = state["project"]["aspect"]
    parts: List[str] = []
    parts += style_tokens(st)
    parts += [f"aspect {aspect}"]
    parts += energy_tokens(shot.get("energy", 0.5))
    parts += [shot.get("prompt_base", ""), shot.get("camera_language", ""), shot.get("environment", "")]
    if isinstance(shot.get("symbolic_elements"), list):
        parts += shot["symbolic_elements"]
    parts += ["no text", "no watermark", "no subtitles", "no logo"]
    return ", ".join([p.strip() for p in parts if p and str(p).strip()])
