# Fré Pathé - AI Coding Agent Instructions

## Project Overview
**Fré Pathé** is an AI-powered video production studio (v1.7.0) that transforms audio into storyboarded videos. It uses LLMs for creative scripting, FAL AI for image/video generation, and follows a modular service architecture.

**Tech Stack:** FastAPI (Python), Vanilla JavaScript SPA, FAL AI (image generation), Claude/OpenAI (LLM), librosa (audio analysis), FFmpeg (video export)

## Architecture

### Modular Services (`services/` - 2914 lines)
The codebase recently underwent major refactoring (v1.6.8-1.7.0) from a monolithic 3444-line `main.py` to 11 specialized services:

- **`config.py`**: Central state, API keys, paths, cost tracking, threading locks
- **`project_service.py`**: Project CRUD, persistence, JSON schema validation  
- **`audio_service.py`**: Audio analysis (BPM, duration), beat grids, Whisper transcription
- **`cast_service.py`**: Character management, ref image handling, style lock
- **`render_service.py`**: FAL AI image generation (T2I, I2I), prompt building
- **`storyboard_service.py`**: Timeline sequences/shots, coverage validation
- **`export_service.py`**: FFmpeg video export pipeline
- **`llm_service.py`**: Claude/OpenAI API calls with cascade fallback
- **`styles.py`**: 55+ visual style presets with token/script generators
- **`ui_service.py`**: Template rendering, static file helpers

### Data Flow Pattern
All endpoints follow: `main.py` → service layer → FAL/LLM APIs → `save_project(state)`

**Critical:** State mutations MUST be wrapped in `with get_project_lock(project_id):` to prevent race conditions during concurrent renders/edits.

### File Organization
```
data/
  projects/{project_id}.json     # Project state (validated against Contracts/*.schema.json)
  renders/projects/{title}/      # Generated images (local storage, NOT git)
    {friendly_name}.png          # e.g., Cast_Emma_RefA.png, Seq01_Shot03.png
  debug/{project_id}_{api}_{ts}  # LLM/FAL call logs for debugging
```

## Critical Conventions

### Image Path Handling (Common Bug Source)
- **FAL URLs** (`https://fal.media/...`): Returned by FAL API, expire after ~24h
- **Local paths** (`/renders/projects/...`): Permanent storage via `download_image_locally()`
- **Resolution**: Use `resolve_render_path(url_or_path)` to convert relative paths to absolute `Path` objects
- **Uploading**: Before sending to FAL, check if path starts with `/renders/` and upload via `fal_client.upload_file(str(local_file))`

**Example (from `main.py` line 134, 770, 1952):**
```python
if ref_a.startswith("/renders/"):
    local_file = resolve_render_path(ref_a)
    if local_file.exists():
        ref_url = fal_client.upload_file(str(local_file))
```

### Cost Tracking Pattern
Every FAL/LLM API call MUST include: `track_cost(model, count, state=state, note="descriptive_label")`
- Costs are per-project (`state["costs"]`) and per-session (`SESSION_COST`)
- Pricing is fetched live from FAL API at startup (`fetch_live_pricing()`)
- Note parameter added in v1.7.0 to distinguish similar calls (e.g., `note="wardrobe"` vs `note="cast_ref"`)

### Character References (Cast Matrix)
Cast members have 3 reference images generated during "lock" operation:
- **`ref_a`**: Full body, used for most shots
- **`ref_b`**: Close-up portrait, used for `close-up|portrait|headshot` camera angles (see `main.py` line 2005)
- **`ref_c`**: Reserved for future use

**Key Logic (line 2005-2008):**
```python
camera_lang = (shot.get("camera_language") or "").lower()
use_closeup = any(kw in camera_lang for kw in ["close-up", "closeup", "close up", "portrait", "head shot", "headshot", "face", "eyes"])
ref_key = "ref_b" if use_closeup else "ref_a"
```

### Style Lock (Known Issue - HANDOVER.md)
- `style_lock_image` is used as `ref_images[1]` in FAL calls to enforce visual consistency
- **Current bug**: If style lock is a person (ref_a of first cast), FAL may blend that person into all renders
- **Intended fix (untested)**: Prompt instructs "match artistic style, not the person" (line ~783)
- **Better solution**: Base style lock on decor/environment images, not people

### LLM Cascade Pattern
Claude models cascade on failure: `claude-sonnet-4-5` → `claude-3-5-sonnet` → `claude-3-haiku` (see `llm_service.py`)
- Always use `call_llm_json(system, user, state)` not raw API calls
- LLM responses saved to `data/debug/` for troubleshooting
- Prompts live in `Prompts/*.txt` and use `{{PROJECT_STATE_JSON}}` template placeholders

## Development Workflow

### Running the App
```powershell
.\run.ps1  # Auto-creates .venv, installs deps, loads keys from *_key.txt files
# Server runs on http://127.0.0.1:8080
```

**Key Environment:**
- API keys loaded from `{fal,openai,claude}_key.txt` (DO NOT commit)
- Python 3.12+, Windows-native (PowerShell commands throughout)
- uvicorn with `--reload` for hot reloading

### Debugging FAL/LLM Calls
Check `data/debug/{project_id}_{fal|llm}_{timestamp}.json` for full request/response payloads. Added in v1.6.6 to diagnose generation issues.

### Schema Validation
All state mutations MUST validate:
- Use `validate_project_state(state, strict=False)` before `save_project(state)`
- Schemas in `Contracts/*.schema.json` follow Draft 2020-12
- Common validation points: shot creation, sequence creation, storyboard generation

### Testing Endpoints
```python
GET /api/test/claude     # Verify Claude API key
GET /api/test/openai     # Verify OpenAI API key  
GET /api/costs           # Check session API costs
```

## Known Issues (v1.7.0-BROKEN per HANDOVER.md)

**The current branch has unresolved bugs from rushed fixes. Consider:**
1. Style lock blends first cast person into all renders (see above)
2. Audio DNA / Cast Matrix height sync CSS broken (`.cast-expanded` logic)
3. Cast card refs change order in UI (`updateCastCardRefs()` attempted fix untested)
4. Preview/export may be broken (FFmpeg debug added but not verified)
5. Renders wardrobe for EVERY scene (should be once per scene)
6. No B-roll scenes generated (storyboard logic issue)

**Recommendation:** Check `git diff c8afc3d..HEAD` to review all changes since v1.6.6 before making new edits.

## Common Patterns

### Concurrent Rendering
Frontend uses `RENDER_QUEUE` + `MAX_CONCURRENT=6` to batch shot renders. Backend uses `RENDER_SEMAPHORE` and per-project locks.

### Friendly Filenames
All downloaded images use `friendly_name` parameter: `Cast_{name}_Ref{A/B/C}`, `Seq{num}_Shot{num}`, `Sce{num}_{title}_Decor`

### Energy-Based Prompting
Shots have 0-1 energy derived from `audio_dna.dynamics`. Converted to tokens via `energy_tokens(energy)` - see `render_service.py`.

## When Editing This Project
1. **Never bypass locks:** Always wrap state mutations in `with get_project_lock(project_id):`
2. **Validate schemas:** Run `validate_project_state()` before saving
3. **Track costs:** Add `track_cost()` to any new FAL/LLM calls
4. **Test image paths:** Verify both FAL CDN URLs and local `/renders/` paths work
5. **Check HANDOVER.md first:** Avoid repeating known broken approaches
6. **Use services:** Don't add logic to `main.py` - extend appropriate service module

## Key Files for Understanding
- `ARCHITECTURE.md` - Full system documentation (635 lines)
- `HANDOVER.md` - Recent failure analysis and warnings
- `Contracts/project_state.schema.json` - Core data model
- `Prompts/claude_generate_storyboard.txt` - LLM creative template
