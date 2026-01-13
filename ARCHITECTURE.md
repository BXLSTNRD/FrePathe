# Fré Pathé v1.7.0 - Architecture Documentation

## 📁 Project Structure

```
FrePathe/
├── main.py                    # FastAPI application (2190 lines)
├── requirements.txt           # Python dependencies
├── run.ps1                    # PowerShell startup script
├── README.md                  # User documentation
├── CHANGELOG.md               # Version history
├── updatelog.md               # Development notes
│
├── services/                  # Modular service layer (2914 lines total)
│   ├── __init__.py           # Module exports (wildcard re-exports)
│   ├── config.py             # Configuration & shared state
│   ├── project_service.py    # Project CRUD & persistence
│   ├── audio_service.py      # Audio analysis & processing
│   ├── cast_service.py       # Cast management & refs
│   ├── render_service.py     # Image generation (T2I/I2I)
│   ├── storyboard_service.py # Sequences & shots
│   ├── export_service.py     # Video export pipeline
│   ├── llm_service.py        # LLM API calls (Claude/OpenAI)
│   ├── styles.py             # Visual style presets (55 styles)
│   └── ui_service.py         # Template rendering & static files
│
├── Contracts/                 # JSON Schema definitions
│   ├── project_state.schema.json
│   ├── storyboard.schema.json
│   ├── visual_dna.schema.json
│   ├── audio_dna.schema.json
│   └── patch_ops.schema.json
│
├── Prompts/                   # LLM prompt templates
│   ├── claude_generate_storyboard.txt
│   ├── claude_insert_scenes.txt
│   └── claude_reinvent_scene.txt
│
├── Builders/                  # Specification documents
│   └── promptbuilder_spec.md
│
├── templates/                 # HTML templates
│   └── index.html            # Main SPA template
│
├── static/                    # Frontend assets
│   ├── app.js                # Main JavaScript application
│   ├── style.css             # Stylesheet
│   └── logo.png              # Application logo
│
├── data/                      # Runtime data storage
│   ├── projects/             # Project state files (*.json)
│   ├── renders/              # Generated images
│   ├── uploads/              # User uploaded files
│   └── debug/                # LLM call logs
│
└── __pycache__/              # Python bytecode cache
```

---

## 🔧 Services Architecture

### 1. `config.py` (283 lines)
**Purpose:** Central configuration, constants, and shared state.

```python
# Exports:
VERSION = "1.7.0"

# Threading
PROJECT_LOCKS: Dict[str, Lock]      # Per-project locks
PROJECT_LOCKS_LOCK: Lock            # Meta-lock
get_project_lock(project_id) -> Lock

# Paths
BASE: Path                          # Project root
DATA: Path                          # data/ directory
PROJECTS_DIR, UPLOADS_DIR, RENDERS_DIR, DEBUG_DIR

# API Keys
FAL_KEY, OPENAI_KEY, CLAUDE_KEY

# FAL Endpoints
FAL_AUDIO, FAL_WHISPER
FAL_NANOBANANA, FAL_NANOBANANA_EDIT
FAL_SEEDREAM45, FAL_SEEDREAM45_EDIT
FAL_FLUX2, FAL_FLUX2_EDIT

# Cost Tracking
API_COSTS: Dict                     # Per-model pricing
SESSION_COST: Dict                  # Current session totals
track_cost(model, count, state)

# Utilities
require_key(key, name) -> str
fal_headers() -> Dict
now_iso() -> str
clamp(val, lo, hi)
safe_float(val, default)
retry_on_502(fn) -> Callable
log_llm_call(...)
fetch_live_pricing()

# Model Helpers
locked_render_models(state) -> Dict
locked_editor_key(state) -> str
locked_model_key(state) -> str
```

---

### 2. `project_service.py` (467 lines)
**Purpose:** Project lifecycle, persistence, validation.

```python
# File System
sanitize_filename(name, max_len) -> str
get_project_folder(state) -> Path
get_project_renders_dir(state) -> Path
get_project_audio_dir(state) -> Path
get_project_video_dir(state) -> Path
get_project_llm_dir(state) -> Path

# Persistence
project_path(project_id) -> Path
load_project(project_id) -> Dict
save_project(state)
new_project(title, style, aspect, llm, image_model, video_model, use_whisper) -> Dict

# Image Downloads
download_image_locally(url, project_id, prefix, state, friendly_name) -> str
save_llm_response(state, response_type, data) -> Path

# Recovery
recover_orphaned_renders(state) -> int

# Validation
validate_against_schema(data, schema_name) -> (bool, List[str])
validate_shot(shot) -> (bool, List[str])
validate_sequence(seq) -> (bool, List[str])
validate_project_state(state, strict) -> (bool, List[str])

# Utilities
normalize_structure_type(raw) -> str
```

---

### 3. `audio_service.py` (315 lines)
**Purpose:** Audio analysis, transcription, beat synchronization.

```python
# Beat Grid
build_beat_grid(bpm, duration) -> List[float]
snap_to_grid(ts, grid) -> float

# Audio Properties
get_audio_duration(file_path) -> float
get_audio_bpm_librosa(file_path) -> Optional[float]

# Audio DNA Processing
normalize_audio_understanding(raw) -> Dict
parse_structure_entry(entry) -> Dict
extract_key_moments(data) -> List[Dict]

# Whisper Integration
transcribe_with_whisper(audio_url) -> Dict
merge_whisper_transcript(audio_dna, whisper_result) -> Dict
```

---

### 4. `cast_service.py` (242 lines)
**Purpose:** Cast member management, character refs, scenes.

```python
# Cast Lookup
find_cast(state, cast_id) -> Optional[Dict]
cast_ref_urls(cast) -> List[str]
get_identity_url(state, cast_id) -> Optional[str]

# Shot/Cast Relations
get_cast_refs_for_shot(state, shot) -> List[str]
get_lead_cast_ref(state, shot) -> Optional[str]

# Cast CRUD
create_cast_visual_dna(cast_id, name, role, local_url, fal_url) -> Dict
update_cast_properties(state, cast_id, updates) -> bool
update_cast_lora(state, cast_id, lora_path, trigger) -> bool
delete_cast_from_state(state, cast_id) -> bool

# Character Refs (Cast Matrix)
set_character_refs(state, cast_id, ref_a, ref_b, ref_c)
get_character_refs(state, cast_id) -> Dict

# Style Lock
check_style_lock(state) -> Optional[str]
get_style_lock_image(state) -> Optional[str]
set_style_lock(state, image_url)
clear_style_lock(state)

# Scenes
get_scene_by_id(state, scene_id) -> Optional[Dict]
get_scene_for_shot(state, shot) -> Optional[Dict]
get_scene_decor_refs(state, scene) -> List[str]
get_scene_wardrobe(state, scene) -> Optional[str]
```

---

### 5. `render_service.py` (381 lines)
**Purpose:** Image generation via FAL AI.

```python
# Model Mapping
model_to_endpoint(model_key) -> str

# Text-to-Image
call_txt2img(model_key, prompt, aspect, size, num_images) -> Dict
t2i_endpoint_and_payload(state, prompt, image_size) -> Tuple[str, Dict, str]
call_t2i_with_retry(state, prompt, image_size) -> Tuple[str, str]

# Image-to-Image
call_img2img_editor(editor_key, prompt, image_urls, aspect) -> str

# Path Resolution
resolve_render_path(url_or_path) -> Path

# Shot Rendering
build_shot_prompt(state, shot) -> str
get_shot_ref_images(state, shot) -> List[str]
update_shot_render(state, shot_id, render_url, model)
get_pending_shots(state) -> List[Dict]
get_render_stats(state) -> Dict

# Prompt Building
energy_tokens(energy: float) -> List[str]
build_prompt(state, shot) -> str
```

---

### 6. `storyboard_service.py` (350 lines)
**Purpose:** Storyboard structure (sequences, shots, timeline).

```python
# Planning
target_sequences_and_shots(duration, bpm) -> Tuple[int, int]

# Sequences
create_sequence(seq_id, title, start_tc, end_tc) -> Dict
find_sequence(state, seq_id) -> Optional[Dict]
update_sequence(state, seq_id, updates) -> bool

# Shots
create_shot(shot_id, seq_id, start_tc, end_tc, prompt_base) -> Dict
find_shot(state, shot_id) -> Optional[Dict]
update_shot(state, shot_id, updates) -> bool
delete_shot(state, shot_id) -> bool
get_shots_for_sequence(state, seq_id) -> List[Dict]

# Timeline
repair_timeline(state) -> int
validate_shots_coverage(state) -> Dict

# Analysis
get_cast_coverage(state) -> Dict
```

---

### 7. `export_service.py` (299 lines)
**Purpose:** Video export and composition pipeline.

```python
# Export Pipeline
prepare_export(state) -> Dict
render_shot_to_video(shot, state) -> str
compose_final_video(state, shots) -> str
export_project(state, format) -> str

# Status Tracking
get_export_status(project_id) -> Dict
update_export_status(project_id, status, progress)

# FFmpeg Helpers
build_ffmpeg_command(inputs, output, options) -> List[str]
run_ffmpeg(command) -> bool
```

---

### 8. `llm_service.py` (200 lines)
**Purpose:** LLM API integration (Claude, OpenAI).

```python
# Constants
CLAUDE_MODEL_CASCADE = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307"
]

# JSON Extraction
extract_json_object(text) -> Optional[Dict]

# API Calls
call_openai_json(system, user, state) -> Dict
call_claude_json(system, user, state) -> Dict
call_llm_json(system, user, state, provider) -> Dict

# Prompt Management
load_prompt(name) -> str
save_llm_debug(state, prompt_type, request, response)
```

---

### 9. `styles.py` (312 lines)
**Purpose:** 55 visual style presets for consistent aesthetics.

```python
# Style Registry
STYLE_PRESETS: Dict[str, Dict] = {
    "Anamorphic Cinema": {
        "label": "Anamorphic Cinema",
        "tokens": ["anamorphic lens", "cinematic", "film grain", ...],
        "script_notes": "Classic Hollywood widescreen aesthetic..."
    },
    # ... 54 more styles
}

# Style Helpers
style_tokens(preset_key) -> List[str]
style_script_notes(preset_key) -> str
get_style_label(preset_key) -> str
list_styles() -> List[str]
get_style_options_html() -> str
```

**Style Categories:**
- Cinema (Anamorphic, Technicolor, Film Noir, Neo-Noir, ...)
- Photography (35mm, Medium Format, Polaroid, ...)
- Art Movements (Art Deco, Bauhaus, Impressionist, ...)
- Digital (Cyberpunk, Vaporwave, Glitch, ...)
- Period (70s, 80s, 90s Nostalgia, ...)
- Experimental (Dreamcore, Liminal, Abstract, ...)

---

### 10. `ui_service.py` (53 lines)
**Purpose:** Template rendering and static file helpers.

```python
# Paths
TEMPLATES_DIR: Path
STATIC_DIR: Path
INDEX_HTML_PATH: Path
STYLE_CSS_PATH: Path
APP_JS_PATH: Path
LOGO_PATH: Path

# Constants
DEFAULT_AUDIO_PROMPT: str

# Template Builders
get_style_options_html() -> str
build_index_html() -> str
get_app_js_content() -> str
get_media_type(filepath) -> str
```

---

## 🌐 API Endpoints (main.py)

### Project Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/project/create` | Create new project |
| GET | `/api/project/{id}` | Load project state |
| GET | `/api/project/{id}/validate` | Validate project |
| PATCH | `/api/project/{id}/settings` | Update settings |

### Audio Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/project/{id}/audio` | Upload & analyze audio |
| POST | `/api/project/{id}/audio/reanalyze` | Re-analyze with new prompt |
| GET | `/api/project/{id}/audio/expert` | Get audio expert data |
| POST | `/api/project/{id}/audio/expert` | Save audio expert edits |

### Storyboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/project/{id}/storyboard/generate` | Generate from audio DNA |
| POST | `/api/project/{id}/storyboard/regenerate` | Regenerate storyboard |
| POST | `/api/project/{id}/scenes/insert` | Insert new scenes |
| POST | `/api/project/{id}/scene/{scene_id}/reinvent` | Reinvent single scene |

### Shots
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/project/{id}/shots` | List all shots |
| PATCH | `/api/project/{id}/shot/{shot_id}` | Update shot |
| DELETE | `/api/project/{id}/shot/{shot_id}` | Delete shot |
| POST | `/api/project/{id}/shot/{shot_id}/render` | Render single shot |
| POST | `/api/project/{id}/shots/render-all` | Batch render shots |

### Cast
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/project/{id}/cast` | Add cast member |
| PATCH | `/api/project/{id}/cast/{cast_id}` | Update cast |
| DELETE | `/api/project/{id}/cast/{cast_id}` | Remove cast |
| POST | `/api/project/{id}/cast/{cast_id}/lock` | Lock character refs |

### Scenes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/project/{id}/scenes` | List scenes |
| POST | `/api/project/{id}/scene/{scene_id}/render` | Render scene |
| POST | `/api/project/{id}/scene/{scene_id}/wardrobe` | Generate wardrobe |

### Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/project/{id}/export` | Start export |
| GET | `/api/project/{id}/export/status` | Check export status |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/version` | Get version info |
| GET | `/api/costs` | Get session costs |
| POST | `/api/costs/reset` | Reset cost tracking |
| GET | `/api/test/claude` | Test Claude API |
| GET | `/api/test/openai` | Test OpenAI API |

---

## 🔄 Data Flow

### 1. Audio Analysis Flow
```
User uploads audio
    ↓
POST /api/project/{id}/audio
    ↓
FAL Whisper (optional) → Transcription
    ↓
Claude LLM → Audio DNA extraction
    ↓
normalize_audio_understanding()
    ↓
State updated with audio_dna
```

### 2. Storyboard Generation Flow
```
Audio DNA available
    ↓
POST /api/project/{id}/storyboard/generate
    ↓
target_sequences_and_shots(duration, bpm)
    ↓
Claude LLM + claude_generate_storyboard.txt
    ↓
Create sequences & shots
    ↓
repair_timeline()
    ↓
State updated with storyboard
```

### 3. Shot Rendering Flow
```
Shot selected for render
    ↓
POST /api/project/{id}/shot/{shot_id}/render
    ↓
build_prompt(state, shot)
    ↓
get_shot_ref_images(state, shot)
    ↓
[If refs] call_img2img_editor()
[Else]    call_t2i_with_retry()
    ↓
download_image_locally()
    ↓
update_shot_render()
    ↓
track_cost()
```

### 4. Cast Lock Flow
```
User uploads cast reference
    ↓
POST /api/project/{id}/cast
    ↓
Upload to FAL CDN
    ↓
create_cast_visual_dna()
    ↓
POST /api/project/{id}/cast/{id}/lock
    ↓
Generate ref_a, ref_b, ref_c with style
    ↓
set_character_refs()
```

---

## 📊 State Schema

### Project State (Simplified)
```json
{
  "project_id": "uuid",
  "project": {
    "title": "string",
    "style_preset": "string",
    "aspect": "horizontal|vertical|square",
    "llm": "claude|openai",
    "render_models": {
      "image_model": "fal-ai/nano-banana-pro",
      "video_model": "none"
    }
  },
  "audio_dna": {
    "title": "string",
    "bpm": 120,
    "duration": 180.5,
    "energy_curve": [...],
    "structure": [...],
    "lyrics": [...]
  },
  "cast": [
    {
      "cast_id": "uuid",
      "name": "string",
      "role": "string",
      "reference_images": [...]
    }
  ],
  "cast_matrix": {
    "character_refs": {
      "cast_id": {
        "ref_a": "url",
        "ref_b": "url", 
        "ref_c": "url"
      }
    }
  },
  "storyboard": {
    "sequences": [...],
    "shots": [...]
  },
  "costs": {
    "total_usd": 0.0,
    "breakdown": {}
  }
}
```

---

## 🔐 External Dependencies

### FAL AI
- **Audio:** `fal-ai/wizper` (transcription)
- **T2I Models:**
  - `fal-ai/nano-banana-pro` (default)
  - `fal-ai/flux-2`
  - `fal-ai/bytedance/seedream/v4.5`
- **I2I Editors:**
  - `fal-ai/nano-banana-editor`
  - `fal-ai/flux-2-kontext-editor`
  - `fal-ai/seedream/v4.5/image-to-image`

### LLM Providers
- **Claude:** Anthropic API (primary)
  - Model cascade: claude-sonnet-4 → claude-3.5-sonnet → claude-3-haiku
- **OpenAI:** GPT-4o-mini (fallback)

### Python Libraries
- FastAPI (web framework)
- fal_client (FAL AI SDK)
- requests (HTTP client)
- jsonschema (validation)
- librosa (audio analysis, optional)

---

## 📝 Version History

| Version | Description |
|---------|-------------|
| 1.7.0 | Modular architecture (11 services) |
| 1.6.9 | Service extraction (integration phase) |
| 1.6.8 | Service preparation (extraction only) |
| 1.6.6 | Bug fixes (audio expert, renders) |
| 1.6.1 | Local render storage, retry logic |
| 1.5.6 | Whisper integration, video model selection |
| 1.5.4 | Logo support, style presets expansion |

---

## 🚀 Running the Application

```powershell
# Install dependencies
pip install -r requirements.txt

# Set API keys (or use *_key.txt files)
$env:FAL_KEY = "your-fal-key"
$env:OPENAI_API_KEY = "your-openai-key"
$env:ANTHROPIC_API_KEY = "your-claude-key"

# Run server
python main.py
# or
./run.ps1

# Access UI
# http://127.0.0.1:8000
```

---

*Document generated for Fré Pathé v1.7.0*
*Architecture refactor: 3444 → 2190 lines in main.py (36% reduction)*
*Total services: 2914 lines across 11 modules*
