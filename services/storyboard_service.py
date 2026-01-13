"""
Fré Pathé v1.7 - Storyboard Service
Handles sequences, shots, and timeline management.
"""
from typing import Any, Dict, List, Optional, Tuple

from .config import clamp
from .project_service import safe_float, normalize_structure_type


# ========= Target Calculations =========

def target_sequences_and_shots(duration_sec: Optional[float]) -> Tuple[int, int]:
    """
    Calculate target number of sequences and shots based on duration.
    Returns (sequence_count, target_shots).
    """
    duration = float(duration_sec) if duration_sec else 180.0
    
    # Roughly 10-20 seconds per sequence
    if duration < 60:
        seq_count = 3
    elif duration < 120:
        seq_count = 5
    elif duration < 180:
        seq_count = 7
    elif duration < 240:
        seq_count = 9
    else:
        seq_count = min(12, int(duration / 20))
    
    # Target 5-8 shots per sequence
    target_shots = seq_count * 6
    
    return (seq_count, target_shots)


# ========= Sequence Operations =========

def create_sequence(
    sequence_id: str,
    label: str,
    start: float,
    end: float,
    structure_type: str = "verse",
    energy: float = 0.5,
    cast: List[str] = None,
    description: str = "",
    arc_start: str = "",
    arc_end: str = "",
    lyrics_reference: str = "",
    start_frame_prompt: str = "",
    end_frame_prompt: str = ""
) -> Dict[str, Any]:
    """Create a new sequence object."""
    return {
        "sequence_id": sequence_id,
        "label": label or sequence_id,
        "start": safe_float(start, 0.0),
        "end": safe_float(end, 0.0),
        "structure_type": normalize_structure_type(structure_type),
        "energy": clamp(safe_float(energy, 0.5), 0.0, 1.0),
        "cast": cast or [],
        "description": description.strip(),
        "arc_start": arc_start.strip(),
        "arc_end": arc_end.strip(),
        "lyrics_reference": lyrics_reference.strip(),
        "start_frame_prompt": start_frame_prompt.strip(),
        "end_frame_prompt": end_frame_prompt.strip(),
    }


def find_sequence(state: Dict[str, Any], sequence_id: str) -> Optional[Dict[str, Any]]:
    """Find a sequence by ID."""
    for seq in state.get("storyboard", {}).get("sequences", []):
        if seq.get("sequence_id") == sequence_id:
            return seq
    return None


def get_sequences_for_shot(
    state: Dict[str, Any], 
    shot: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Get the sequence that contains a shot."""
    seq_id = shot.get("sequence_id")
    if seq_id:
        return find_sequence(state, seq_id)
    return None


def update_sequence(
    sequence: Dict[str, Any],
    label: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    structure_type: Optional[str] = None,
    energy: Optional[float] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Update sequence properties."""
    if label is not None:
        sequence["label"] = label.strip()
    if start is not None:
        sequence["start"] = safe_float(start, 0.0)
    if end is not None:
        sequence["end"] = safe_float(end, 0.0)
    if structure_type is not None:
        sequence["structure_type"] = normalize_structure_type(structure_type)
    if energy is not None:
        sequence["energy"] = clamp(safe_float(energy, 0.5), 0.0, 1.0)
    if description is not None:
        sequence["description"] = description.strip()
    return sequence


# ========= Shot Operations =========

def create_shot(
    shot_id: str,
    sequence_id: str,
    start: float,
    end: float,
    structure_type: str = "verse",
    energy: float = 0.5,
    cast: List[str] = None,
    wardrobe: Dict[str, str] = None,
    intent: str = "",
    camera_language: str = "",
    environment: str = "",
    symbolic_elements: List[str] = None,
    prompt_base: str = ""
) -> Dict[str, Any]:
    """Create a new shot object."""
    return {
        "shot_id": shot_id,
        "sequence_id": sequence_id,
        "start": safe_float(start, 0.0),
        "end": safe_float(end, 0.0),
        "structure_type": normalize_structure_type(structure_type),
        "energy": clamp(safe_float(energy, 0.5), 0.0, 1.0),
        "cast": cast or [],
        "wardrobe": wardrobe or {},
        "intent": intent.strip(),
        "camera_language": camera_language.strip(),
        "environment": environment.strip(),
        "symbolic_elements": symbolic_elements or [],
        "prompt_base": prompt_base.strip(),
        "render": {
            "status": "none",
            "image_url": None,
            "model": None,
            "ref_images_used": 0,
            "error": None,
        },
    }


def find_shot(state: Dict[str, Any], shot_id: str) -> Optional[Dict[str, Any]]:
    """Find a shot by ID."""
    for shot in state.get("storyboard", {}).get("shots", []):
        if shot.get("shot_id") == shot_id:
            return shot
    return None


def update_shot(
    shot: Dict[str, Any],
    start: Optional[float] = None,
    end: Optional[float] = None,
    prompt_base: Optional[str] = None,
    cast: Optional[List[str]] = None,
    wardrobe: Optional[Dict[str, str]] = None,
    intent: Optional[str] = None,
    camera_language: Optional[str] = None,
    environment: Optional[str] = None
) -> Dict[str, Any]:
    """Update shot properties."""
    if start is not None:
        shot["start"] = safe_float(start, 0.0)
    if end is not None:
        shot["end"] = safe_float(end, 0.0)
    if prompt_base is not None:
        shot["prompt_base"] = prompt_base.strip()
    if cast is not None:
        shot["cast"] = cast
    if wardrobe is not None:
        shot["wardrobe"] = wardrobe
    if intent is not None:
        shot["intent"] = intent.strip()
    if camera_language is not None:
        shot["camera_language"] = camera_language.strip()
    if environment is not None:
        shot["environment"] = environment.strip()
    return shot


def delete_shot(state: Dict[str, Any], shot_id: str) -> bool:
    """Delete a shot by ID. Returns True if found and deleted."""
    shots = state.get("storyboard", {}).get("shots", [])
    original_len = len(shots)
    state["storyboard"]["shots"] = [s for s in shots if s.get("shot_id") != shot_id]
    return len(state["storyboard"]["shots"]) < original_len


def get_shots_for_sequence(
    state: Dict[str, Any], 
    sequence_id: str
) -> List[Dict[str, Any]]:
    """Get all shots belonging to a sequence."""
    shots = state.get("storyboard", {}).get("shots", [])
    return [s for s in shots if s.get("sequence_id") == sequence_id]


# ========= Timeline Repair =========

def repair_timeline(
    state: Dict[str, Any], 
    actual_duration: float
) -> Dict[str, Any]:
    """
    Fix sequences and shots that exceed audio duration.
    Returns dict with repair statistics.
    """
    sequences = state.get("storyboard", {}).get("sequences", [])
    shots = state.get("storyboard", {}).get("shots", [])
    
    repaired_seqs = []
    removed_seqs = []
    capped_seqs = []
    
    for seq in sequences:
        seq_id = seq.get("sequence_id", "unknown")
        start = float(seq.get("start", 0))
        end = float(seq.get("end", 0))
        
        # Skip sequences that start after audio ends
        if start >= actual_duration:
            removed_seqs.append(seq_id)
            continue
        
        # Cap end time to audio duration
        if end > actual_duration:
            seq["end"] = actual_duration
            capped_seqs.append(seq_id)
        
        # Fix start >= end
        if seq["start"] >= seq["end"]:
            removed_seqs.append(seq_id)
            continue
        
        repaired_seqs.append(seq)
    
    # Repair shots
    valid_seq_ids = {s["sequence_id"] for s in repaired_seqs}
    repaired_shots = []
    removed_shots = []
    
    for shot in shots:
        shot_id = shot.get("shot_id", "unknown")
        shot_start = float(shot.get("start", 0))
        shot_end = float(shot.get("end", 0))
        
        # Skip shots from removed sequences
        if shot.get("sequence_id") not in valid_seq_ids:
            removed_shots.append(shot_id)
            continue
        
        # Skip shots that start after audio ends
        if shot_start >= actual_duration:
            removed_shots.append(shot_id)
            continue
        
        # Cap shot end time
        if shot_end > actual_duration:
            shot["end"] = actual_duration
        
        # Skip invalid shots
        if shot["start"] >= shot["end"]:
            removed_shots.append(shot_id)
            continue
        
        repaired_shots.append(shot)
    
    state["storyboard"]["sequences"] = repaired_seqs
    state["storyboard"]["shots"] = repaired_shots
    
    return {
        "sequences_removed": removed_seqs,
        "sequences_capped": capped_seqs,
        "sequences_kept": len(repaired_seqs),
        "shots_removed": removed_shots,
        "shots_kept": len(repaired_shots),
    }


# ========= Shot Validation =========

def validate_shots_coverage(
    state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate that shots cover sequences without gaps or overlaps.
    Returns validation report.
    """
    sequences = state.get("storyboard", {}).get("sequences", [])
    shots = state.get("storyboard", {}).get("shots", [])
    
    issues = []
    
    for seq in sequences:
        seq_id = seq.get("sequence_id")
        seq_start = seq.get("start", 0)
        seq_end = seq.get("end", 0)
        
        seq_shots = sorted(
            [s for s in shots if s.get("sequence_id") == seq_id],
            key=lambda x: x.get("start", 0)
        )
        
        if not seq_shots:
            issues.append(f"Sequence {seq_id} has no shots")
            continue
        
        # Check first shot starts at sequence start
        if abs(seq_shots[0].get("start", 0) - seq_start) > 0.1:
            issues.append(f"Gap at start of {seq_id}")
        
        # Check last shot ends at sequence end
        if abs(seq_shots[-1].get("end", 0) - seq_end) > 0.1:
            issues.append(f"Gap at end of {seq_id}")
        
        # Check for gaps between shots
        for i in range(len(seq_shots) - 1):
            current_end = seq_shots[i].get("end", 0)
            next_start = seq_shots[i + 1].get("start", 0)
            if abs(next_start - current_end) > 0.1:
                issues.append(f"Gap between {seq_shots[i]['shot_id']} and {seq_shots[i+1]['shot_id']}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "sequence_count": len(sequences),
        "shot_count": len(shots),
    }


# ========= Cast Coverage =========

def get_cast_coverage(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Calculate how much screen time each cast member has.
    Returns dict of cast_id -> {total_time, shot_count, percentage}
    """
    shots = state.get("storyboard", {}).get("shots", [])
    cast_list = state.get("cast", [])
    
    total_duration = sum(
        max(0, s.get("end", 0) - s.get("start", 0)) 
        for s in shots
    )
    
    coverage = {}
    for c in cast_list:
        cast_id = c.get("cast_id")
        if not cast_id:
            continue
        
        cast_shots = [s for s in shots if cast_id in s.get("cast", [])]
        cast_time = sum(
            max(0, s.get("end", 0) - s.get("start", 0)) 
            for s in cast_shots
        )
        
        coverage[cast_id] = {
            "name": c.get("name", cast_id),
            "role": c.get("role", "extra"),
            "total_time": round(cast_time, 2),
            "shot_count": len(cast_shots),
            "percentage": round(cast_time / total_duration * 100, 1) if total_duration > 0 else 0,
        }
    
    return coverage
