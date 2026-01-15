"""
Fré Pathé v1.7 - Export Service
Handles video export with FFmpeg.
"""
import subprocess
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .config import PATH_MANAGER
from .project_service import (
    sanitize_filename,
    get_project_video_dir,
)


# ========= Export Status Tracking =========

EXPORT_STATUS: Dict[str, Dict[str, Any]] = {}


def update_export_status(
    project_id: str, 
    status: str, 
    current: int = 0, 
    total: int = 0, 
    message: str = ""
) -> None:
    """Update export status for polling."""
    EXPORT_STATUS[project_id] = {
        "status": status,  # "idle", "processing", "done", "error"
        "current": current,
        "total": total,
        "message": message,
        "updated_at": time.time()
    }


def get_export_status(project_id: str) -> Dict[str, Any]:
    """Get export status for polling."""
    return EXPORT_STATUS.get(project_id, {
        "status": "idle", 
        "current": 0, 
        "total": 0, 
        "message": ""
    })


# ========= FFmpeg Helpers =========

def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    return shutil.which("ffmpeg") is not None


def create_video_clip(
    image_path: Path,
    output_path: Path,
    duration: float,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30
) -> bool:
    """
    Create a video clip from a single image.
    Returns True on success.
    """
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-t", str(duration),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] FFmpeg clip creation failed: {e.stderr[:200] if e.stderr else str(e)}")
        return False


def concat_clips_with_audio(
    concat_file: Path,
    audio_path: Path,
    output_path: Path
) -> bool:
    """
    Concatenate video clips and add audio using FFmpeg.
    Returns True on success.
    """
    cmd = [
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
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] FFmpeg concat failed: {result.stderr}")
        return False
    
    return True


# ========= Video Export =========

def resolve_image_path(img_url: str) -> Optional[Path]:
    """
    v1.8.0: Resolve render URL to file path using PATH_MANAGER.
    """
    if img_url.startswith("/"):
        # URL path - convert using PATH_MANAGER
        img_path = PATH_MANAGER.from_url(img_url)
    else:
        # Absolute path
        img_path = Path(img_url)
    
    return img_path if img_path.exists() else None


def export_video(
    state: Dict[str, Any],
    project_id: str,
    fade_duration: float = 0.5,
    fps: int = 30,
    resolution: str = "1920x1080"
) -> Dict[str, Any]:
    """
    Export storyboard as video with FFmpeg.
    
    Args:
        state: Project state
        project_id: Project ID
        fade_duration: Fade duration between scenes (currently unused with concat)
        fps: Frames per second
        resolution: Output resolution (e.g., "1920x1080")
    
    Returns:
        Dict with video_url, shots_exported, duration_sec, scene_transitions
    """
    if not check_ffmpeg():
        raise HTTPException(500, "FFmpeg not found. Install FFmpeg and add to PATH.")
    
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
    
    # Parse resolution
    res_parts = resolution.split("x")
    width = int(res_parts[0])
    height = int(res_parts[1]) if len(res_parts) > 1 else width
    
    # Setup directories
    video_dir = get_project_video_dir(state)
    temp_dir = video_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Output path
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
            img_path = resolve_image_path(img_url)
            
            if not img_path:
                print(f"[WARN] Shot {shot.get('shot_id')} image not found: {img_url}")
                skipped.append(shot.get('shot_id', f'idx_{i}'))
                continue
            
            duration = float(shot.get("end", 0)) - float(shot.get("start", 0))
            if duration <= 0:
                print(f"[WARN] Shot {shot.get('shot_id')} has invalid duration: {duration}")
                skipped.append(shot.get('shot_id', f'idx_{i}'))
                continue
            
            clip_path = temp_dir / f"clip_{i:03d}.mp4"
            
            success = create_video_clip(
                image_path=img_path,
                output_path=clip_path,
                duration=duration,
                width=width,
                height=height,
                fps=fps
            )
            
            if success:
                clip_paths.append({
                    "path": clip_path,
                    "shot": shot,
                    "duration": duration,
                    "seq_id": shot.get("sequence_id", "")
                })
                print(f"[INFO] Created clip {i+1}/{total_shots}: {shot.get('shot_id')} ({duration:.1f}s)")
                update_export_status(project_id, "processing", i+1, total_shots, f"Created clip {i+1}/{total_shots}: {shot.get('shot_id')}")
            else:
                skipped.append(shot.get('shot_id', f'idx_{i}'))
        
        print(f"[INFO] Created {len(clip_paths)} clips, skipped {len(skipped)}")
        
        if not clip_paths:
            update_export_status(project_id, "error", 0, 0, "No clips created")
            raise HTTPException(500, "No clips created")
        
        # Step 2: Create concat file
        total_duration = sum(c["duration"] for c in clip_paths)
        print(f"[INFO] Expected video duration: {total_duration:.1f}s from {len(clip_paths)} clips")
        update_export_status(project_id, "processing", total_shots, total_shots, f"Concatenating {len(clip_paths)} clips...")
        
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for clip in clip_paths:
                # FFmpeg concat format requires forward slashes
                clip_path_str = str(clip["path"]).replace("\\", "/")
                f.write(f"file '{clip_path_str}'\n")
        
        # Step 3: Concat and add audio
        success = concat_clips_with_audio(
            concat_file=concat_file,
            audio_path=Path(audio_path),
            output_path=output_path
        )
        
        if not success:
            update_export_status(project_id, "error", 0, 0, "FFmpeg concat failed")
            raise HTTPException(500, "FFmpeg export failed")
        
        # Calculate scene transitions
        scene_transitions = sum(
            1 for i in range(1, len(clip_paths)) 
            if clip_paths[i-1]["seq_id"] != clip_paths[i]["seq_id"]
        )
        
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
        
        # Return video URL relative to DATA
        rel_path = output_path.relative_to(DATA)
        video_url = f"/renders/{rel_path.as_posix()}"
        
        update_export_status(
            project_id, "done", 
            total_shots, total_shots, 
            f"Export complete: {len(clip_paths)} clips, {total_duration:.1f}s"
        )
        
        return {
            "video_url": video_url,
            "shots_exported": len(clip_paths),
            "duration_sec": total_duration,
            "scene_transitions": scene_transitions,
            "skipped_shots": skipped,
        }
        
    except subprocess.CalledProcessError as e:
        update_export_status(project_id, "error", 0, 0, f"FFmpeg error: {str(e)[:100]}")
        raise HTTPException(500, f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        update_export_status(project_id, "error", 0, 0, f"Export failed: {str(e)[:100]}")
        raise HTTPException(500, f"Export failed: {str(e)}")
