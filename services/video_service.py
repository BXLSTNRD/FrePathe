"""
Fré Pathé v1.8.1 - Video Service
Image-to-video generation via FAL AI (img2vid).
"""
import time
import requests
import fal_client
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    FAL_KEY, FAL_LTX2_I2V, FAL_KLING_I2V, FAL_VEO31_I2V, FAL_WAN_I2V, FAL_HAILUO_I2V, FAL_KANDINSKY5_I2V,
    fal_headers, track_cost, now_iso, retry_on_502, PATH_MANAGER,
)
from .project_service import (
    get_project_video_dir, download_image_locally,
)


# ========= Video Model Constants =========

VIDEO_MODELS = {
    "ltx2_i2v": {
        "name": "LTX-2 19B",
        "endpoint": FAL_LTX2_I2V,
        "cost": 0.10,
        "duration_range": (3, 10),
        "supports_audio": True,
        "description": "Fast, high-quality img2vid with audio generation",
    },
    "kling_i2v": {
        "name": "Kling Video v2.6 Pro",
        "endpoint": FAL_KLING_I2V,
        "cost": 0.25,
        "duration_range": (5, 10),
        "supports_audio": True,
        "description": "Cinematic quality with fluid motion and audio",
    },
    "veo31_i2v": {
        "name": "Veo 3.1 Fast",
        "endpoint": FAL_VEO31_I2V,
        "cost": 0.12,
        "duration_range": (4, 8),
        "supports_audio": True,
        "description": "Google SOTA with audio (4s/6s/8s, 720p/1080p/4K)",
    },
    "wan_i2v": {
        "name": "Wan v2.6",
        "endpoint": FAL_WAN_I2V,
        "cost": 0.15,
        "duration_range": (4, 8),
        "supports_audio": False,
        "description": "Cost-effective img2vid with good quality",
    },
    "hailuo_i2v": {
        "name": "MiniMax Hailuo 2.3 Pro",
        "endpoint": FAL_HAILUO_I2V,
        "cost": 0.18,
        "duration_range": (5, 10),
        "supports_audio": True,
        "description": "High-quality 1080p video with audio (6s fixed)",
    },
    "kandinsky5_i2v": {
        "name": "Kandinsky5 Pro",
        "endpoint": FAL_KANDINSKY5_I2V,
        "cost": 0.08,
        "duration_range": (5, 5),
        "supports_audio": False,
        "description": "Fast generation (5s fixed, 512p/1024p)",
    },
}

DEFAULT_VIDEO_MODEL = "ltx2_i2v"


# ========= FAL Image Upload =========

def upload_image_to_fal(image_url: str, state: Optional[Dict[str, Any]] = None) -> str:
    """
    Upload local image to FAL for img2vid processing.
    Uses FAL upload cache if available (from render_service).
    
    Args:
        image_url: Local /files/ URL or absolute path
        state: Project state (for cache access)
    
    Returns:
        FAL CDN URL (https://v3b.fal.media/...)
    """
    # Check cache first
    if state:
        cache = state.get("project", {}).get("fal_upload_cache", {})
        if image_url in cache:
            cached_url = cache[image_url]
            # Validate cached URL
            try:
                resp = requests.head(cached_url, timeout=5)
                if resp.status_code == 200:
                    print(f"[VIDEO] Using cached FAL URL for {image_url}")
                    return cached_url
            except Exception:
                pass
    
    # Convert /files/ URL to absolute path if needed
    original_url = image_url  # Store for cache key
    if image_url.startswith("/files/") or image_url.startswith("/renders/"):
        # v1.8.5: Use PATH_MANAGER.from_url() with state for migrated projects
        image_path = PATH_MANAGER.from_url(image_url, state)
        if not image_path.exists():
            raise Exception(f"Image file not found: {image_path}")
        image_url = str(image_path)
    
    # Upload to FAL
    try:
        print(f"[VIDEO] Uploading {image_url} to FAL...")
        fal_url = fal_client.upload_file(image_url)
        
        # Store in cache (use /files/ URL format as key for consistency)
        if state:
            if "project" not in state:
                state["project"] = {}
            if "fal_upload_cache" not in state["project"]:
                state["project"]["fal_upload_cache"] = {}
            # Always use /files/ URL format as cache key
            cache_key = original_url
            state["project"]["fal_upload_cache"][cache_key] = fal_url
        
        return fal_url
    except Exception as e:
        raise Exception(f"Failed to upload image to FAL: {str(e)}")


# ========= Core Img2Vid Functions =========

def call_img2vid(
    model_key: str,
    image_url: str,
    prompt: str = "",
    duration: float = 5.0,
    aspect_ratio: str = "16:9",
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Call FAL img2vid endpoint.
    
    Args:
        model_key: Video model key (ltx2_i2v, kling_i2v, veo31_i2v, wan_i2v)
        image_url: FAL CDN URL or local path (will be uploaded)
        prompt: Optional motion prompt
        duration: Video duration in seconds
        aspect_ratio: Aspect ratio (16:9, 9:16, 1:1)
        state: Project state
    
    Returns:
        {
            "video_url": "https://...",
            "duration": 5.0,
            "model": "ltx2_i2v",
            "has_audio": True/False,
        }
    """
    if model_key not in VIDEO_MODELS:
        model_key = DEFAULT_VIDEO_MODEL
    
    model_info = VIDEO_MODELS[model_key]
    endpoint = model_info["endpoint"]
    
    # Clamp duration to model limits
    min_dur, max_dur = model_info["duration_range"]
    duration = max(min_dur, min(max_dur, duration))
    
    # Upload image if needed
    if not image_url.startswith("https://"):
        image_url = upload_image_to_fal(image_url, state)
    
    # Build payload (model-specific)
    payload = {
        "image_url": image_url,
        "prompt": prompt or "Natural motion, cinematic quality",
    }
    
    # Model-specific parameters
    if model_key == "ltx2_i2v":
        # LTX-2 Distilled with LoRA endpoint
        num_frames = int(25 * duration)  # 25 fps
        payload["num_frames"] = min(481, max(9, num_frames))
        payload["generate_audio"] = True
        payload["use_multiscale"] = True
        payload["fps"] = 25
        payload["loras"] = []  # Empty loras array required
    elif model_key == "kling_i2v":
        payload["duration"] = int(duration)
        payload["aspect_ratio"] = aspect_ratio
        payload["creativity"] = 0.7
    elif model_key == "veo31_i2v":
        # Veo 3.1 Fast uses duration enum: "4s", "6s", "8s"
        dur = int(duration)
        if dur <= 5:
            veo_duration = "4s"
        elif dur <= 7:
            veo_duration = "6s"
        else:
            veo_duration = "8s"
        payload["duration"] = veo_duration
        payload["aspect_ratio"] = aspect_ratio
        payload["generate_audio"] = True
        payload["resolution"] = "720p"  # 720p/1080p/4k supported
    elif model_key == "wan_i2v":
        # Wan uses string duration: "5", "10", "15" - round to nearest
        dur = int(duration)
        if dur <= 7:
            wan_duration = "5"
        elif dur <= 12:
            wan_duration = "10"
        else:
            wan_duration = "15"
        payload["duration"] = wan_duration
        # Wan uses 720p/1080p with aspect ratio mapping
        if aspect_ratio == "9:16":
            payload["resolution"] = "720p"  # Vertical format
        else:
            payload["resolution"] = "1080p"  # Horizontal/square
    elif model_key == "hailuo_i2v":
        # Hailuo generates 6s videos, prompt optimizer enabled by default
        payload["prompt_optimizer"] = True
    elif model_key == "kandinsky5_i2v":
        # Kandinsky5 Pro: 5s fixed duration, 512p or 1024p resolution
        payload["duration"] = "5s"
        payload["resolution"] = "1024P"  # 512P or 1024P
        payload["num_inference_steps"] = 28
        payload["acceleration"] = "regular"
    
    print(f"[VIDEO] Calling {model_info['name']} img2vid...")
    print(f"[VIDEO] Image: {image_url[:80]}...")
    print(f"[VIDEO] Duration: {duration}s, Prompt: {prompt[:50]}...")
    print(f"[VIDEO] Payload: {payload}")
    
    try:
        response = requests.post(
            endpoint,
            headers=fal_headers(),
            json=payload,
            timeout=300,  # 5 min timeout for video generation
        )
        response.raise_for_status()
        result = response.json()
        print(f"[VIDEO] Generation complete!")
        
        # Extract video URL (model-specific response format)
        video_url = None
        if "video" in result:
            if isinstance(result["video"], dict):
                video_url = result["video"].get("url")
            else:
                video_url = result["video"]
        elif "video_url" in result:
            video_url = result["video_url"]
        elif "url" in result:
            video_url = result["url"]
        
        if not video_url:
            raise Exception(f"No video URL in response: {result}")
        
        # Track cost - extract endpoint path for cost lookup
        if state:
            endpoint_path = endpoint.replace("https://fal.run/", "")
            track_cost(endpoint_path, 1, state)
        
        return {
            "video_url": video_url,
            "duration": duration,
            "model": model_key,
            "has_audio": model_info["supports_audio"],
            "raw_response": result,
        }
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"FAL API error: {str(e)}")


@retry_on_502
def call_img2vid_with_retry(
    model_key: str,
    image_url: str,
    prompt: str = "",
    duration: float = 5.0,
    aspect_ratio: str = "16:9",
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Call img2vid with automatic retry on 502 errors.
    """
    return call_img2vid(model_key, image_url, prompt, duration, aspect_ratio, state)


# ========= Shot Video Generation =========

def generate_shot_video(
    state: Dict[str, Any],
    shot: Dict[str, Any],
    video_model: str,
    download_locally: bool = True,
) -> Dict[str, Any]:
    """
    Generate video for a single shot using img2vid.
    
    Args:
        state: Project state
        shot: Shot data (must have render.image_url)
        video_model: Video model key
        download_locally: Whether to download video to project folder
    
    Returns:
        Updated shot with video data in render.video
    """
    # Validate shot has render
    render = shot.get("render", {})
    image_url = render.get("image_url")
    
    if not image_url:
        raise ValueError(f"Shot {shot.get('shot_id')} has no rendered image")
    
    # Calculate duration
    start = float(shot.get("start", 0))
    end = float(shot.get("end", 0))
    target_duration = end - start  # Storyboard timing (for audio sync)
    
    if target_duration <= 0:
        raise ValueError(f"Shot {shot.get('shot_id')} has invalid duration: {target_duration}")
    
    # Duration for generation (will be clamped to model limits)
    duration = target_duration
    
    # Build motion prompt from shot metadata
    motion_prompt = build_shot_motion_prompt(shot)
    
    # Get aspect ratio from project
    aspect_setting = state.get("project", {}).get("aspect", "horizontal")
    aspect = {"horizontal": "16:9", "vertical": "9:16", "square": "1:1"}.get(aspect_setting, "16:9")
    
    # Generate video
    video_result = call_img2vid_with_retry(
        model_key=video_model,
        image_url=image_url,
        prompt=motion_prompt,
        duration=duration,
        aspect_ratio=aspect,
        state=state,
    )
    
    video_url = video_result["video_url"]
    
    # Download locally if requested  
    local_path = None
    if download_locally:
        project_id = state.get("project", {}).get("project_id")
        shot_id = shot.get("shot_id", "unknown")
        
        # Download video file (skip thumbnail generation for videos)
        try:
            video_dir = get_project_video_dir(state)
            video_dir.mkdir(parents=True, exist_ok=True)
            
            local_filename = f"video_{shot_id}.mp4"
            local_path = video_dir / local_filename
            
            # Download video
            print(f"[VIDEO] Downloading video to {local_path}...")
            response = requests.get(video_url, timeout=60)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            print(f"[VIDEO] Video saved locally: {local_path}")
            
            # Convert to URL path
            video_url = PATH_MANAGER.to_url(local_path)
            local_path = str(local_path)
        except Exception as e:
            print(f"[WARN] Video download failed: {e}")
            local_path = None
    
    # Update shot render data
    if "render" not in shot:
        shot["render"] = {}
    
    shot["render"]["video"] = {
        "video_url": video_url,
        "local_path": local_path,
        "duration": video_result["duration"],  # Actual generated duration (model-clamped)
        "target_duration": target_duration,      # Storyboard duration (for audio sync trimming)
        "model": video_result["model"],
        "has_audio": video_result["has_audio"],
        "generated_at": now_iso(),
        "motion_prompt": motion_prompt,
    }
    
    return shot


def build_shot_motion_prompt(shot: Dict[str, Any]) -> str:
    """
    Build motion prompt from shot metadata.
    
    Extracts camera movement, energy, and symbolic elements
    to guide video motion generation.
    """
    parts = []
    
    # Camera language
    camera = shot.get("camera_language", "").strip()
    if camera:
        parts.append(camera)
    
    # Energy/dynamics
    energy = shot.get("energy", 0.5)
    if energy > 0.7:
        parts.append("dynamic motion")
    elif energy < 0.3:
        parts.append("subtle motion")
    
    # Environment
    env = shot.get("environment", "").strip()
    if env:
        parts.append(env)
    
    # Symbolic elements (select first 2)
    symbolic = shot.get("symbolic_elements", [])
    if symbolic:
        parts.extend(symbolic[:2])
    
    # Default if empty
    if not parts:
        return "Natural cinematic motion, smooth camera movement"
    
    return ", ".join(parts)


# ========= Batch Video Generation =========

async def _generate_shot_video_async(
    state: Dict[str, Any],
    shot: Dict[str, Any],
    video_model: str,
    semaphore: Any,
) -> tuple[str, bool, Optional[str]]:
    """
    Generate video for a single shot with semaphore control.
    
    Returns:
        (shot_id, success, error_msg)
    """
    from .config import VIDEO_SEMAPHORE
    
    shot_id = shot.get("shot_id", "unknown")
    
    async with semaphore:
        try:
            # Run sync function in thread pool
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, generate_shot_video, state, shot, video_model)
            print(f"[VIDEO] Generated video for {shot_id}")
            return (shot_id, True, None)
        except Exception as e:
            error_msg = str(e)
            print(f"[VIDEO] Failed {shot_id}: {error_msg}")
            return (shot_id, False, error_msg)


async def generate_videos_for_shots(
    state: Dict[str, Any],
    shot_ids: Optional[List[str]] = None,
    video_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    v1.8.2: Generate videos for multiple shots with async concurrency (max 8 parallel).
    
    Args:
        state: Project state
        shot_ids: List of shot IDs (None = all rendered shots)
        video_model: Video model key (None = use project setting)
    
    Returns:
        {
            "success": 5,
            "failed": 1,
            "skipped": 2,
            "total": 8,
            "errors": {...}
        }
    """
    import asyncio
    from .config import VIDEO_SEMAPHORE
    
    # Get video model from project or default
    if not video_model:
        video_model = state.get("project", {}).get("video_model", DEFAULT_VIDEO_MODEL)
    
    # Get shots
    all_shots = state.get("storyboard", {}).get("shots", [])
    
    # Filter by shot_ids if provided
    if shot_ids:
        shots = [s for s in all_shots if s.get("shot_id") in shot_ids]
    else:
        # All rendered shots
        shots = [s for s in all_shots if s.get("render", {}).get("image_url")]
    
    # Separate shots that need generation vs already have video
    to_generate = []
    skipped_count = 0
    
    for shot in shots:
        shot_id = shot.get("shot_id", "unknown")
        if shot.get("render", {}).get("video", {}).get("video_url"):
            print(f"[VIDEO] Skipping {shot_id} - already has video")
            skipped_count += 1
        else:
            to_generate.append(shot)
    
    results = {
        "success": 0,
        "failed": 0,
        "skipped": skipped_count,
        "total": len(shots),
        "errors": {},
    }
    
    # Generate videos concurrently (max 8 parallel)
    if to_generate:
        print(f"[VIDEO] Generating {len(to_generate)} videos with concurrency=8...")
        tasks = [
            _generate_shot_video_async(state, shot, video_model, VIDEO_SEMAPHORE)
            for shot in to_generate
        ]
        
        # Execute all tasks concurrently
        task_results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # Process results
        for shot_id, success, error_msg in task_results:
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                results["errors"][shot_id] = error_msg
    
    return results


# ========= Video Model Utilities =========

def get_video_model_info(model_key: str) -> Dict[str, Any]:
    """Get info about a video model."""
    return VIDEO_MODELS.get(model_key, VIDEO_MODELS[DEFAULT_VIDEO_MODEL])


def get_video_model_duration_guidance(state: Dict[str, Any]) -> tuple:
    """
    v1.8.8: Get duration constraints and LLM guidance string for the selected video model.
    
    Returns:
        (min_dur, max_dur, guidance_string)
    """
    video_model_key = state.get("project", {}).get("video_model", "none")
    video_model_info = VIDEO_MODELS.get(video_model_key) if video_model_key != "none" else None
    
    if video_model_info:
        min_dur, max_dur = video_model_info.get("duration_range", (2, 5))
        model_name = video_model_info.get("name", video_model_key)
        if min_dur == max_dur:
            guidance = f"EXACTLY {min_dur} seconds (video model {model_name} has fixed duration)"
        else:
            guidance = f"{min_dur}-{max_dur} seconds (video model {model_name} requirements)"
    else:
        min_dur, max_dur = 2, 5
        guidance = "2-5 seconds"
    
    return min_dur, max_dur, guidance


def list_video_models() -> List[Dict[str, Any]]:
    """List all available video models with metadata."""
    return [
        {
            "key": key,
            **info,
        }
        for key, info in VIDEO_MODELS.items()
    ]
