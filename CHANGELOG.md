# Changelog

## v1.7.1 (2026-01-15) - PREVIEW MODULE BUGFIX

### Fixed
- **Preview Module Export**: Fixed 500 errors and video export failures in Preview module
  - Image path resolution: Use only new project folder structure, removed legacy path support
  - FFmpeg debugging: Enhanced error logging with detailed command and file path information
  - Clip caching: Temp folder preserved for reuse, dramatically faster subsequent exports
  - Concat reliability: Fixed input file errors with proper encoding and path validation
- **Cost tracking persistence**: All render endpoints now persist costs to project JSON (Bug #1 - Critical Fix)
  - Scene renders (decor, decor_alt, wardrobe preview)
  - Shot renders (both t2i and i2i paths)
  - Scene edit operations (decor_alt generation, img2img edits)
  - Shot edit operations
  - Previously costs were tracked to in-memory state but lost on fresh_state reload within locks
- **Scene queue system**: buildTimelineAndScenes now uses unified queue system like shots (visual status in timeline)
- **AudioDNA/CastMatrix sync**: Fixed flexbox height when cast > 3 (Bug #2)
- **CastMatrix UX**: 6 fixes including input loss, ref clickability, style lock clarity (Bug #3)
- **Scene decor people**: Strengthened no-people prompt with all-caps emphasis (even if style allows people)
- **Wardrobe cascade**: Shots now inherit scene wardrobe with proper fallback chain (shot > scene > cast)
- **Image popup z-index**: Now appears above scene popup (z-index 2100 vs 2000)

### UI Improvements
- **Preview Module**: Simplified interface with fade transitions removed, only resolution selector
- **Version**: Updated UI title to v1.7.1
- **Timeline icons**: Wardrobe and decor-lock indicators moved to bottom-right with yellow accent
- **Queue status**: Added `.timeline-seg-v2.in-queue` styling (dashed yellow border)
- **Render states**: Added timeline support for rendering/done/error states with animations
- **Queue badges**: Added yellow queue number styling in timeline thumbnails

### Director Logging (Fine-tuning Data Collection)
- **New module**: `get_project_director_dir()` and `save_director_log()` in project_service
- **Complete conversations**: System prompt + user context + LLM response saved to director/{operation}_{timestamp}.json
- **Coverage**: All 4 LLM endpoints now log to Director folder:
  - `sequences/build` - Timeline generation with beat grid
  - `scenes/autogen` - Scene generation from sequences
  - `shots/expand_all` - Expand all sequences to shots
  - `shots/expand_sequence` - Expand single sequence to shots
- **Purpose**: Training data for fine-tuning storyboard generation models

### LLM Prompt Improvements
- **Scene generation**: Strengthened guidance to use B-scenes and wardrobe SPARINGLY (95% and 80-90% empty respectively)
- **B-scene criteria**: Only for narratively essential dual locations (flashbacks, dream vs reality, parallel timelines)
- **Wardrobe criteria**: Only for story-critical costumes (uniforms, formal events, period clothing, transformations)
- **No repetition**: Explicitly forbid repeating same wardrobe across multiple scenes
- **Shot inheritance**: Shots now inherit scene wardrobe unless specifically overridden
- **Empty decors**: CRITICAL emphasis that scene renders must be UNINHABITED (even if style allows people)

### Technical
- Enhanced icon positioning with proper z-index stacking when both wardrobe + lock present
- Uniformized timeline scene cards with shot card design patterns
- Added pulse-border animation for rendering state

---

## v1.7.0 (2026-01-14) - SERVICES ARCHITECTURE

### Major Refactor
- **Modular architecture**: Extracted 11 service modules from monolithic main.py
- **Code reduction**: main.py reduced from 3444 to 2190 lines (36% reduction)
- **Better maintainability**: Clear separation of concerns across services

### New Service Modules (2914 lines total)
- `services/config.py` - Configuration, API keys, cost tracking, threading locks
- `services/project_service.py` - Project CRUD, persistence, validation
- `services/audio_service.py` - Audio analysis, BPM detection, beat grids, Whisper
- `services/cast_service.py` - Cast management, character refs, style lock
- `services/render_service.py` - FAL AI image generation (T2I, I2I), prompt building
- `services/storyboard_service.py` - Sequences, shots, timeline management
- `services/export_service.py` - FFmpeg video export pipeline
- `services/llm_service.py` - LLM API calls (Claude/OpenAI) with cascade fallback
- `services/styles.py` - 55+ visual style presets with tokens
- `services/ui_service.py` - Template rendering, static file helpers

### Key Features Preserved
- All v1.6.6 functionality maintained
- Thread-safe project locks
- JSON schema validation
- Cost tracking with live pricing
- Cast matrix with ref_a/ref_b/ref_c
- Multi-model support (Flux, SeeDream, Nano Banana)

### Documentation
- `ARCHITECTURE.md` - Complete system documentation (635 lines)
- Service layer patterns and data flows documented
- API endpoint reference included

---

## v1.6.6 (2026-01-13) - STABLE BASELINE

*Last version before services refactor - all features working*
- `sanitize_filename()`, `get_project_folder()`, `get_project_renders_dir()`
- `get_project_audio_dir()`, `get_project_video_dir()`, `get_project_llm_dir()`
- `save_llm_response()`, `download_image_locally()`
- `validate_against_schema()`, `validate_shot()`, `validate_sequence()`, `validate_project_state()`
- `project_path()`, `load_project()`, `recover_orphaned_renders()`, `save_project()`, `new_project()`
- `list_projects()`, `delete_project()`, `normalize_structure_type()`

### Imported from services.audio_service
- `get_audio_duration_librosa()`, `get_audio_duration_mutagen()`, `get_audio_duration()`
- `get_audio_bpm_librosa()`, `build_beat_grid()`, `snap_to_grid()`
- `normalize_audio_understanding()`

### Imported from services.cast_service
- `find_cast()`, `cast_ref_urls()`, `get_cast_refs_for_shot()`, `get_lead_cast_ref()`
- `create_cast_visual_dna()`, `update_cast_properties()`, `update_cast_lora()`
- `delete_cast_from_state()`, `set_character_refs()`, `get_character_refs()`
- `check_style_lock()`, `get_style_lock_image()`, `set_style_lock()`, `clear_style_lock()`
- `get_scene_by_id()`, `get_scene_for_shot()`, `get_scene_decor_refs()`, `get_scene_wardrobe()`

### Imported from services.render_service
- `model_to_endpoint()`, `call_txt2img()`, `call_img2img_editor()`
- `resolve_render_path()`, `build_shot_prompt()`, `get_shot_ref_images()`
- `update_shot_render()`, `get_pending_shots()`, `get_render_stats()`

### Imported from services.storyboard_service
- `target_sequences_and_shots()`
- `create_sequence()`, `find_sequence()`, `update_sequence()`
- `create_shot()`, `find_shot()`, `update_shot()`, `delete_shot()`, `get_shots_for_sequence()`
- `repair_timeline()`, `validate_shots_coverage()`, `get_cast_coverage()`

### Imported from services.export_service
- `update_export_status()`, `get_export_status()`
- `check_ffmpeg()`, `export_video()`

---

## v1.6.8 (2026-01-13) - SERVICES EXTRACTION (Prep for v1.7)

### New services/ Module (Preparation)
- **Extracted 6 service modules** from main.py (not yet integrated):
  - `config.py` - Shared configuration, API keys, endpoints, cost tracking
  - `project_service.py` - Project CRUD, validation, folder management
  - `audio_service.py` - Audio DNA extraction, BPM detection, beat grid
  - `cast_service.py` - Cast management, character refs, style lock
  - `render_service.py` - FAL image generation (txt2img, img2img)
  - `storyboard_service.py` - Sequences, shots, timeline operations
  - `export_service.py` - FFmpeg video export

### Status
- Services are **standalone modules** ready for import
- main.py still contains original code (works as before)
- v1.7.0 will integrate services into main.py

---

## v1.6.6 (2026-01-13) - BUG FIX SPRINT

### Audio Expert Persistence Fix
- Audio Expert checkbox (`use_whisper`) now properly restored on page reload
- Added project state restoration in `DOMContentLoaded` event
- Settings correctly synced from server when project ID exists

### Scene Render Improvements
- **Wardrobe auto-render**: When a scene has wardrobe defined, it's now automatically generated during scene render
- New `_generate_wardrobe_ref_internal()` helper function for consistent wardrobe preview generation
- Scene render endpoint now returns `wardrobe_ref` alongside `decor_refs` and `decor_alt`
- Refactored wardrobe_ref endpoint to use shared helper (DRY code)

### Shot Card UI Fix
- Fixed Enter key not triggering shot edit (changed `this.value` to `event.target.value`)
- Fixed arrow button using wrong DOM selector pattern
- Both inline edit prompt input and arrow button now work correctly

### Collapsible Sections Fix
- `toggleSectionCollapse()` now handles both card modules (Audio, Cast) and subsections (Timeline, Shots)
- Timeline and Shots sections can now be manually collapsed/expanded after auto-collapse
- Fixed content element targeting for different section types

---

## v1.6.5 (2026-01-13) - STABILITY & CACHE FIX

### Race Condition Fix (Parallel Renders)
- Added per-project threading locks for atomic load→modify→save operations
- Fixes bug where parallel renders would overwrite each other's results
- All render endpoints now thread-safe:
  - Shot render and edit
  - Cast canonical refs and single ref rerender
  - Scene decor render, alt decor, and edit

### Cache-Busting for All Images
- New `cacheBust(url)` helper adds timestamp to image URLs
- Prevents browser from showing stale renders after re-rendering
- Applied to all dynamically rendered images:
  - Cast refs (main, ref_a, ref_b)
  - Scene decors in timeline and ref picker
  - Shot renders in storyboard cards
  - Shot ref picker images
  - Shot editor images
  - Scene popup images (decor 1, decor 2, wardrobe)

### Audio Expert Persistence Fix
- `ensureProject()` now captures checkbox state when creating new projects
- Audio Expert setting properly stored when audio is imported
- Setting changeable after analysis but before lock

---

## v1.6.3 (2025-01-12) - AUDIO LOCK FIX & UI POLISH

### Audio Lock Flow (3-stage)
- IMPORT AUDIO → LOCK AUDIO → AUDIO LOCKED
- Audio no longer auto-locks; requires explicit lock action
- Storyboard buttons now require BOTH audio AND cast locked

### Collapsible Sections
- Audio & Cast sections are now manually toggleable (click header)
- Shows ▼ when expanded, ▶ when collapsed
- Collapse state persists during session

### Cast Rerender Fixes
- Status messages now show in Cast Matrix module (not Pipeline)
- All rerender functions use castStatus
- refreshFromServer called after each rerender

### UI Fixes
- Card headers left-aligned
- Cursor pointer on all card headers
- SVG icons for lock and wardrobe indicators

---

## v1.6.2 (2025-01-12) - SCENE MANAGEMENT & COLLAPSIBLE UI

### Scene Popup Overhaul
- Image displayed at 1:1 ratio (no forced square crop)
- Reprompter (edit prompt + rerender button) moved from card to popup
- Lock Decor button: prevents re-rendering/editing scene
- Lock Wardrobe button: prevents wardrobe changes
- Alt decor display when present

### Alternative Decors (decor_alt)
- LLM can now suggest an alternative decor per scene for:
  - Flashbacks
  - Dream sequences
  - Parallel timelines
  - Dramatic contrasts
- Alt decor rendered automatically when LLM provides `decor_alt_prompt`
- Displayed as smaller thumbnail in scene popup

### Wardrobe Preview
- New "Preview" button generates wardrobe reference image
- Combines lead cast ref_a with scene decor + wardrobe prompt

### Scene Cards (Simplified)
- Removed inline edit prompt and rerender button (now in popup)
- Shows decor lock indicator (🔒) when locked
- Wardrobe indicator icon changed: 👔 → 🎩

### Collapsible Sections
- Audio DNA collapses when both audio + cast are locked
- Cast Matrix collapses when cast is locked
- Click header to expand (shows ▶ indicator)

---

## v1.6.1 (2025-01-12) - UI POLISH & COST FIX

### New Logo
- Updated Fré Pathé logo with cat mascot

### Cost Tracking Fixed
Updated FAL API pricing from dashboard (Jan 2026):
- `nano-banana-pro/edit`: $0.15/image
- `seedream/v4.5/edit`: $0.04/image
- `flux-2/edit`: $0.012/megapixel
- `audio-understanding`: $0.01/5sec

Added Claude model pricing:
- `claude-sonnet-4-5-20250929`: $0.02/call
- `claude-3-5-sonnet-latest`: $0.015/call
- `claude-3-haiku-20240307`: $0.002/call

LLM cost tracking now automatic in `call_llm_json()`.

### Cast Matrix UI
- Style lock badge: text only, no emoji (monotone UI)
- Placeholder "Keywords..." → "Extra prompt..."
- New rerender button (↻) next to extra prompt field
- Extra prompt now has override priority (placed at start of prompt, not end)

### Audio Expert
Already working: checkbox enables Whisper v3 for lyrics extraction instead of audio-understanding.

---

## v1.6.0 (2025-01-12) - STYLE LOCK & SCENE WARDROBE

### Scene Wardrobe System
Characters can have different outfits per scene:
- LLM generates `scene.wardrobe` during scene autogen
- Scene wardrobe **overrides** cast `prompt_extra` (default outfit)
- Enables: gala dresses, flashback outfits, work uniforms, transformations
- Empty wardrobe falls back to cast default

### Claude Model Cascade
Robust fallback through 4 Claude models:
1. `claude-sonnet-4-5-20250929` (primary - latest Sonnet 4.5)
2. `claude-3-5-sonnet-latest` (latest stable)
3. `claude-3-5-sonnet-20241022` (older specific)
4. `claude-3-haiku-20240307` (fast fallback)
5. OpenAI as absolute last resort

### Style Lock System
First generated cast reference becomes the style anchor:
- `style_locked: true` after first cast ref generated
- `style_lock_image` stores the anchor image URL
- All subsequent renders use this as additional reference
- Ensures visual consistency across all characters and shots
- Clear via UI badge or `/api/project/{id}/clear_style_lock`

### API Test Endpoints
New endpoints to verify API connectivity:
- `GET /api/test/claude` - Test Claude API
- `GET /api/test/openai` - Test OpenAI API
- Returns `{ok: true/false, response/error}`

### Path Resolution Helper
- `resolve_render_path()` handles both legacy and new folder structures
- Works for: `/renders/filename.png` and `/renders/projects/Title_v1.6.0/renders/filename.png`
- Used consistently across all render-related code

### UI Improvements
- Style lock badge in Cast Matrix header (🎨)
- Click badge to clear style lock with confirmation
- Version display updated throughout

---

## v1.5.9.1 (2025-01-10) - PROJECT FOLDERS & STABILITY

### Project Folder System
All project assets now organized in dedicated folders:
```
data/projects/ProjectTitle_v1.5.9.1/
├── renders/     ← All images (Cast_Name_RefA.png, Sce01_Sho01.png)
├── audio/       ← Audio files
├── video/       ← Exported videos
├── llm/         ← Raw LLM responses for debugging
└── project.json ← Project state copy
```

### Friendly Filenames
- Cast refs: `Cast_JohnDoe_RefA.png` instead of `uuid_lead_1_ref_a_hash.png`
- Shots: `Sce01_Sho03.png` instead of `uuid_seq_01_sh03_hash.png`
- Scenes: `Sce01_Decor.png`, `Sce01_Edit.png`
- Video: `ProjectTitle_export.mp4`

### Version Mismatch Protection
- Projects store `created_version`
- Autosave disabled when loading projects from different versions
- Prevents accidental corruption of old projects

### LLM Response Logging
- Raw Claude/OpenAI responses saved to `project/llm/` folder
- Useful for debugging and prompt optimization

### Export Progress in UI
- New endpoint: `GET /api/project/{id}/export/status`
- UI polls during export, shows "Created clip X/Y: shot_id"
- Real-time feedback instead of just "Encoding video..."

### 5 New Puppet/Animation Styles
- `muppet_show` - Jim Henson felt puppet aesthetic
- `claymation` - Aardman-style plasticine
- `thunderbirds` - Supermarionation retro sci-fi
- `spitting_image` - Satirical latex caricature
- `team_america` - Action puppet parody

### Character Prompts Improved
Extended negative prompts for cast refs:
- Added: `no typography, no title, no caption, no overlay, no frame, no border, no logo`
- Prevents text/UI elements appearing on character images

### Frontend Fixes
- Status messages: joke OR serious (not both combined), 7s interval
- Progress bar removed (was non-functional)
- Version display updated

### Backward Compatibility
- Legacy render paths (`/renders/filename.png`) still work
- serve_render handles both old and new folder structures

### Retry on 502 Errors
- API calls to FAL retry up to 3 times on 502 errors
- Exponential backoff (2s, 4s, 8s)
- Applies to: img2img, t2i, all image generation calls

### LLM Fallback System
- `call_llm_json()` automatically falls back between Claude ↔ OpenAI
- If primary provider fails, tries secondary
- No more complete failures due to single provider issues

### Style Dropdown Remains Editable
- Style can be changed after cast is rendered
- Warning shown if existing renders will need re-rendering
- Allows iterating on visual style without starting over

### Wardrobe in Storyboard Generator
- Cast `prompt_extra` field now passed as "wardrobe" to LLM
- LLM can incorporate costume/wardrobe hints in shot descriptions
- Better visual consistency for character outfits

### Bug Fixes
- Fixed indentation bug in bulk decor render (decor_2 was inside loop)
- Improved error handling throughout

---

## v1.5.3 (2025-01-08) - VIDEO EXPORT

### FFmpeg Video Export

New VIDEO section with export functionality:

```
[Fade Duration: 0.5s] [Resolution: 1080p] [Export Video]
```

**Features:**
- Hard cuts within scenes
- Audio sync with original track
- Resolution options: 720p, 1080p, 4K
- In-browser video player with download

### Bug Fixes

**Aspect Ratio Fix:**
- Seedream and Flux2 img2img now respect project aspect ratio (was defaulting to 1:1)
- All editors now pass `aspect_ratio: "16:9"` for horizontal projects

**Cast Distribution Fix:**
- Shot expansion now includes full cast info with roles and impact percentages
- EXTRA cast members now explicitly required to appear in at least 1-2 shots
- LLM prompt updated with clear cast distribution rules

**UI Fixes:**
- Image model dropdown syncs to saved project value on load
- LLM, Style, Aspect, and Project Name also sync correctly

**Cost Breakdown Popup:**
- Click on cost display ($X.XX) to see detailed breakdown
- Shows per-model costs and call counts
- Note about BTW/VAT (+21%) on actual FAL charges

### Shot Image Live Update

Shot cards now show image immediately after render (no refresh needed).

### Timeline Duration Fix

LLM prompt now explicitly states audio duration 3x to ensure sequences don't exceed it.

---

## v1.5.2 (2025-01-08)

### Cast Ref Pose Fix

Changed from frontal to three-quarter view for better character recognition:

```python
# Before (too frontal, misses ponytails/buns):
"full body, standing, neutral pose, centered"

# After (captures hair/profile details):
"full body, standing, three-quarter view, slight angle"
```

### Lyrics/Cast Column Height Sync

Audio DNA and Cast Matrix cards now match height:
```css
.two-column > .card {
  display: flex;
  flex-direction: column;
  height: 100%;
}
```

### Unified Render Queue

Queue system now handles shots, scenes, AND cast refs:
```javascript
RENDER_QUEUE = [{type: "shot", id: "..."}, {type: "scene", id: "..."}, {type: "cast", id: "..."}]
```

- `buildScenes()` now adds scenes to queue instead of sequential rendering
- `renderItemAsync()` handles all three types
- `updateRenderStatus()` updates UI for any type

### Consistent Rerender Buttons

All rerender buttons (↻) now use unified `.rerender-btn` style:
- Circular button, appears on hover
- Same styling across shots, scenes, cast refs

---

## v1.5.1 (2025-01-08) - CRITICAL HOTFIX

### Cast References Fix

**BUG:** Cast ref_a/ref_b images were NOT being sent to img2img!

```python
# v1.5.0 (BROKEN):
if ref_url and not ref_url.startswith("/renders/"):  # ← Excludes ALL local files!
    ref_images.append(ref_url)

# v1.5.1 (FIXED):
if ref_url and not ref_url.startswith("/renders/"):
    ref_images.append(ref_url)
elif ref_url and ref_url.startswith("/renders/"):
    # Upload local file to FAL
    uploaded_url = fal_client.upload_file(str(local_file))
    ref_images.append(uploaded_url)
```

### Correct FAL Pricing

Updated from FAL dashboard screenshots:

| Model | Old Price | Correct Price |
|-------|-----------|---------------|
| nano-banana-pro | $0.025 | **$0.15**/image |
| nano-banana-pro/edit | $0.03 | **$0.15**/image |
| audio-understanding | $0.05 | **$0.002**/sec ($0.01/5s) |
| seedream/v4.5/edit | $0.04 | $0.04/image ✓ |
| flux-2/edit | $0.05 | **$0.012**/megapixel |

### Audio Cost by Duration

```python
# Now calculates cost based on actual duration
duration_for_cost = local_duration or 180
audio_cost_units = max(1, int(duration_for_cost / 5))  # 5-second units
track_cost("fal-ai/audio-understanding", audio_cost_units, state=state)
```

---

## v1.5.0 (2025-01-08) - RENDER STABILITEIT

### Render Queue System

Frontend-managed render queue with max 2 concurrent renders:

```javascript
// Queue variables
let RENDER_QUEUE = [];
let ACTIVE_RENDERS = 0;
const MAX_CONCURRENT = 2;

// Render All → adds to queue → processRenderQueue()
// processRenderQueue() → starts up to 2 concurrent renders
// When render completes → starts next from queue
```

**UI States:**
- `.in-queue` - Dashed border, slight opacity
- `.rendering` - Orange pulsing border animation
- `.render-done` - Green border
- `.render-error` - Red border

**Prioritize:** Click "↑ Priority" to move shot to front of queue.

### Beat Grid

Audio analysis now calculates beat/bar grid for shot timing:

```json
{
  "beat_grid": {
    "bpm": 120,
    "beat_sec": 0.5,
    "bar_sec": 2.0,
    "beats": [0, 0.5, 1.0, ...],
    "bars": [0, 2.0, 4.0, ...],
    "total_beats": 366,
    "total_bars": 92
  }
}
```

### Cost Tracking Fix

Fixed model name resolution for accurate pricing:

```python
MODEL_TO_ENDPOINT = {
    "nanobanana_edit": "fal-ai/nano-banana-pro/edit",  # $0.03
    "flux2_edit": "fal-ai/flux-2/edit",                # $0.05
    "seedream45_edit": "fal-ai/bytedance/seedream/v4.5/edit",  # $0.04
}
```

### Backend Semaphore

Prepared for future async rendering:
```python
RENDER_SEMAPHORE = asyncio.Semaphore(2)
```

---

## v1.4.9.1 (2025-01-08) - HOTFIX

### Render Recovery

Auto-recovers orphaned render files from previous sessions where the race condition caused data loss.

**On project load:**
1. Scans `/renders/` for files matching `{project_id}_{shot_id}_*.png`
2. If shot has no render but file exists → recovers it
3. Also recovers scene decor refs
4. Auto-saves recovered state

```python
def recover_orphaned_renders(state, pid):
    for shot in shots:
        if not shot.render.image_url:
            for f in RENDERS_DIR.glob(f"{pid}_{shot_id}*"):
                if f.exists():
                    shot["render"] = {"status": "done", "image_url": f"/renders/{f.name}", ...}
```

**Console output:**
```
[INFO] Recovered render for seq_02_sh02: /renders/proj_seq_02_sh02_abc123.png
[INFO] Recovered 5 orphaned renders for project proj-id
```

---

## v1.4.9 (2025-01-08) - FINAL 1.4.x RELEASE

### Critical Bug Fixes

1. **Cost tracking now persistent** - Costs saved to project state, not just session
   - `track_cost()` now updates the state dict directly
   - No more race conditions between cost tracking and project saves
   
2. **Shot renders properly saved** - Fixed race condition where cost tracking overwrote shot render data
   - Root cause: `track_cost()` was loading/saving its own copy of state
   - Fix: `track_cost(model, count, state=state)` updates in-place

3. **CAST HIRED ✓** - Checkmark added to match BAND HIRED

4. **Scene popup** - Dedicated popup with proper styling

### API Changes

```python
# OLD (broken - caused race conditions)
track_cost("fal-ai/model", 1, project_id)

# NEW (correct - updates state in place)
track_cost("fal-ai/model", 1, state=state)
```

### New Endpoint

```
GET /api/project/{id}/costs - Returns project-specific costs
```

---

## v1.4.8 (2025-01-08)

### Bug Fixes

1. **Cast images saved locally** - Source images now saved to `/renders/` with `fal_url` kept for API calls
2. **CAST HIRED ✓** - Added checkmark to match BAND HIRED
3. **Scene popup redesigned** - Dedicated popup with proper layout (280x280 image + title/prompt)
4. **Cast upload refresh** - Uses `refreshFromServer()` to properly show generated refs

### Storage Model

```javascript
// Cast reference_images now stores both:
{
  "url": "/renders/proj_cast_source.jpg",      // Local display
  "fal_url": "https://fal.ai/...",             // API calls
  "role": "primary_face"
}
```

---

## v1.4.7 (2025-01-08)

### Major UI Overhaul

**Cast Matrix**
- Cast ref images (A/B) now stored locally (like shots)
- Separate rerender buttons for A and B
- Empty slots show full UI (slider, text fields) - same as filled slots
- Default impact per role: LEAD=70%, SUPPORT=50%, EXTRA=10%

**Audio/Cast Status**
- "AUDIO LOADED" → "BAND HIRED ✓"
- "LOCKED" → "CAST HIRED"

**Storyboard Workflow**
- "Build Scenes" button removed - now automatic with "Create Timeline"
- Timeline shows scene thumbnails (80px height with 60x60 thumb)
- Story Arc box moved above Timeline
- Click scene thumbnail for popup with details
- Scenes section removed (integrated into timeline)

### New Endpoints
- `POST /api/project/{id}/cast/{cast_id}/rerender/{a|b}` - Rerender single ref

### CSS
- `.timeline-seg-v2` - New timeline segment with thumbnail
- Scene thumbnails clickable for popup
- Rerender button appears on hover

---

## v1.4.6 (2025-01-08)

### Bug Fixes

1. **Slider contained** - Value no longer "goes to eleven" outside the box
   - Fixed width slider (45px) + fixed width value (30px)
   - `overflow: hidden` on wrapper

2. **Text preserved on refresh** - Name/prompt values no longer disappear when ref images load
   - `refreshFromServer()` now saves pending input values before refresh
   - Merges them back into state before re-rendering

3. **"CAST HIRED"** - Changed from "LOCKED" for more creative flair 🎬

---

## v1.4.5 (2025-01-08)

### Cast Card Layout Fix

Corrected grid layout per user's sketch:

```
┌───────┬──────────┬──────────────────────────────┬───────┬───────┐
│       │   DROP   │   NAME              [READY]  │       │       │
│  IMG  ├──────────┼──────────────────────────────┤   A   │   B   │
│ 60x60 │  SLIDER  │   PROMPT                     │ 60x60 │ 60x60 │
└───────┴──────────┴──────────────────────────────┴───────┴───────┘
```

**Grid**: `60px 90px 1fr 60px 60px` × `28px 28px`

- All 3 images: 60×60px
- All fields: 28px height
- READY badge: inline with NAME (not centered)
- PROMPT: full width on row 2
- Rerender button: inside ref A image

---

## v1.4.4 (2025-01-08)

### Cast Card Redesign

Complete rewrite using CSS Grid for proper alignment:

```
┌───────┬──────────┬───────────────────────┬────────┬─────────┐
│       │   DROP   │   NAME                │        │         │
│  IMG  ├──────────┼───────────────────────┤ READY  │ [A] [B] │
│       │  SLIDER  │   PROMPT              │        │         │
└───────┴──────────┴───────────────────────┴────────┴─────────┘
```

- **Grid layout**: 4 columns (thumb, fields, status, refs)
- **Thumbnail**: 60x60px, spans both rows
- **DROP/SLIDER**: Same width (90px), vertically aligned
- **NAME/PROMPT**: Flexible width, fill remaining space
- **Refs**: 36x36px each, rerender button positioned bottom-right
- **Slider**: Shows percentage value next to it

---

## v1.4.3 (2025-01-08)

### Bug Fixes

1. **Cost tracking fixed** - Canonical refs (cast reference images) now tracked
2. **Cast updates now save** - New PATCH endpoint `/api/project/{id}/cast/{cast_id}`
   - Name, role, impact, prompt_extra all saved to server
3. **Impact slider works** - Uses new API endpoint

### UI Improvements

1. **Cast cards redesigned** per sketch:
   - Unified height (32px) for dropdown and name input
   - Bottom row: Screen %, slider (wider), keywords input (28px)
   - Better alignment across all elements
   - Larger slider thumb (14px) for easier interaction
2. **READY badge** - Consistent styling with flex-shrink

---

## v1.4.2 (2025-01-08)

### UI Redesign

1. **Full-width progress bar** at very top of page (thin 4px)
2. **Pipeline nav redesigned**:
   - Steps on left
   - Status text + cost value on right (no emoji)
   - Status text blinks when working
3. **Cast Matrix improvements**:
   - "READY" badge (green) appears when cast member has both ref images
   - Lock button without emoji
   - Cleaner layout with "Screen:" instead of "Impact:"
4. **Module status** - each section can show status next to title

### Dynamic Pricing

- **Live pricing from fal.ai API** on server startup
- `GET https://api.fal.ai/v1/models/pricing` fetched automatically
- Fallback to hardcoded prices if API unavailable
- New endpoint: `POST /api/costs/refresh-pricing` to manually refresh

---

## v1.4.1 (2025-01-07)

### Cost Tracking Fix

- Updated API costs with **real fal.ai pricing** (source: fal.ai/pricing)
- Prices now reflect actual Jan 2025 rates:
  - Nano Banana Pro: $0.025/image
  - Flux Dev: $0.025/image  
  - Flux Pro 1.1: $0.04/image
  - Recraft V3: $0.04/image
  - Claude 3.5 Sonnet: ~$0.003/call
  - GPT-4o-mini: ~$0.0003/call
- Added default fallback price ($0.03) for unknown models
- Added comment with dynamic pricing API endpoint

---

## v1.4.0 (2025-01-07) - MAJOR RELEASE

### 🔴 CRITICAL BUG FIXES

1. **Scenes Now Match Timeline Sequences**
   - Previously: Scenes were randomly generated based only on style
   - Now: Scene autogen receives full sequence context (label, description, energy, cast, arc)
   - Each scene is directly linked to its corresponding sequence

2. **Accurate Audio Duration**
   - Added librosa for accurate audio duration detection
   - No longer relies on fal.ai's often-incorrect duration estimates
   - Fallback to mutagen if librosa unavailable

3. **LLM Prompt Logging**
   - All LLM calls now logged to `data/debug/` directory
   - Includes: system prompt, user prompt, and response
   - Enables debugging of storyboard/scene generation issues

### 💰 Cost Tracking

- New cost counter in status bar (top right)
- Tracks estimated API costs per session
- `/api/costs` endpoint to view cost details
- `/api/costs/reset` to reset counter

### 🔒 Cast Lock System

- **Lock Button**: Must lock cast before creating timeline
- **Locked State**: 
  - Disables all cast editing (images, names, roles)
  - Enables "Create Timeline" button
  - Shows "🔒 CAST LOCKED" badge
- **Unlock**: Click badge area to unlock (allows editing again)

### 🎭 Enhanced Cast Matrix UI

1. **Role Dropdown**: LEAD / SUPPORTING / EXTRA with clear descriptions
2. **Name Field**: Now required before locking
3. **Impact Slider**: 0-100% screen time weight
4. **Prompt Field**: Extra keywords injected into shot prompts
5. **Both Ref Images**: Shots now use both ref_a AND ref_b for better consistency

### 📦 Dependencies

- Added: librosa, soundfile, anthropic, openai to requirements.txt

---

## v1.2.7 (2025-01-07)

### Fixes

1. **Load Project Now Shows Renders**
   - `loadProjectFromFile()` now calls `refreshFromServer()` after import
   - All renders properly display when loading a saved project

2. **Consistent UI Refresh**
   - Added `refreshFromServer()` function for reliable state sync
   - All major actions now use `refreshFromServer()` instead of `autosave()`:
     - createTimeline
     - buildScenes
     - rerenderScene
     - sceneToShots
     - allShots
     - renderShot
     - renderAllShots

3. **Refresh Button Added**
   - New ⟳ button next to "Render All" in Shots section
   - Click to manually refresh UI from server state

---

## v1.2.6 (2025-01-07)

### Fixes

1. **Empty Render Boxes Fixed**
   - Added `updateUI()` call after batch operations (renderAllShots, buildScenes)
   - UI now properly refreshes with local render URLs

2. **Scenes: 1 Render Per Scene**
   - Changed from 2 renders to 1 establishing shot per scene
   - Faster build process, less API calls
   - UI updated to show single scene render

3. **Final Sync After Batch Operations**
   - After buildScenes and renderAllShots, full project state is synced
   - UI is fully refreshed to show all rendered images

---

## v1.2.5 (2025-01-07)

### UI/UX Improvements

1. **Incremental Shot Rendering**
   - Individual shot renders no longer cause full UI refresh
   - Shot card updates in-place when render completes
   - No more flickering or disappearing already-rendered shots

2. **Incremental Scene Rendering**
   - Scene renders update cards incrementally during "Build Scenes"
   - Re-render scene updates only that scene card

3. **Render All Shots Button**
   - New "Render All" button in Shots section header
   - Batch renders all unrendered shots with progress indicator
   - Respects sequence filter (renders only selected sequence if one is selected)

4. **Better Coherence Flow**
   - Scenes render both decor images (wide + medium shot)
   - Shot rendering uses scene decor + cast refs for img2img consistency

---

## v1.2.4 (2025-01-07)

### Bug Fixes

1. **500 Error on Create Timeline Fixed**
   - `beat_grid` is a dict, not a list - removed invalid `[:10]` slice
   
2. **Cast Slots Disappearing Fixed**
   - `renderCastList()` now always shows minimum 3 slots (LEAD, SUPPORTING, EXTRA)
   - Empty slots remain visible when first cast member is uploaded
   - Unified rendering logic for filled and empty slots

---

## v1.2.3 (2025-01-07)

### Major Fixes

1. **Seedream 4.5 Edit 422 Error Fixed**
   - Removed invalid `image_size: "auto_2K"` and `max_images` parameters
   - Seedream edit endpoint only accepts: `prompt`, `image_urls`, `num_images`

2. **Shot Rendering Now Uses Reference Images (img2img)**
   - Shots now render using img2img instead of plain text-to-image
   - Reference images used:
     - Scene decor image (first render from matching scene)
     - Cast member ref_a image (first cast member in shot)
   - Fallback to t2i if img2img fails or no refs available

3. **All Renders Saved Locally**
   - New `/data/renders/` directory for local image storage
   - Scene decor images → `{project_id}_{scene_id}_decor1.png`
   - Shot renders → `{project_id}_{shot_id}_*.png`
   - New endpoint: `GET /renders/{filename}` to serve local images

4. **Improved Storyboard Generation Prompt**
   - LLM now receives:
     - Full lyrics preview
     - Song structure sections
     - Story arc info
     - Cast with explicit role descriptions:
       - LEAD = Protagonist, most screen time
       - SUPPORTING = Secondary focus, interacts with lead
       - EXTRA = Background, brief appearances
   - Sequences must reference specific lyrics lines
   - Output includes `story_summary` and `lyrics_reference` per sequence

5. **Story Summary Box in UI**
   - Non-editable text box appears under timeline
   - Shows the generated story arc summary from LLM
   - Helps director understand the visual narrative

### Storage Structure
```
data/
├── projects/    # Project JSON files
├── uploads/     # Audio files, cast uploads
└── renders/     # All rendered images (scenes + shots)
```

---

## v1.2.2 (2025-01-07)

### Bug Fixes

1. **422 Error on Scene Renders Fixed!**
   - Nano Banana Pro API requires `resolution: "1K"` not `"1024"`
   - Fixed payload: `{"prompt": "...", "aspect_ratio": "16:9", "resolution": "1K"}`

2. **Audio DNA Parsing Fixed!**
   - Backend now properly parses JSON from fal.ai audio-understanding text output
   - Extracts BPM, STYLE, STRUCTURE, DYNAMICS, DELIVERY, STORY, LYRICS into correct fields
   - Duration now correctly extracted
   - Frontend has fallback JSON parsing from `raw_text_blob` for older project files

### Storage Info
- **Audio files**: Stored locally in `data/uploads/{project_id}_audio.mp3`
- **Rendered images**: Stored on fal.ai CDN (URLs returned in project JSON)
- **Project JSON**: Use Save button to download complete project including all URLs
- To keep images locally, download them from the CDN URLs in the saved JSON

---

## v1.2.1 (2025-01-07)

### CRITICAL FIX
- **Scene rendering now works!** Added new `/api/project/{project_id}/castmatrix/scene/{scene_id}/render` endpoint that generates 2 decor refs per scene. `buildScenes()` now calls autogen THEN renders each scene.

### Tweaks

1. **Save/Load buttons** moved next to Image Model dropdown. Icons now 90% of button size.

2. **Audio DNA fixes**:
   - Lyrics field now 6x taller and scrollable (no visible scrollbar)
   - Default empty fields shown for idle project
   - Fixed parsing: BPM, STYLE, STRUCTURE, DYNAMICS, DELIVERY, STORY, LYRICS now correctly extracted from fal.ai response

3. **Cast Matrix fixes**:
   - Default 3 empty cards (LEAD, SUPPORTING, EXTRA) shown for idle project
   - When "Cast Loaded" appears, "Confirm Cast" button hides
   - Role labels (LEAD, SUPPORTING, EXTRA, EXTRA 2, etc.) are NOT editable - just text labels

4. **Spacing consistency**: Added `module-content` wrapper with proper margin between module titles and content (PROJECT, STORYBOARD now match DNA and CAST)

5. **Timeline info**: Now shows "X scenes • Ys" with actual audio duration (not hardcoded 180s)

6. **Section headers**: Added whitespace between section titles (Timeline, Scenes, Shots) and their content

7. **Cards improvements**:
   - Description text boxes now scrollable (hidden scrollbar)
   - Re-render buttons (↻) on scene and shot renders

---

## v1.2 (2025-01-06)

### Major UI Overhaul - 15 Patches Applied

1. **Version Update**: 1.12.3 → 1.2

2. **Pipeline**: Kept as is (PROJECT → AUDIO DNA → CAST MATRIX → STORYBOARD → VIDEO)

3. **Status Bar**: Now sticky at top when scrolling. Status text right-aligned.

4. **Module Titles**: Consistent uppercase styling across all modules

5. **Save/Load Icons**: Monochrome icons in header. Full project save/load including:
   - Project settings
   - Audio file & analysis data
   - Cast info (names, IDs, uploads, generated refs)
   - All LLM responses
   - All rendered scenes and shots

6. **Layout**: AUDIO DNA and CAST MATRIX side by side (restored from v1.12.2)

7. **Audio Import**: Single "Import Audio" button replaces file picker + analyze button. Auto-analyzes on import. Shows "AUDIO LOADED ✓" when complete.

8. **Audio DNA Parsing**: Improved JSON structure in default prompt for better pill parsing. Pills now correctly populated from fal.ai response.

9. **Cast Matrix**: 
   - Layout from v1.12.2 with v1.12.3 functionality
   - "Confirm Cast" button (switches to "CAST LOADED ✓")
   - Cast members in horizontal rows
   - Circle "+" button to add new cast
   - Editable role text (Lead/Supporting/Extra)
   - Re-render buttons (↻) on ref thumbnails
   - Click refs to open full-size popup

10. **Storyboard Buttons**: Renamed:
    - "Build sequences from audio dna" → **Create Timeline**
    - "Generate Scenes" → **Build Scenes**
    - Added: **Scene to Shots** (expand selected)
    - Added: **All Shots** (expand all)

11. **Timeline**: Horizontal, scales to 100% width. No horizontal scrollbar.

12. **Scene Cards**: Auto-render on Build Scenes. Card layout:
    - Black title bar: "Scene 1 - Location Name"
    - Gray description area
    - Two render thumbnails side by side
    - Click for popup, re-render button per thumb

13. **Shots Section**: Removed expand/tighten buttons (now in storyboard actions)

14. **Shot Cards**: Card layout:
    - Title bar: Shot ID, start time, end time, duration
    - Description below title
    - Render placeholder with "Render" button (manual per-shot)
    - Re-render button when rendered

15. **Render Module**: Removed entirely

---

## v1.12.3 (2025-01-06)

### Pipeline Navigation
- Removed step numbers — Now displays: PROJECT → AUDIO DNA → CAST MATRIX → STORYBOARD → RENDER → VIDEO

### Project
- Hidden project ID field and Copy ID button
- **Autosave** after every action (audio upload, cast upload, sequence build, etc.)

### Audio DNA
- Output parsed into structured fields: BPM, Style, Structure, Dynamics, Delivery, Story, Lyrics
- Fields are **clickable** — open full content in popup for review
- Custom prompt hidden (uses default)

### Cast Matrix
- **3 initial slots** (Lead, Supporting, Vibe/Extra)
- **Add/Remove cast** buttons
- **Editable names** per cast member
- Thumbnails **clickable** — open full size in popup
- **Regenerate button** (↻) for each generated reference
- **Confirm Cast** button to finalize before storyboard

### Storyboard
- Fixed sequence generation — sequences now properly appear in timeline
- "Generate 5 Scenes" → **"Generate Scenes"** (count matches sequences)
- Scenes input derived from built sequences

### Render
- New dedicated RENDER section with grid of rendered shots

---

## v1.12.2 (2025-01-06)

### UI Redesign
- **Dark theme** — Deep blacks matching screenshot design
- **Two-column layout** — Audio DNA and Cast side-by-side
- **Audio DNA structured viewer**:
  - Info pills: BPM, Style, Structure, Dynamics, Delivery, Story
  - Lyrics box below
  - Hidden custom prompt (uses default)
- **Simplified Cast section**:
  - Upload image → auto-generates 2 canonical refs
  - Clean list view with thumbnails (Lead, Supporting, Vibe/Extra)
  - No verbose descriptions
- **Scenes moved to Storyboard** — "Generate 5 Scenes" now in Storyboard section
- **Save/Load file dialogs**:
  - Save → Downloads project JSON via browser file dialog
  - Load → Opens file picker to import JSON

### API Changes
- Added `POST /api/project/import` — Import project from JSON file

### Terminology
- Scenes = Sequences = Decor (unified as "Scenes")

---

## v1.12.1 (2025-01-06)

- Removed header buttons (dark mode, shortcuts)
- Removed Create/Load buttons

---

## v1.12.0 (2025-01-06)

### Bug Fixes
- **Removed duplicate declarations** — `BASE`, `DATA`, `PROJECTS_DIR`, `UPLOADS_DIR` were defined twice (lines 11-16 and 202-206). Now defined once at the top.
- **Removed dead code** — Unreachable `editor = locked_editor_key(state)` statement after a `raise` in `api_cast_generate_canonical_refs()` has been removed.

### New Features

#### Runtime Schema Validation
- Added `jsonschema` dependency for runtime validation
- New validation functions:
  - `validate_against_schema()` — Generic JSON schema validation
  - `validate_shot()` — Validate individual shot objects
  - `validate_sequence()` — Validate individual sequence objects  
  - `validate_project_state()` — Full project state validation
- `save_project()` now validates before saving (warnings only, non-blocking)
- `load_project()` now validates on load (warnings only)
- New API endpoints:
  - `GET /api/project/{project_id}/validate` — Returns validation status and errors
  - `GET /api/version` — Returns API version info

#### UI Enhancements
- **Dark Mode** — Toggle via 🌓 button, preference saved to localStorage
- **Keyboard Shortcuts**:
  - `Ctrl+S` / `Ctrl+R` — Refresh project
  - `Ctrl+E` — Expand selected sequence
  - `Ctrl+B` — Build sequences
  - `←` `→` — Navigate timeline segments
  - `Esc` — Close modals
- **Pipeline Navigation** — Visual step indicator showing progress
- **Validation Badge** — Shows ✓ Valid or ✗ Errors in status bar
- **Timeline Improvements**:
  - Time ruler with minute:second markers
  - Sequence count and duration info
  - Better segment selection styling
- **Shots Section**:
  - Shot count badge
  - "Render All Visible" batch button
  - "Export Shot List" CSV export
  - Render status indicators (✓ checkmark)
- **Collapsible Audio Section** — Cleaner default view
- **Mobile Responsive** — Better layout on smaller screens
- **Copy Project ID** button for easy sharing

#### Code Quality
- Added `VERSION` constant (`1.12.0`)
- Better error handling with `showError()` function
- Improved code organization and comments

### Dependencies
- Added: `jsonschema==4.23.0`

### Documentation
- Added `docs/PIPELINE_PLAN.md` — Complete roadmap for video assembly features (Stages 6-8)

---

## v1.11.1 (Previous)

- Hard-lock render models by project `image_model_choice`
- Fixed `UnboundLocalError` for `editor` variable
- Redux/identity models removed

## v1.11.0 (Previous)

- Flux-1/dev + Redux removed (hard-disabled)
- Locked T2I models: Nano Banana Pro, Seedream 4.5, Flux 2
- Multiple img2img editors available per project
