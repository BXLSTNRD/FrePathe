# FréPathé v1.8.7 - Storyboard System Fixes

**Datum:** 24 januari 2026  
**Aanleiding:** Analyse van 7 systemische problemen in storyboard generatie

---

## SAMENVATTING WIJZIGINGEN

### Bestanden gewijzigd:
- `main.py` - Shot expansion, scene generation, cast handling
- `services/llm_service.py` - Temperature parameter toegevoegd

---

## FIX 1: Wardrobe & Decor_alt Prompt Instructies

**Probleem:** System prompt voor scene generatie zei "USE SPARINGLY" en "leave empty 80-90% of scenes", waardoor LLM bijna nooit wardrobe/decor_alt genereerde.

**Oplossing:** Instructies herschreven om wardrobe en decor_alt te ENCOURAGEREN wanneer narratief zinvol:

```
WARDROBE:
- Describe what characters WEAR in this scene - clothing, accessories, style
- Consider: Does the scene context call for specific attire? (work, formal, casual, period)
- Does the character's emotional state affect their appearance? (disheveled, polished, transformed)
- Wardrobe creates visual continuity within a scene and contrast between scenes

ALTERNATIVE DECOR:
- Use when the narrative benefits from contrasting locations: flashbacks, dreams, parallel timelines
- Provides visual variety and storytelling depth - use when it enhances the scene
```

**Locatie:** `main.py` line ~1790 (`api_castmatrix_autogen_scenes`)

---

## FIX 2: Video Model Duration in Shot Expansion

**Probleem:** Shot expansion LLM kreeg hardcoded "2-5 seconds" instructie, ongeacht welk video model geselecteerd was. Kling vereist min 5s, Kandinsky exact 5s.

**Oplossing:** Duration guidance dynamisch uit `VIDEO_MODELS[video_model].duration_range`:

```python
video_model_key = state.get("project", {}).get("video_model", "none")
video_model_info = VIDEO_MODELS.get(video_model_key)
if video_model_info:
    min_dur, max_dur = video_model_info.get("duration_range", (2, 5))
    if min_dur == max_dur:
        duration_guidance = f"EXACTLY {min_dur} seconds (video model has fixed duration)"
    else:
        duration_guidance = f"{min_dur}-{max_dur} seconds (video model requirements)"
```

**LLM krijgt nu:** "SHOT DURATION: Each shot MUST be 5-10 seconds (video model Kling Video v2.6 Pro requirements). This is a HARD CONSTRAINT."

**Locatie:** `main.py` in `api_expand_all` en `api_expand_sequence`

---

## FIX 3: Shot Duration Validation & Auto-Extend

**Probleem:** Shots korter dan video model minimum werden niet gecorrigeerd.

**Oplossing:** Na LLM response, valideer elke shot tegen min/max:

```python
if duration < min_dur:
    print(f"[WARN] Shot {shot_id} is {duration:.1f}s (below {min_dur}s min)")
    end = start + min_dur
    print(f"[INFO] Extended {shot_id} to {min_dur}s")
elif duration > max_dur:
    print(f"[WARN] Shot {shot_id} is {duration:.1f}s (exceeds {max_dur}s max)")
```

**Locatie:** `main.py` in beide `api_expand_all` en `api_expand_sequence` shot loops

---

## FIX 4: Scene Wardrobe/Decor naar LLM Payload

**Probleem:** System prompt zei "Scene WARDROBE is provided" maar de data werd NIET meegestuurd in de user payload.

**Oplossing:** Scene context toegevoegd aan LLM payload:

```python
scene_for_seq = next((s for s in scenes if s.get("sequence_id") == seq.get("sequence_id")), None)
scene_context = {
    "wardrobe": scene_for_seq.get("wardrobe", ""),
    "decor_alt_prompt": scene_for_seq.get("decor_alt_prompt", ""),
    "decor_prompt": scene_for_seq.get("prompt", ""),
} if scene_for_seq else None

# In user payload:
"scene_context": scene_context,
```

**Locatie:** `main.py` in beide `api_expand_all` en `api_expand_sequence`

---

## FIX 5: Cast Impact Sliders Werken Nu

**Probleem:** Impact slider waarde werd opgeslagen maar `usage` string was alleen gebaseerd op role, niet op actual impact value.

**Oplossing:** Dynamische usage string gebaseerd op impact percentage:

```python
if impact >= 0.7:
    usage = f"HIGH PRESENCE ({int(impact*100)}%) - MUST appear in most shots (70%+)"
elif impact >= 0.4:
    usage = f"MEDIUM PRESENCE ({int(impact*100)}%) - should appear in ~half the shots"
else:
    usage = f"LOW PRESENCE ({int(impact*100)}%) - brief appearances, 1-2 shots with PURPOSE"
```

**Effect:** Supporting cast met 80% impact krijgt nu "HIGH PRESENCE" ipv default "~half shots"

**Locatie:** `main.py` in `api_build_sequences`, `api_expand_all`, `api_expand_sequence`

---

## FIX 6: Temperature Parameter voor Regeneratie Variatie

**Probleem:** Claude altijd met temperature 0.7 aangeroepen. Regenerate gaf vaak zelfde output.

**Oplossing:** Temperature parameter toegevoegd aan LLM calls:

```python
def call_claude_json(system, user, model, max_tokens, temperature=0.7):
    """temperature: 0.7 default. Use 0.85-0.95 for regeneration variety."""

def call_llm_json(system, user, preferred, max_tokens, state, temperature=0.7):
    # Passed through to both Claude and OpenAI
```

**Gebruik:** Voor regenerate calls, gebruik `temperature=0.9` voor meer variatie.

**Locatie:** `services/llm_service.py`

---

## FIX 7: Beat Grid Snapping voor Music Sync

**Probleem:** Downbeats werden naar LLM gestuurd maar niet geforceerd. `snap_to_grid()` functie bestond maar werd niet gebruikt.

**Oplossing:** Post-processing snap na LLM response:

```python
all_downbeats = beat_grid.get("downbeats") or []
if all_downbeats:
    orig_start, orig_end = start, end
    start = snap_to_grid(start, all_downbeats, tolerance=0.3)
    end = snap_to_grid(end, all_downbeats, tolerance=0.3)
    # Ensure minimum duration still met after snapping
    if end - start < min_dur:
        end = start + min_dur
    if start != orig_start or end != orig_end:
        print(f"[SYNC] {shot_id}: snapped {orig_start:.2f}-{orig_end:.2f} → {start:.2f}-{end:.2f}")
```

**Effect:** Shot cuts vallen nu op muziek beats (±0.3s tolerance)

**Locatie:** `main.py` in beide `api_expand_all` en `api_expand_sequence`

---

## NIET GEWIJZIGD (bestaande code was correct)

- Cast sorting by role hierarchy (lead → supporting → extra) - al geïmplementeerd
- Continuity context (prev/next sequence) - al geïmplementeerd  
- Beat grid generation (`build_beat_grid`) - werkte correct
- Lyrics slicing per sequence - werkte correct
- Total duration validation & auto-scaling - al geïmplementeerd

---

## TESTING CHECKLIST

- [ ] Maak nieuw project met Kling video model
- [ ] Genereer scenes → check of wardrobe/decor_alt nu vaker worden ingevuld
- [ ] Expand shots → check console voor `[SYNC]` log messages (beat snapping)
- [ ] Check shot durations zijn ≥5s (Kling minimum)
- [ ] Verander cast impact slider → re-expand → check of usage in prompt verandert
- [ ] Vergelijk total shot duration met track duration

---

## POTENTIËLE ISSUES

1. **Beat snapping kan gaps creëren** als shots na snapping niet meer aansluiten
   - Huidige mitigatie: duration scaling achteraf corrigeert totaal
   
2. **Scene matching** gaat op `sequence_id` - als die niet matchen krijgt LLM geen scene context
   - Check: scene.sequence_id moet exact matchen met sequence.sequence_id

3. **Temperature niet exposed in UI** - alleen via code aan te passen voor regenerate calls
