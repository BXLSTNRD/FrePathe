"""
Fré Pathé v1.7 - Cast Service
Handles cast member CRUD, character refs, and wardrobe generation.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import clamp


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


# ========= Style Lock =========

def check_style_lock(state: Dict[str, Any]) -> bool:
    """Check if style is locked."""
    return state.get("project", {}).get("style_locked", False)


def get_style_lock_image(state: Dict[str, Any]) -> Optional[str]:
    """Get the style lock image URL."""
    return state.get("project", {}).get("style_lock_image")


def set_style_lock(
    state: Dict[str, Any],
    locked: bool,
    image_url: Optional[str] = None
) -> None:
    """Set or clear style lock."""
    state["project"]["style_locked"] = locked
    state["project"]["style_lock_image"] = image_url if locked else None


def clear_style_lock(state: Dict[str, Any]) -> None:
    """Clear style lock to allow re-rendering with different style."""
    state["project"]["style_locked"] = False
    state["project"]["style_lock_image"] = None


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
