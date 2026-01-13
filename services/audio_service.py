"""
Fré Pathé v1.7 - Audio Service
Handles audio DNA extraction, duration, BPM, Whisper transcription, and beat grid.
"""
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    FAL_AUDIO,
    FAL_WHISPER,
    fal_headers,
    track_cost
)


# ========= Audio Duration Functions =========

def get_audio_duration_librosa(file_path: str) -> Optional[float]:
    """Get accurate audio duration using librosa."""
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
    """Get audio duration with fallbacks."""
    # Try librosa first (most accurate)
    dur = get_audio_duration_librosa(file_path)
    if dur:
        return dur
    # Fallback to mutagen
    dur = get_audio_duration_mutagen(file_path)
    if dur:
        return dur
    return None


# ========= BPM Detection =========

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


# ========= Beat Grid =========

def build_beat_grid(duration_sec: float, bpm: float) -> Dict[str, Any]:
    """
    Build a beat grid for shot timing synchronization.
    Returns beats, bars, and downbeats lists.
    """
    try:
        duration_sec = float(duration_sec) if duration_sec else 0.0
        bpm = float(bpm) if bpm else 120.0
    except (TypeError, ValueError):
        duration_sec = 0.0
        bpm = 120.0
    
    if duration_sec <= 0 or bpm <= 0:
        return {"beats": [], "bars": [], "downbeats": [], "total_beats": 0, "total_bars": 0}
    
    beat_duration = 60.0 / bpm  # Seconds per beat
    beats_per_bar = 4  # Assume 4/4 time
    
    beats = []
    bars = []
    downbeats = []
    
    t = 0.0
    beat_count = 0
    while t < duration_sec:
        beats.append(round(t, 3))
        
        # Is this a downbeat (first beat of a bar)?
        if beat_count % beats_per_bar == 0:
            bars.append(round(t, 3))
            downbeats.append(round(t, 3))
        
        t += beat_duration
        beat_count += 1
    
    return {
        "beats": beats,
        "bars": bars,
        "downbeats": downbeats,
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


# ========= Audio DNA Extraction =========

def _extract_json_from_fal_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    v1.7.0: FAL audio-understanding returns JSON inside an 'output' string
    with markdown code blocks. Extract the actual data.
    """
    import json as json_module
    import re
    
    # If raw already has the expected keys, return as-is
    if raw.get("bpm") or raw.get("structure") or raw.get("lyrics"):
        return raw
    
    # Check for 'output' string containing JSON
    output = raw.get("output", "")
    if not output or not isinstance(output, str):
        return raw
    
    # Remove markdown code block markers
    # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
    cleaned = output.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ```
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        # Remove closing ```
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    
    # Try to parse as JSON
    try:
        parsed = json_module.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json_module.JSONDecodeError as e:
        print(f"[WARN] Failed to parse FAL output JSON: {e}")
    
    return raw


def normalize_audio_understanding(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize FAL audio-understanding response into standardized audio DNA.
    v1.7.0: Handle FAL's output format (JSON inside markdown code block)
    """
    # v1.7.0: Extract JSON from FAL's output string format
    data = _extract_json_from_fal_output(raw)
    
    # Extract basic metadata
    meta = {
        "duration_sec": data.get("duration_sec") or data.get("duration"),
        "bpm": data.get("bpm") or data.get("tempo") or 120,
        "key": data.get("key") or data.get("musical_key") or "unknown",
        "energy": data.get("energy") or 0.5,
        "genre": data.get("genre") or "unknown",
    }
    
    # v1.7.0: Extract style (FAL returns as list)
    style = data.get("style") or []
    if isinstance(style, list):
        style = ", ".join(style) if style else "unknown"
    
    # Extract mood/emotion
    mood = data.get("mood") or data.get("emotion") or data.get("atmosphere") or "energetic"
    if isinstance(mood, list):
        mood = mood[0] if mood else "energetic"
    
    # v1.7.0: Extract structure sections (FAL format)
    sections = data.get("structure") or data.get("sections") or []
    # Normalize section format
    normalized_sections = []
    for sec in sections:
        if isinstance(sec, dict):
            normalized_sections.append({
                "type": sec.get("type") or sec.get("label") or "verse",
                "start": sec.get("start") or 0,
                "end": sec.get("end") or 0,
            })
    sections = normalized_sections if normalized_sections else sections
    
    # v1.7.0: Extract dynamics (FAL format: list of {start, end, energy})
    dynamics = data.get("dynamics") or []
    if dynamics and isinstance(dynamics, list):
        # Calculate average energy or get dominant dynamic
        energies = [d.get("energy", 0.5) for d in dynamics if isinstance(d, dict)]
        if energies:
            meta["energy"] = sum(energies) / len(energies)
            meta["energy_curve"] = dynamics
    
    # v1.7.0: Extract vocal delivery
    vocal_delivery = data.get("vocal_delivery") or {}
    delivery_str = "unknown"
    if isinstance(vocal_delivery, dict):
        pace = vocal_delivery.get("pace", "")
        tone = vocal_delivery.get("tone", [])
        if isinstance(tone, list):
            tone = ", ".join(tone)
        delivery_str = f"{pace} - {tone}" if pace or tone else "unknown"
    elif isinstance(vocal_delivery, str):
        delivery_str = vocal_delivery
    
    # v1.7.0: Extract story arc
    story_arc = data.get("story_arc") or {}
    story_str = "unknown"
    if isinstance(story_arc, dict):
        theme = story_arc.get("theme", "")
        conflict = story_arc.get("conflict", "")
        story_str = theme or conflict or "unknown"
    elif isinstance(story_arc, str):
        story_str = story_arc
    
    # Extract lyrics (FAL format: list of {start, text})
    lyrics = data.get("lyrics") or []
    if isinstance(lyrics, str):
        lines = [l.strip() for l in lyrics.split("\n") if l.strip()]
        lyrics = [{"text": l} for l in lines]
    elif isinstance(lyrics, list):
        # Normalize to have 'text' key
        normalized_lyrics = []
        for item in lyrics:
            if isinstance(item, str):
                normalized_lyrics.append({"text": item})
            elif isinstance(item, dict):
                normalized_lyrics.append({
                    "text": item.get("text", ""),
                    "start": item.get("start"),
                })
        lyrics = normalized_lyrics
    
    # Extract instruments
    instruments = data.get("instruments") or data.get("instrumentation") or []
    if isinstance(instruments, str):
        instruments = [i.strip() for i in instruments.split(",")]
    
    return {
        "meta": meta,
        "mood": mood,
        "style": style,
        "sections": sections,
        "dynamics": dynamics,
        "delivery": delivery_str,
        "story": story_str,
        "lyrics": lyrics,
        "instruments": instruments,
        "raw_response": raw,  # Keep original for debugging
    }


async def analyze_audio(
    file_path: Path,
    audio_url: str,
    prompt: str,
    state: Dict[str, Any],
    use_whisper: bool = False
) -> Dict[str, Any]:
    """
    Analyze audio file using FAL audio-understanding and optionally Whisper.
    Returns normalized audio DNA with beat grid.
    """
    # Get accurate duration using librosa/mutagen BEFORE fal.ai call
    local_duration = get_audio_duration(str(file_path))
    print(f"[INFO] Local audio duration: {local_duration}s")
    
    # Get accurate BPM using librosa beat tracking
    local_bpm = get_audio_bpm_librosa(str(file_path))
    if local_bpm:
        print(f"[INFO] Local BPM detection (librosa): {local_bpm}")
    else:
        print(f"[WARN] Local BPM detection failed, will use FAL")
    
    # Optionally use Whisper for better transcription
    whisper_transcript = None
    if use_whisper:
        print(f"[INFO] Using Whisper for enhanced transcription...")
        try:
            whisper_r = requests.post(
                FAL_WHISPER,
                headers=fal_headers(),
                json={
                    "audio_url": audio_url,
                    "task": "transcribe",
                    "language": "en",
                    "chunk_level": "segment",
                    "version": "3"
                },
                timeout=300
            )
            
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
    
    # Call FAL audio-understanding
    r = requests.post(
        FAL_AUDIO,
        headers=fal_headers(),
        json={"audio_url": audio_url, "prompt": prompt},
        timeout=300
    )
    
    # Track cost based on duration ($0.01 per 5 seconds)
    duration_for_cost = local_duration or 180  # Fallback to 3 min estimate
    audio_cost_units = max(1, int(duration_for_cost / 5))  # 5-second units
    track_cost("fal-ai/audio-understanding", audio_cost_units, state=state)
    
    if r.status_code >= 300:
        raise Exception(f"FAL audio-understanding failed: {r.status_code} - {r.text}")
    
    raw = r.json()
    audio_dna = normalize_audio_understanding(raw)
    
    # Enhance lyrics with Whisper transcript if available
    if whisper_transcript:
        audio_dna["whisper_transcript"] = whisper_transcript
        existing_lyrics = audio_dna.get("lyrics", [])
        if not existing_lyrics or len(existing_lyrics) < 3:
            lines = [l.strip() for l in whisper_transcript.split("\n") if l.strip()]
            if not lines:
                lines = [s.strip() + "." for s in whisper_transcript.split(".") if s.strip()]
            audio_dna["lyrics"] = [{"text": l} for l in lines[:50]]
            audio_dna["lyrics_source"] = "whisper"
        else:
            audio_dna["lyrics_source"] = "audio-understanding"
    
    # Use local duration (librosa) if available
    if local_duration:
        if not audio_dna.get("meta"):
            audio_dna["meta"] = {}
        audio_dna["meta"]["duration_sec"] = local_duration
        audio_dna["meta"]["duration_source"] = "librosa"
    
    # Use librosa BPM if available (much more accurate than FAL)
    if local_bpm:
        if not audio_dna.get("meta"):
            audio_dna["meta"] = {}
        fal_bpm = audio_dna["meta"].get("bpm", 120)
        audio_dna["meta"]["bpm"] = local_bpm
        audio_dna["meta"]["bpm_source"] = "librosa"
        audio_dna["meta"]["bpm_fal"] = fal_bpm
        print(f"[INFO] Using librosa BPM {local_bpm} (FAL detected: {fal_bpm})")
    
    # Calculate beat grid for shot timing sync
    duration = audio_dna.get("meta", {}).get("duration_sec", 0)
    bpm = audio_dna.get("meta", {}).get("bpm", 120)
    beat_grid = build_beat_grid(duration, bpm)
    audio_dna["beat_grid"] = beat_grid
    print(f"[INFO] Beat grid: {beat_grid.get('total_bars', 0)} bars, {beat_grid.get('total_beats', 0)} beats @ {bpm} BPM")
    
    return {
        "audio_dna": audio_dna,
        "local_duration": local_duration,
        "used_whisper": use_whisper,
        "whisper_transcript": whisper_transcript,
    }


def update_bpm(state: Dict[str, Any], new_bpm: int) -> Dict[str, Any]:
    """
    Manually update the BPM and recalculate beat grid.
    Returns updated audio_dna.
    """
    audio_dna = state.get("audio_dna")
    if not audio_dna:
        raise ValueError("No audio DNA found")
    
    if new_bpm < 40 or new_bpm > 240:
        raise ValueError("BPM must be between 40 and 240")
    
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
    
    return audio_dna
