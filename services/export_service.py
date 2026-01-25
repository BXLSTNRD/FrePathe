"""
Fré Pathé v1.8.0 - Export Service
Handles video export with FFmpeg and img2vid AI.
"""
import subprocess
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .config import PATH_MANAGER, DATA
from .project_service import (
    sanitize_filename,
    get_project_video_dir,
    download_image_locally,
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

def resolve_image_path(img_url: str, state: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """
    v1.8.5: Resolve render URL to file path using PATH_MANAGER.
    Now accepts state for migrated project path resolution.
    """
    if img_url.startswith("/"):
        # URL path - convert using PATH_MANAGER with state for project folder lookup
        img_path = PATH_MANAGER.from_url(img_url, state)
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


# ========= Img2Vid Export =========

def export_video_with_img2vid(
    state: Dict[str, Any],
    project_id: str,
    video_model: Optional[str] = None,
    fps: int = 30,
    resolution: str = "1920x1080"
) -> Dict[str, Any]:
    """
    Export storyboard using img2vid AI instead of static stills.
    
    Generates video clips for each shot using img2vid, then concatenates with audio.
    
    Args:
        state: Project state
        project_id: Project ID
        video_model: Video model to use (None = use project setting)
        fps: Frames per second (for concat)
        resolution: Output resolution
    
    Returns:
        Dict with video_url, shots_exported, duration_sec, generation_time
    """
    from .video_service import generate_shot_video, DEFAULT_VIDEO_MODEL
    
    if not check_ffmpeg():
        raise HTTPException(500, "FFmpeg not found. Install FFmpeg and add to PATH.")
    
    shots = state.get("storyboard", {}).get("shots", [])
    
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
    
    # Get video model
    if not video_model:
        video_model = state.get("project", {}).get("video_model", DEFAULT_VIDEO_MODEL)
        if video_model == "none":
            raise HTTPException(400, "No video model selected. Please select a video model in project settings.")
    
    # Setup directories
    video_dir = get_project_video_dir(state)
    temp_dir = video_dir / "temp_img2vid"
    temp_dir.mkdir(exist_ok=True)
    
    # Output path
    project_title = sanitize_filename(state.get("project", {}).get("title", "video"), 30)
    output_path = video_dir / f"{project_title}_img2vid_export.mp4"
    
    try:
        # Step 1: Generate video for each shot using img2vid (v1.8.2: async batch)
        video_clips = []
        skipped = []
        total_shots = len(rendered_shots)
        generation_start = time.time()
        
        print(f"[IMG2VID] Processing {total_shots} shots with {video_model} (concurrency=8)...")
        update_export_status(project_id, "processing", 0, total_shots, f"Generating videos with {video_model}...")
        
        # Generate all videos concurrently
        from .video_service import generate_videos_for_shots
        import asyncio
        
        shot_ids_to_generate = [s.get("shot_id") for s in rendered_shots if not s.get("render", {}).get("video", {}).get("video_url")]
        
        if shot_ids_to_generate:
            print(f"[IMG2VID] Generating {len(shot_ids_to_generate)} new videos...")
            batch_results = asyncio.run(generate_videos_for_shots(state, shot_ids_to_generate, video_model))
            print(f"[IMG2VID] Batch complete: {batch_results['success']} success, {batch_results['failed']} failed, {batch_results['skipped']} skipped")
        
        # Now collect all video clips
        for i, shot in enumerate(rendered_shots):
            shot_id = shot.get("shot_id", f"shot_{i}")
            
            try:
                # All shots should now have video (either existing or just generated)
                video_url = shot.get("render", {}).get("video", {}).get("video_url")
                if not video_url:
                    raise Exception(f"No video URL for {shot_id}")
                
                print(f"[IMG2VID] Collecting video for {shot_id}")
                
                # Resolve to local path - handle both /files/ URLs and absolute paths
                if video_url.startswith("/files/") or video_url.startswith("/renders/"):
                    # v1.8.5: Pass state for migrated project path resolution
                    video_path = PATH_MANAGER.from_url(video_url, state)
                elif Path(video_url).is_absolute():
                    video_path = Path(video_url)
                else:
                    # Relative path - resolve from project dir
                    video_path = get_project_video_dir(project_id) / video_url
                
                if not video_path.exists():
                    raise Exception(f"Video file not found: {video_path}")
                
                duration = float(shot.get("end", 0)) - float(shot.get("start", 0))
                
                video_clips.append({
                    "path": video_path,
                    "shot": shot,
                    "duration": duration,
                    "seq_id": shot.get("sequence_id", ""),
                })
                
                print(f"[IMG2VID] Processed {i+1}/{total_shots}: {shot_id}")
                update_export_status(project_id, "processing", i+1, total_shots, f"Generated video {i+1}/{total_shots}: {shot_id}")
                
            except Exception as e:
                print(f"[IMG2VID] Failed {shot_id}: {str(e)}")
                skipped.append(shot_id)
        
        generation_time = time.time() - generation_start
        print(f"[IMG2VID] Generated {len(video_clips)} videos in {generation_time:.1f}s")
        
        if not video_clips:
            update_export_status(project_id, "error", 0, 0, "No video clips generated")
            raise HTTPException(500, "No video clips generated")
        
        # Step 2: Create concat file
        total_duration = sum(c["duration"] for c in video_clips)
        print(f"[IMG2VID] Concatenating {len(video_clips)} clips (total {total_duration:.1f}s)...")
        update_export_status(project_id, "processing", total_shots, total_shots, f"Concatenating {len(video_clips)} video clips...")
        
        # v1.8.7: Trim/speed-adjust clips to match storyboard duration for audio sync
        # TRIM-FIRST: If model outputs 5s but target is 3.2s, TRIM don't speed up (preserves natural motion)
        # SPEED-UP: Only if trim failed or actual < target (rare)
        adjusted_clips = []
        for i, clip in enumerate(video_clips):
            video_data = clip["shot"].get("render", {}).get("video", {})
            actual_dur = float(video_data.get("duration", 0) or 0)
            target_dur = float(video_data.get("target_duration") or clip["duration"] or 0)
            
            # Adjust if durations don't match (tolerance 0.1s)
            if actual_dur > 0 and target_dur > 0 and abs(actual_dur - target_dur) > 0.1:
                
                # CASE A: Model output LONGER than target -> TRIM (no speed change, natural motion)
                if actual_dur > target_dur:
                    trimmed_path = temp_dir / f"trimmed_{i:03d}.mp4"
                    trim_cmd = [
                        "ffmpeg", "-y",
                        "-i", str(clip["path"]),
                        "-t", f"{target_dur:.3f}",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-an",  # No audio in individual clips
                        str(trimmed_path)
                    ]
                    result = subprocess.run(trim_cmd, capture_output=True)
                    if result.returncode == 0:
                        print(f"[IMG2VID] {clip['shot'].get('shot_id')} trimmed: {actual_dur:.1f}s → {target_dur:.1f}s")
                        adjusted_clips.append(trimmed_path)
                        continue
                    else:
                        print(f"[WARN] Trim failed for {clip['shot'].get('shot_id')}, falling back to speed adjust")
                
                # CASE B: Model output SHORTER than target OR trim failed -> speed adjust
                speed_factor = actual_dur / target_dur  # >1 = speedup, <1 = slowdown
                adjusted_path = temp_dir / f"adjusted_{i:03d}.mp4"
                
                # Use setpts for video speed
                speed_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(clip["path"]),
                    "-filter:v", f"setpts=PTS/{speed_factor}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-an",  # No audio in individual clips
                    str(adjusted_path)
                ]
                result = subprocess.run(speed_cmd, capture_output=True)
                if result.returncode == 0:
                    action = "sped up" if speed_factor > 1 else "slowed down"
                    print(f"[IMG2VID] {clip['shot'].get('shot_id')} {action} {speed_factor:.2f}x: {actual_dur:.1f}s → {target_dur:.1f}s")
                    adjusted_clips.append(adjusted_path)
                else:
                    print(f"[WARN] Speed adjust failed for {clip['shot'].get('shot_id')}, using original")
                    adjusted_clips.append(clip["path"])
            else:
                adjusted_clips.append(clip["path"])
        
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for clip_path in adjusted_clips:
                clip_path_str = str(clip_path).replace("\\", "/")
                f.write(f"file '{clip_path_str}'\n")
        
        # Step 3: Concat videos and add/mix audio
        success = concat_clips_with_audio(
            concat_file=concat_file,
            audio_path=Path(audio_path),
            output_path=output_path
        )
        
        if not success:
            update_export_status(project_id, "error", 0, 0, "FFmpeg concat failed")
            raise HTTPException(500, "FFmpeg concat failed")
        
        # Calculate scene transitions
        scene_transitions = sum(
            1 for i in range(1, len(video_clips)) 
            if video_clips[i-1]["seq_id"] != video_clips[i]["seq_id"]
        )
        
        # Cleanup temp files
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
            f"Img2Vid export complete: {len(video_clips)} clips, {total_duration:.1f}s"
        )
        
        return {
            "video_url": video_url,
            "shots_exported": len(video_clips),
            "duration_sec": total_duration,
            "scene_transitions": scene_transitions,
            "skipped_shots": skipped,
            "generation_time": generation_time,
            "video_model": video_model,
        }
        
    except subprocess.CalledProcessError as e:
        update_export_status(project_id, "error", 0, 0, f"FFmpeg error: {str(e)[:100]}")
        raise HTTPException(500, f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        update_export_status(project_id, "error", 0, 0, f"Export failed: {str(e)[:100]}")
        raise HTTPException(500, f"Export failed: {str(e)}")
