"""
Fré Pathé v1.8.8 - Cast Service
Handles cast member CRUD, character refs, and wardrobe generation.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import clamp


# ========= Cast Impact/Usage =========

def get_cast_usage_string(role: str, impact: float, is_primary_lead: bool = False) -> str:
    """
    v1.8.9: Convert role + impact to LLM usage instruction.
    Role CONSTRAINS maximum presence, impact fine-tunes within that.
    
    - LEAD: can be HIGH (70%+) or MEDIUM (40-69%)
    - SUPPORTING: can be MEDIUM (40%+) or LOW (<40%)
    - EXTRA: always LOW regardless of impact slider
    """
    role_lower = role.lower()
    
    if role_lower == "extra":
        # Extras are ALWAYS low presence - but impact slider scales within that
        if impact >= 0.5:
            return f"LOW PRESENCE ({int(impact*100)}%) - background/functional role, 5-6 shots, must have PURPOSE (bartender, taxi driver, etc.)"
        else:
            return f"MINIMAL PRESENCE ({int(impact*100)}%) - background only, 1-2 shots MAX, must have PURPOSE"
    
    elif role_lower == "supporting":
        # Supporting can be medium or low, never high
        if impact >= 0.5:
            return f"MEDIUM PRESENCE ({int(impact*100)}%) - appears in ~half the shots, interacts with lead"
        else:
            return f"LOW PRESENCE ({int(impact*100)}%) - occasional appearances, supports the narrative"
    
    else:  # lead
        if is_primary_lead:
            return f"PRIMARY PROTAGONIST ({int(impact*100)}%) - THE main character, appears in 80%+ of shots"
        elif impact >= 0.7:
            return f"CO-LEAD ({int(impact*100)}%) - major character, appears in most shots (60%+)"
        else:
            return f"SECONDARY LEAD ({int(impact*100)}%) - important but not primary focus"


def get_cast_usage_string_sequences(role: str, impact: float, is_primary_lead: bool = False) -> str:
    """
    v1.8.9: Usage string for sequence building. Same logic as shots but sequence-appropriate wording.
    """
    role_lower = role.lower()
    
    if role_lower == "extra":
        if impact >= 0.5:
            return f"BACKGROUND ({int(impact*100)}%) - appears in 2-3 sequences, functional role with PURPOSE"
        else:
            return f"MINIMAL ({int(impact*100)}%) - appears in 1 sequence only, must have narrative PURPOSE"
    
    elif role_lower == "supporting":
        if impact >= 0.5:
            return f"RECURRING ({int(impact*100)}%) - appears in ~half the sequences, supports lead"
        else:
            return f"OCCASIONAL ({int(impact*100)}%) - few key appearances, supports narrative"
    
    else:  # lead
        if is_primary_lead:
            return f"PROTAGONIST ({int(impact*100)}%) - THE main character, story follows them"
        elif impact >= 0.7:
            return f"CO-PROTAGONIST ({int(impact*100)}%) - major character arc, most sequences"
        else:
            return f"SECONDARY LEAD ({int(impact*100)}%) - important but not the primary focus"


def build_sorted_cast_info(state: Dict[str, Any], for_sequences: bool = False) -> List[Dict[str, Any]]:
    """
    v1.8.9: Build cast info list sorted by role hierarchy and impact.
    Centralizes the cast sorting + info building logic.
    Identifies PRIMARY LEAD (first lead with highest impact) for protagonist clarity.
    
    Args:
        state: Project state
        for_sequences: If True, use sequence-appropriate usage strings
    
    Returns:
        List of cast info dicts ready for LLM payload
    """
    role_priority = {"lead": 0, "supporting": 1, "extra": 2}
    cast_sorted = sorted(
        state.get("cast", []),
        key=lambda c: (role_priority.get(c.get("role", "extra").lower(), 2), -c.get("impact", 0.5))
    )
    
    # Find the primary lead (first lead = highest impact lead after sorting)
    primary_lead_id = None
    for c in cast_sorted:
        if c.get("role", "").lower() == "lead":
            primary_lead_id = c["cast_id"]
            break  # First lead in sorted list is primary
    
    cast_info = []
    for c in cast_sorted:
        role = c.get("role", "extra")
        impact = c.get("impact", 0.1 if role == "extra" else (0.5 if role == "supporting" else 0.7))
        is_primary = (c["cast_id"] == primary_lead_id)
        
        if for_sequences:
            usage = get_cast_usage_string_sequences(role, impact, is_primary)
        else:
            usage = get_cast_usage_string(role, impact, is_primary)
        
        cast_info.append({
            "cast_id": c["cast_id"],
            "name": c.get("name", ""),
            "role": role.upper() if not for_sequences else role,
            "impact": f"{int(impact*100)}%",
            "wardrobe": c.get("prompt_extra", ""),
            "usage": usage,
        })
    
    return cast_info


# ========= Cast Lookup =========

def find_cast(state: Dict[str, Any], cast_id: str) -> Optional[Dict[str, Any]]:
    """Find a cast member by ID."""
    for c in state.get("cast", []):
        if c.get("cast_id") == cast_id:
            return c
    return None


def cast_ref_urls(cast: Dict[str, Any]) -> List[str]:
    """Extract reference image URLs from a cast member."""
    urls = []
    for ref in cast.get("reference_images", []):
        # Prefer fal_url (already uploaded), fallback to regular url
        url = ref.get("fal_url") or ref.get("url")
        if url:
            urls.append(url)
    return urls


def get_identity_url(state: Dict[str, Any], cast_id: str) -> Optional[str]:
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


def get_cast_refs_for_shot(state: Dict[str, Any], shot: Dict[str, Any]) -> List[str]:
    """
    Get all cast reference URLs relevant to a shot.
    Returns ref_a URLs for each cast member in the shot.
    """
    cast_ids = shot.get("cast", [])
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    refs = []
    
    for cid in cast_ids:
        char = char_refs.get(cid, {})
        ref_a = char.get("ref_a")
        if ref_a:
            refs.append(ref_a)
    
    return refs


def get_lead_cast_ref(state: Dict[str, Any], shot: Dict[str, Any]) -> Optional[str]:
    """Get the primary cast ref_a for a shot (lead character)."""
    cast_ids = shot.get("cast", [])
    if not cast_ids:
        return None
    
    lead_id = cast_ids[0]
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    return char_refs.get(lead_id, {}).get("ref_a")


# ========= Cast Visual DNA =========

def create_cast_visual_dna(
    cast_id: str,
    name: str,
    role: str,
    local_url: str,
    fal_url: str
) -> Dict[str, Any]:
    """Create a new cast visual DNA entry."""
    return {
        "cast_id": cast_id,
        "name": name,
        "role": role,
        "text_tokens": ["consistent face", "consistent outfit"],
        "reference_images": [
            {
                "url": local_url,
                "fal_url": fal_url,
                "role": "primary_face",
                "notes": ""
            }
        ],
        "conditioning": {
            "identity": {"enabled": True, "strength": 0.75},
            "lora": {"enabled": False, "lora_id": None, "strength": 0.8},
        },
        "impact": 0.7,  # Default impact
        "prompt_extra": "",  # Extra prompt override
    }


def update_cast_properties(
    cast: Dict[str, Any],
    name: Optional[str] = None,
    role: Optional[str] = None,
    impact: Optional[float] = None,
    prompt_extra: Optional[str] = None
) -> Dict[str, Any]:
    """Update allowed cast member properties."""
    if name is not None:
        cast["name"] = str(name).strip()
    if role is not None:
        cast["role"] = str(role).strip().lower()
    if impact is not None:
        cast["impact"] = clamp(float(impact), 0.0, 1.0)
    if prompt_extra is not None:
        cast["prompt_extra"] = str(prompt_extra).strip()
    return cast


def update_cast_lora(
    cast: Dict[str, Any],
    lora_id: Optional[str],
    strength: float = 0.8
) -> Dict[str, Any]:
    """Update cast LoRA settings."""
    cond = cast.get("conditioning") or {}
    lora = cond.get("lora") or {"enabled": False, "lora_id": None, "strength": 0.8}
    
    if lora_id:
        lora.update({
            "enabled": True,
            "lora_id": lora_id,
            "strength": clamp(strength, 0.0, 2.0)
        })
    else:
        lora.update({
            "enabled": False,
            "lora_id": None,
            "strength": clamp(strength, 0.0, 2.0)
        })
    
    cond["lora"] = lora
    cast["conditioning"] = cond
    return cast


def delete_cast_from_state(state: Dict[str, Any], cast_id: str) -> bool:
    """
    Remove a cast member from state.
    Returns True if found and deleted.
    """
    cast_list = state.get("cast", [])
    original_len = len(cast_list)
    state["cast"] = [c for c in cast_list if c.get("cast_id") != cast_id]
    
    if len(state["cast"]) == original_len:
        return False
    
    # Also remove from character_refs
    char_refs = state.get("cast_matrix", {}).get("character_refs", {})
    if cast_id in char_refs:
        del char_refs[cast_id]
    
    return True


# ========= Character Refs =========

def set_character_refs(
    state: Dict[str, Any],
    cast_id: str,
    ref_a: Optional[str] = None,
    ref_b: Optional[str] = None
) -> Dict[str, Any]:
    """Set character ref_a and/or ref_b for a cast member."""
    char_refs = state.setdefault("cast_matrix", {}).setdefault("character_refs", {})
    
    if cast_id not in char_refs:
        char_refs[cast_id] = {}
    
    if ref_a is not None:
        char_refs[cast_id]["ref_a"] = ref_a
    if ref_b is not None:
        char_refs[cast_id]["ref_b"] = ref_b
    
    return char_refs[cast_id]


def get_character_refs(state: Dict[str, Any], cast_id: str) -> Dict[str, Any]:
    """Get character refs for a cast member."""
    return state.get("cast_matrix", {}).get("character_refs", {}).get(cast_id, {})


# ========= Cast Prompts =========

def build_cast_prompt_tokens(cast: Dict[str, Any]) -> List[str]:
    """Build prompt tokens for a cast member."""
    tokens = cast.get("text_tokens", []).copy()
    extra = cast.get("prompt_extra", "").strip()
    if extra:
        tokens.insert(0, extra)
    return tokens


def build_ref_prompt(
    cast: Dict[str, Any],
    style_tokens: List[str],
    ref_type: str = "a"
) -> str:
    """Build prompt for generating ref_a or ref_b."""
    base_style = ", ".join(style_tokens + ["no text", "no watermark", "clean background"])
    negatives = "no props, no objects, no mug, no cup, no drink, no phone, no bag, no accessories, clean hands, no typography, no title, no caption, no overlay, no frame, no border, no logo"
    
    extra = cast.get("prompt_extra", "").strip()
    extra_prefix = f"{extra}, " if extra else ""
    
    if ref_type == "a":
        return f"{base_style}, {extra_prefix}full body, standing, three-quarter view, slight angle, neutral pose, clean background, consistent identity, {negatives}"
    else:
        return f"{base_style}, {extra_prefix}portrait close-up, head and shoulders, three-quarter view, slight angle from side, neutral expression, clean background, consistent identity, {negatives}"


# ========= Scenes =========

def get_scene_by_id(state: Dict[str, Any], scene_id: str) -> Optional[Dict[str, Any]]:
    """Find a scene by ID."""
    scenes = state.get("cast_matrix", {}).get("scenes", [])
    for scene in scenes:
        if scene.get("scene_id") == scene_id:
            return scene
    return None


def get_scene_for_shot(state: Dict[str, Any], shot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get the scene associated with a shot."""
    scene_id = shot.get("scene_id")
    if not scene_id:
        # Try to derive from sequence
        seq_id = shot.get("sequence_id")
        if seq_id:
            scene_id = f"scene_{seq_id.split('_')[-1]}" if seq_id.startswith("seq_") else None
    
    if scene_id:
        return get_scene_by_id(state, scene_id)
    return None


def get_scene_decor_refs(scene: Dict[str, Any]) -> List[str]:
    """Get decor reference URLs for a scene."""
    return scene.get("decor_refs", []) if scene else []


def get_scene_wardrobe(scene: Dict[str, Any]) -> str:
    """Get wardrobe description for a scene."""
    return scene.get("wardrobe", "") if scene else ""


def get_scene_wardrobe_ref(scene: Dict[str, Any]) -> Optional[str]:
    """Get wardrobe reference image for a scene."""
    return scene.get("wardrobe_ref") if scene else None
