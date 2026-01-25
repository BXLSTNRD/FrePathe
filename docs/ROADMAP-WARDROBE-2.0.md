# Wardrobe 2.0 - Roadmap

**Status:** Planned  
**Priority:** High (GOUD waard als het werkt)  
**Discovered:** 2026-01-25  
**Session:** Storyboard bug fixes → led to wardrobe hiaten discovery

---

## Problem Summary

Current wardrobe system has 5 critical hiaten discovered through visual testing:

| # | Problem | Visual Example |
|---|---------|----------------|
| 1 | Gender unknown → wrong clothes | Dokteur in pink renaissance dress 👗 |
| 2 | Wardrobe = scene-wide | Everyone becomes bompa in tweed 👴👴👴👴 |
| 3 | ref_a + wardrobe_ref = clones | 4 identical people at café tables |
| 4 | Extra with function role → no outfit | "Waiter" extra in casual black t-shirt |
| 5 | No base outfit fallback | Marc styled in scene 1, casual in scene 2-10 |

---

## Proposed Solutions

### 1. Gender-Aware Wardrobe Generation

**Current:**
```python
wardrobe = "elegant period costume"  # → LLM picks dress for male character
```

**Proposed:**
```python
# Cast member has gender field
cast = {
    "cast_id": "dokteur_01",
    "name": "Dokteur Dubois", 
    "gender": "male",  # NEW FIELD
    ...
}

# Wardrobe generation includes gender
wardrobe_prompt = f"{gender} {wardrobe_description}"  
# → "male elegant period costume" → suit, not dress
```

**Implementation:**
- Add `gender` field to cast schema (male/female/neutral)
- UI: dropdown in cast creation
- Pass gender to wardrobe LLM prompt
- Pass gender to image generation prompt

---

### 2. Per-Cast Wardrobe (not Scene-Wide)

**Current Schema:**
```python
scene = {
    "scene_id": "scene_01",
    "wardrobe": "vintage tweed outfit",  # EVERYONE gets this
    ...
}
```

**Proposed Schema:**
```python
scene = {
    "scene_id": "scene_01",
    "wardrobe": {
        "marc_01": "vintage tweed outfit, flat cap, leather satchel",
        "dokteur_01": "white lab coat, stethoscope",
        "ober_extra": "formal waiter uniform, bow tie"
    },
    ...
}
```

**Implementation:**
- Change `wardrobe` from string to dict
- LLM prompt: generate wardrobe per cast_id in scene
- Wardrobe ref generation: per cast_id
- Shot rendering: lookup wardrobe by cast_id

---

### 3. Wardrobe Ref REPLACES Character Ref

**Current:**
```python
refs = []
refs.append(char_refs["ref_a"])      # Character reference
refs.append(scene["wardrobe_ref"])   # + Wardrobe reference
# → Model sees 2 different people → clones
```

**Proposed:**
```python
# Per cast member in shot:
if has_wardrobe_ref(cast_id, scene_id):
    refs.append(wardrobe_refs[cast_id])  # ONLY wardrobe ref
else:
    refs.append(char_refs["ref_a"])       # Fallback to character ref
```

**Implementation:**
- `get_shot_ref_images()`: check wardrobe_ref per cast_id first
- If wardrobe_ref exists → use ONLY that, skip ref_a
- If no wardrobe_ref → use ref_a as before

---

### 4. Auto-Wardrobe for Functional Roles

**Current:**
- Extra with role "Waiter" → no wardrobe generated
- Visual: casual clothes in formal setting

**Proposed:**
```python
FUNCTIONAL_ROLES = {
    "waiter": "formal waiter uniform, white shirt, black vest, bow tie",
    "gardener": "work overalls, gardening gloves, sun hat",
    "doctor": "white lab coat, stethoscope",
    "guard": "security uniform, badge",
    "chef": "white chef coat, chef hat",
    # ... etc
}

# During scene generation:
for cast_id in scene_cast:
    cast = get_cast(cast_id)
    if cast["role"] == "Extra" and cast.get("function") in FUNCTIONAL_ROLES:
        scene["wardrobe"][cast_id] = FUNCTIONAL_ROLES[cast["function"]]
```

**Implementation:**
- Define FUNCTIONAL_ROLES mapping
- Auto-populate wardrobe for Extras with matching functions
- Or: LLM instruction to always give functional Extras appropriate wardrobe

---

### 5. Base Outfit System

**Problem:** Great wardrobe in scene 1, falls back to casual ref_a in other scenes.

**Proposed:**

#### A. "Set as Default Outfit" Button
```python
cast = {
    "cast_id": "marc_01",
    "default_wardrobe": {
        "description": "vintage tweed outfit, flat cap, leather satchel",
        "ref_url": "/renders/projects/.../marc_01_wardrobe_default.png"
    }
}
```
- UI: Button on wardrobe preview → "Set as Default"
- All scenes WITHOUT explicit wardrobe → use default_wardrobe
- Maintains visual consistency across video

#### B. "Outfit Inspiration" Button (NEW!)
```python
# User clicks "Inspire Others" on Marc's vintage outfit
# System generates complementary outfits for other cast:
{
    "marc_01": "vintage tweed outfit, flat cap",           # SOURCE
    "dokteur_01": "vintage wool coat, period glasses",     # INSPIRED
    "anna_01": "vintage floral dress, pearl necklace",     # INSPIRED
}
```
- Select a wardrobe as "style source"
- LLM generates complementary (not identical) outfits for other cast
- Great for: "everyone in vintage", "formal event", "beach party", etc.

---

## UI Changes Required

### Cast Panel
- [ ] Gender dropdown (male/female/neutral)
- [ ] Default Outfit thumbnail + "Set as Default" button
- [ ] "Clear Default" button

### Scene Panel  
- [ ] Wardrobe per cast member (expandable list)
- [ ] "Inspire Others" button on any wardrobe
- [ ] Visual indicator: 👔 = has wardrobe, ∅ = using default/ref

### Shot Panel
- [ ] Show which ref type used: [REF-A] / [WARDROBE] / [DEFAULT]

---

## Data Migration

Existing projects have `scene.wardrobe` as string. Migration:

```python
# If wardrobe is string (old format):
if isinstance(scene.get("wardrobe"), str):
    old_wardrobe = scene["wardrobe"]
    # Assign to all cast in scene
    scene["wardrobe"] = {
        cast_id: old_wardrobe 
        for cast_id in scene.get("cast", [])
    }
```

---

## Implementation Order

1. **Phase 1: Schema & Storage**
   - Add gender to cast
   - Change wardrobe to dict
   - Add default_wardrobe to cast
   - Migration script for existing projects

2. **Phase 2: Generation Logic**
   - Gender-aware wardrobe prompts
   - Per-cast wardrobe generation
   - Auto-wardrobe for functional roles

3. **Phase 3: Rendering Logic**  
   - Wardrobe ref replaces ref_a
   - Default outfit fallback chain
   - Update `get_shot_ref_images()`

4. **Phase 4: UI**
   - Gender dropdown
   - Per-cast wardrobe display
   - "Set as Default" button
   - "Inspire Others" button

---

## Testing Checklist

- [ ] Male cast member gets masculine wardrobe
- [ ] Female cast member gets feminine wardrobe  
- [ ] Scene with 3 cast → 3 different wardrobes possible
- [ ] Wardrobe ref used → no cloning
- [ ] Extra "Waiter" → automatic uniform
- [ ] Default outfit persists across scenes
- [ ] "Inspire Others" creates complementary looks

---

## Notes

- This is a significant refactor touching: schema, LLM prompts, render logic, UI
- Backward compatibility via migration script
- "Outfit Inspiration" is the cherry on top - do last
- Test with the hilarious examples from discovery session 😂

---

*Documented: 2026-01-25*  
*Ready for implementation after good night's sleep* 😴
