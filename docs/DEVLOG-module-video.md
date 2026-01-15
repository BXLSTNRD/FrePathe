# Development Roadmap: development/module-video

## Branch Info
- **Created:** 2026-01-15
- **Base:** main
- **Status:** Ready for architecture & design
- **RFC:** docs/rfcs/rfc-003-shots-to-video-module.md

## Quick Start

```powershell
# Checkout branch
git checkout development/module-video

# Run development server (with new endpoints disabled until ready)
python main.py
```

## Overview: SHOTS TO VID Module

Converts image sequences + timing + transitions → MP4/WebM video files.

**Key difference from Shots module:**
- Shots: manages static images + visual metadata
- SHOTS TO VID: renders images to video file with transitions, audio sync, timing

---

## Phase 1: Foundation & Architecture [WEEK 1]

### Task 1.1: Create service layer structure
**Files to create:**
- `services/video_composition_service.py` (main API)
- `services/timeline_builder.py` (timeline management)
- `services/ffmpeg_builder.py` (FFmpeg wrapper)

**Acceptance Criteria:**
- ✅ All classes instantiable and testable
- ✅ Unit tests for each class
- ✅ Mock FFmpeg (no real encoding yet)
- ✅ Data structures validated

**Architecture checklist:**
```
[ ] Design VideoComposition class interface
[ ] Design Timeline class interface
[ ] Design FFmpegVideoBuilder interface
[ ] Create unit test scaffolds
[ ] Add imports to services/__init__.py
[ ] Document class contracts (docstrings)
```

**Estimated time:** 2-3 days

---

### Task 1.2: Define JSON schema & contracts
**File to create:**
- `Contracts/video_composition.schema.json` (new)
- Update `Contracts/project_state.schema.json` (add video compositions)

**Schema structure:**
```json
{
  "compositions": [
    {
      "composition_id": "comp_001",
      "timeline": [
        {
          "shot_id": "shot_001",
          "duration_sec": 3.0,
          "transition": "fade",
          "transition_duration_sec": 0.5
        }
      ],
      "output_config": {
        "fps": 30,
        "bitrate": "5000k",
        "codec": "libx264",
        "format": "mp4"
      }
    }
  ]
}
```

**Acceptance Criteria:**
- ✅ Schema validates valid compositions
- ✅ Schema rejects invalid transitions
- ✅ Test: validate_against_schema() works
- ✅ Added to project_service validation

**Checklist:**
```
[ ] Write video_composition.schema.json
[ ] Update project_state.schema.json
[ ] Add schema to Contracts/__init__.py
[ ] Write schema validation tests
[ ] Test: validate_project_state() includes videos
```

**Estimated time:** 1-2 days

---

## Phase 2: Backend API Development [WEEK 2]

### Task 2.1: Implement service classes
**Files:** `services/video_composition_service.py` + others

**Acceptance Criteria:**
- ✅ VideoComposition class: full implementation
- ✅ Timeline class: add/insert/remove/validate operations
- ✅ FFmpegVideoBuilder class: command generation (mocked execution)
- ✅ Unit tests: ≥ 80% coverage

**Implementation checklist:**
```
[ ] VideoComposition.__init__()
[ ] VideoComposition.add_shot()
[ ] VideoComposition.set_audio_track()
[ ] VideoComposition.validate()
[ ] Timeline.add_clip()
[ ] Timeline.insert_clip()
[ ] Timeline.remove_clip()
[ ] Timeline.validate()
[ ] Timeline.to_ffmpeg_concat()
[ ] FFmpegVideoBuilder.build() [mocked]
[ ] FFmpegVideoBuilder.build_with_transitions() [mocked]
[ ] Write unit tests for all methods
```

**Estimated time:** 3-4 days

---

### Task 2.2: Create API endpoints
**File:** `main.py` (new endpoints)

**Endpoints to add:**
```
POST   /api/projects/{project_id}/video-compositions
GET    /api/projects/{project_id}/video-compositions
GET    /api/projects/{project_id}/video-compositions/{comp_id}
PATCH  /api/projects/{project_id}/video-compositions/{comp_id}
DELETE /api/projects/{project_id}/video-compositions/{comp_id}
POST   /api/projects/{project_id}/video-compositions/{comp_id}/generate
```

**Acceptance Criteria:**
- ✅ All endpoints return proper HTTP responses
- ✅ Validation errors return 400 with details
- ✅ Permissions checked (project ownership)
- ✅ Compositions persist to project file

**Implementation checklist:**
```
[ ] Create route: POST /api/projects/{id}/video-compositions
    - Validate input against schema
    - Save to project file
    - Return 201 Created

[ ] Create route: GET /api/projects/{id}/video-compositions
    - List all compositions
    - Return 200 with array

[ ] Create route: PATCH /api/projects/{id}/video-compositions/{comp_id}
    - Update timeline/config
    - Validate changes
    - Persist

[ ] Create route: POST /api/projects/{id}/video-compositions/{comp_id}/generate
    - Trigger video encoding (async job)
    - Return job ID for polling

[ ] Add error handling & logging
[ ] Test endpoints with curl/Postman
```

**Estimated time:** 2-3 days

---

### Task 2.3: FFmpeg integration & video generation
**File:** `services/ffmpeg_builder.py`

**Acceptance Criteria:**
- ✅ FFmpeg wrapper calls real FFmpeg (if installed)
- ✅ Generates valid MP4 with basic cuts (no transitions yet)
- ✅ Error handling for missing/corrupt files
- ✅ Progress tracking (frame count vs total)

**Implementation checklist:**
```
[ ] Check FFmpeg installed at startup
[ ] Add FFmpeg binary detection (Windows .exe path)
[ ] Implement concat demuxer format generation
[ ] Implement basic FFmpeg command builder
[ ] Test: generate video with 3 shots, 2 sec each
[ ] Add error handling & retry logic
[ ] Implement progress callback
[ ] Test: various image formats (PNG, JPEG, WebP)
```

**Estimated time:** 2-3 days

---

## Phase 3: Frontend UI [WEEK 3]

### Task 3.1: Add "Video Export" section to UI
**File:** `templates/index.html` + `static/app.js`

**UI Components to add:**
- Tabs: "Shots" | "Video Export" | "Settings" (reorganize)
- Shot list with drag-drop reordering
- Per-shot duration editor
- Per-shot transition selector (dropdown)
- Audio track selector (from Shots module)
- Quality preset selector (Web 720p / HD 1080p / 4K)
- Generate button + progress bar
- Download link after completion

**Acceptance Criteria:**
- ✅ Tab navigation works
- ✅ Drag-drop reordering functional
- ✅ Form inputs validated client-side
- ✅ Progress bar updates during encoding
- ✅ Download link appears when ready

**HTML structure:**
```html
<div id="video-export-tab" style="display:none;">
  <h2>Video Export</h2>
  
  <div id="shot-timeline">
    <!-- Drag-drop shot list will render here -->
  </div>
  
  <div id="video-settings">
    <label>Audio Track:
      <select id="audio-select">
        <option value="">None</option>
        <!-- Shots audio options populate here -->
      </select>
    </label>
    
    <label>Quality:
      <select id="quality-preset">
        <option value="web">Web (720p, ~15MB)</option>
        <option value="hd" selected>HD (1080p, ~45MB)</option>
        <option value="4k">4K (2160p, ~150MB)</option>
      </select>
    </label>
  </div>
  
  <button id="generate-video-btn">Generate Video</button>
  <div id="progress-container" style="display:none;">
    <progress id="encode-progress"></progress>
    <span id="progress-text">0%</span>
  </div>
</div>
```

**JavaScript checklist:**
```
[ ] Fetch Shots module data
[ ] Render shot list with duration inputs
[ ] Implement drag-drop reordering
[ ] Transition dropdown with 4 options (cut/fade/dissolve/wipe)
[ ] Quality preset selector
[ ] Audio track selector from Shots
[ ] Generate button click handler
[ ] POST to /api/projects/{id}/video-compositions
[ ] Start polling /api/projects/{id}/videos/{job_id}/status
[ ] Update progress bar
[ ] Show download link when complete
```

**Estimated time:** 3-4 days

---

### Task 3.2: Styling & UX polish
**File:** `static/style.css`

**Elements to style:**
- Shot timeline container (visual card layout)
- Duration input (spinner control)
- Transition selector (dropdown with preview icons)
- Progress bar (animated)
- Download button (CTA styling)
- Responsive layout (mobile-friendly)

**Checklist:**
```
[ ] Add CSS classes for new UI sections
[ ] Style shot cards (thumbnail, duration, transition)
[ ] Style progress bar (animated green fill)
[ ] Add hover states & feedback
[ ] Test responsive: desktop, tablet, mobile
[ ] Match existing design system (colors, fonts)
```

**Estimated time:** 1-2 days

---

## Phase 4: Testing & Polish [WEEK 4]

### Task 4.1: Integration testing
**What to test:**
```gherkin
Scenario: Create and generate simple video
  Given a project with 5 shots
  When user drags shots to Video Export
  And sets duration to 2 sec per shot
  And clicks Generate
  Then MP4 created in data/projects/{id}/videos/
  And playable in browser

Scenario: Transition effects work
  Given shots with fade transitions (0.5 sec)
  When video generates
  Then fade visible in output MP4

Scenario: Audio sync
  Given Shots module audio selected
  When video generates
  Then audio plays in sync with video
  And no drift detected
```

**Checklist:**
```
[ ] Write integration test script
[ ] Test: generate video (no transitions)
[ ] Test: generate video (with transitions)
[ ] Test: audio sync validation
[ ] Test: quality presets produce different sizes
[ ] Test: error cases (missing files, FFmpeg fail)
[ ] Load test: large timeline (50+ shots)
```

**Estimated time:** 2-3 days

---

### Task 4.2: Performance optimization
**What to measure:**
- Video generation time for various project sizes
- Memory usage during encoding
- Disk I/O efficiency

**Optimizations:**
```
[ ] Implement async encoding (don't block API)
[ ] Add progress polling (browser can track status)
[ ] Cleanup temp files after encoding
[ ] Implement codec-specific optimizations
[ ] Cache thumbnail generation
```

**Estimated time:** 2 days

---

### Task 4.3: Documentation & user guide
**Files to create:**
- `docs/GUIDE-video-export.md` (user guide)
- Inline code comments (complex sections)
- Docstrings (all public methods)

**Content:**
```markdown
# Video Export Guide

## Quick Start
1. Go to Video Export tab
2. Drag shots from Shots module
3. Set timing & transitions
4. Click Generate
5. Download MP4

## Transition Types
- Cut: Instant change (0 duration)
- Fade: Crossfade between shots
- Dissolve: Soft blend
- Wipe: Directional transition

## Quality Presets
[table of specs]

## Troubleshooting
- Video won't generate: Check FFmpeg installed
- Slow encoding: Try lower bitrate
- Sync issues: Check audio file format
```

**Estimated time:** 1 day

---

## Design Decisions to Validate

### 1. Transition complexity
**Question:** Do we support all 4 transitions in v1.0?

**Options:**
- A) Start with "cut" only (simple, fast)
- B) Support all 4 (complex, image interpolation needed)
- C) Hybrid: cut/fade (simple), dissolve/wipe as stretch goal

**Recommendation:** Start with A, extend to B if time permits.

---

### 2. Timeline UI model
**Question:** Simple list vs timeline scrubber?

**Options:**
- A) Simple list (shot card with duration input)
- B) Visual timeline (REAPER/DaVinci style scrubber)
- C) Waveform + timeline (audio visible, hard)

**Recommendation:** A (ship v1.0), B as stretch goal for v1.1.

---

### 3. Async job handling
**Question:** How to track long-running encodes?

**Options:**
- A) WebSocket for real-time updates
- B) HTTP polling (simpler, less efficient)
- C) Job ID returned, user checks later (simplest)

**Recommendation:** B (simple polling, adequate for now).

---

## Deployment Notes

### FFmpeg dependency
Ensure FFmpeg installed on server:
```powershell
# Windows
choco install ffmpeg

# Linux
apt-get install ffmpeg

# macOS
brew install ffmpeg
```

Add to startup checks:
```python
# main.py
if not check_ffmpeg_installed():
    logger.warning("FFmpeg not found. Video export will be disabled.")
```

---

## Out of Scope (Stretch Goals)

- 3D transitions
- Color grading per shot
- Keyframe animations
- Real-time preview
- HDR support
- Multi-layer composition

These are v2.x features.

---

## Success Metrics

By end of Phase 4:
- ✅ Video generates from shot sequence
- ✅ All 4 transitions work (or documented why not)
- ✅ Audio syncs correctly
- ✅ < 5% of encodes fail
- ✅ Performance: 30 shots @ 1080p encodes in < 5 min
- ✅ No major bugs reported in test

---

## Debugging & Dev Tools

### Inspect FFmpeg command
```python
# ffmpeg_builder.py - add debug output
print(f"DEBUG: FFmpeg command: {' '.join(cmd)}")
```

### Monitor video generation
```python
# Watch temp files being written
import subprocess
subprocess.Popen(["powershell", "while($true) { ls data\\projects\\{id}\\videos; sleep 1 }"])
```

### Test quick generate
```bash
# Generate minimal video (10 sec, 2 shots, 480p)
curl -X POST http://localhost:8000/api/projects/test-proj/video-compositions/comp1/generate \
  -H "Content-Type: application/json" \
  -d '{"fps": 24, "bitrate": "2000k"}'
```

---

## When Ready to Merge

1. Push all commits to `development/module-video`
2. Create Pull Request to `main`
3. Provide:
   - Test video MP4 (sample output)
   - Performance metrics
   - Browser test evidence
4. Get review approval
5. Merge with squash commit

**PR Title:** `[FEATURE] New SHOTS TO VID module - Image-to-video export pipeline`

---

**Last updated:** 2026-01-15  
**Owner:** Opus 4.5 (architecture & design)  
**Status:** 🟢 Ready for Phase 1 (foundation)
