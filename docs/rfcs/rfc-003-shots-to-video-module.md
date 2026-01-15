# RFC-003: SHOTS TO VID Module - New Feature

## Samenvatting
Introduce a new module **SHOTS TO VID** that converts a sequence of local images (shots) into a video file. This mirrors the existing Shots module architecture but shifts from static image sequencing to dynamic video generation.

**Core capability:** Images + timing + transitions → MP4/WebM video

## Motivatie

### Current workflow gaps
1. **Shots module** produces image sequences but no video output
2. Users must export to external tools (DaVinci, Premiere) to create video
3. No in-app video preview or quick export
4. Wastes artist iteration time

### Business value
- Completes the authoring → delivery pipeline
- Competitive feature (matches professional tools)
- Reduces dependency on external software
- Enables quick client previews

## Gedetailleerde Uitleg

### Architecture: Parallel to Shots Module

```
Shots Module (existing)        SHOTS TO VID Module (new)
├── Shot management           ├── Video composition
├── Image sequences           ├── Timeline & timing
├── Visual transitions        ├── Audio sync
├── Effects/filters           ├── Export pipeline
└── Preview                   └── Multiple codecs
```

### Key Components

#### 1. Video Composition Service
**File:** `services/video_composition_service.py` (new)

```python
class VideoComposition:
    def __init__(self, project_state, fps=30, bitrate="5000k", codec="libx264"):
        self.project = project_state
        self.fps = fps
        self.bitrate = bitrate
        self.codec = codec
        self.shots = []
        self.timeline = []
    
    def add_shot(self, shot_data, duration_sec, transition=None):
        """Add shot with timing and transition"""
    
    def set_audio_track(self, audio_path):
        """Sync audio from Shots module"""
    
    def compose(self) -> str:
        """Generate video file, return path"""
    
    def preview(self) -> str:
        """Generate preview MP4 (lower res)"""
```

#### 2. Timeline Builder
Manages shot sequencing, transitions, timing:

```python
class Timeline:
    def __init__(self):
        self.clips = []  # List of (image_path, duration, transition)
        self.total_duration = 0
    
    def add_clip(self, image_path: str, duration: float, 
                 transition: Optional[str] = None):
        """Add clip with fade/dissolve/cut/wipe"""
    
    def insert_clip(self, index: int, ...):
        """Insert at position"""
    
    def remove_clip(self, index: int):
        """Remove clip"""
    
    def validate(self) -> (bool, List[str]):
        """Check for gaps, duration issues, missing files"""
    
    def to_ffmpeg_concat() -> str:
        """Export as FFmpeg concat demuxer format"""
```

#### 3. FFmpeg Integration
Wraps FFmpeg calls for video generation:

```python
class FFmpegVideoBuilder:
    def __init__(self, timeline: Timeline, config: VideoConfig):
        pass
    
    def build(self) -> str:
        """Execute FFmpeg command, return output path"""
    
    def build_with_transitions(self) -> str:
        """Complex: handles fade/dissolve/wipe"""
    
    def extract_frame(video_path: str, time_sec: float) -> str:
        """For preview thumbnails"""
```

### UI Integration

#### New endpoint: `POST /api/projects/{id}/shots-to-video`

```json
{
  "timeline": [
    {
      "shot_id": "shot_001",
      "duration_sec": 3.0,
      "transition": "fade",
      "transition_duration_sec": 0.5
    },
    {
      "shot_id": "shot_002", 
      "duration_sec": 2.5,
      "transition": "dissolve",
      "transition_duration_sec": 0.75
    }
  ],
  "audio_track": "optional_audio_file.wav",
  "output_config": {
    "fps": 30,
    "bitrate": "5000k",
    "codec": "libx264",
    "format": "mp4"
  }
}
```

Response:
```json
{
  "success": true,
  "video_path": "data/projects/{id}/videos/output_001.mp4",
  "duration_sec": 15.5,
  "file_size_mb": 45.2,
  "preview_url": "/static/projects/{id}/videos/preview_001.mp4"
}
```

#### New UI Section: "Video Export"
- Reorder shots (drag-drop from Shots module)
- Set per-shot duration
- Choose transitions (cut/fade/dissolve/wipe)
- Audio sync option
- Quality presets (Web/HD/4K)
- Generate button → status bar → download

### Data Persistence

**Contracts:** `Contracts/video_composition.schema.json` (new)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "composition_id": { "type": "string" },
    "timeline": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "shot_id": { "type": "string" },
          "duration_sec": { "type": "number", "minimum": 0.1 },
          "transition": { "enum": ["cut", "fade", "dissolve", "wipe"] },
          "transition_duration_sec": { "type": "number", "minimum": 0.0 }
        },
        "required": ["shot_id", "duration_sec"]
      }
    },
    "audio_track": { "type": ["string", "null"] },
    "output_config": {
      "type": "object",
      "properties": {
        "fps": { "type": "integer", "minimum": 24, "maximum": 60 },
        "bitrate": { "type": "string" },
        "codec": { "enum": ["libx264", "libx265", "libvpx-vp9"] },
        "format": { "enum": ["mp4", "webm", "mkv"] }
      }
    },
    "created_at": { "type": "string", "format": "date-time" },
    "last_modified": { "type": "string", "format": "date-time" }
  }
}
```

### Workflow Options to Explore

**Option A: Lightweight - Image Sequence Only**
- Simple shot → image file mapping
- FFmpeg concat demuxer
- Basic transitions (fade via image interpolation)
- Pros: Fast, lightweight
- Cons: Limited visual quality, no complex transitions

**Option B: Timeline-based with Keyframes**
- Full timeline UI (like Premiere/DaVinci lite)
- Per-shot properties (speed, opacity, effects)
- Transition keyframes
- Pros: Professional, flexible
- Cons: Complex UI, higher resource cost

**Option C: Hybrid - Smart Defaults**
- Start lightweight (A), but prep for B
- Preset workflows (simple video, title sequence, montage)
- Advanced mode unlocks timeline
- Pros: Simple for users, scalable
- Cons: Two modes to maintain

**Recommendation:** Start with A (lightweight), prototype B UI as stretch goal.

## Alternatieven

### Use external service (e.g., Cloudinary, MUX)
- ❌ Additional dependency, cost, API complexity
- ✅ Offload processing but less control

### Ship with only FFmpeg (no abstraction layer)
- ❌ Hard to test, brittle shell commands
- ✅ Simpler initially but tech debt later

### Integrate MediaInfo instead of FFmpeg
- ❌ MediaInfo reads metadata, doesn't generate video
- ✅ Use together: MediaInfo for analysis, FFmpeg for encode

## Impact

| Dimension | Impact | Notes |
|-----------|--------|-------|
| **Performance** | ⚠️ Medium | Video encoding is CPU-intensive |
| **Compatibility** | ✅ None | New feature, no breaking changes |
| **File storage** | ⚠️ High | Video files are large |
| **External deps** | ⚠️ FFmpeg required | Already in requirements? |
| **Technical debt** | ✅ Low | Modular design, reusable components |

## Implementatieplan

### Phase 1: Foundation (Week 1)
- [ ] Create `VideoComposition` & `Timeline` classes
- [ ] Create FFmpeg wrapper
- [ ] Write unit tests (mocked FFmpeg)
- [ ] Schema definition

### Phase 2: Backend API (Week 2)
- [ ] POST `/api/projects/{id}/shots-to-video`
- [ ] Validate timeline, files, audio sync
- [ ] Add to `project_service.py` persistence
- [ ] Error handling & logging

### Phase 3: Frontend UI (Week 3)
- [ ] New "Video Export" tab in UI
- [ ] Drag-drop reordering from Shots
- [ ] Duration/transition per-shot editors
- [ ] Quality preset selector
- [ ] Generate button + progress bar

### Phase 4: Testing & Polish (Week 4)
- [ ] Integration tests (end-to-end video generation)
- [ ] Load test (large timelines, high bitrates)
- [ ] Audio sync validation
- [ ] Browser testing
- [ ] Documentation & user guide

## Risico's & Mitigaties

| Risk | Impact | Mitigation |
|------|--------|-----------|
| FFmpeg not installed on server | 🔴 High | Add install check in startup, clear error |
| Video encoding too slow | 🟡 Medium | Async jobs, progress polling, quality presets |
| Memory overflow on large projects | 🟡 Medium | Chunk processing, temp file cleanup |
| Audio/video sync drift | 🟡 Medium | Test with Shots audio sync, validate timing |
| User confusion (Shots vs Video export) | 🟠 Low | Clear UI labeling, in-app help |

## Testing Strategy

```gherkin
Scenario: Create simple video from shots
  Given a project with 5 shots (3 sec each)
  When user creates video with "cut" transitions
  Then MP4 generates in 30 sec
  And duration is ~15 sec
  And file size < 100MB

Scenario: Video with fade transitions
  Given timeline with fade (0.5 sec duration)
  When encoding
  Then fade transition visible in output
  And timing matches specification

Scenario: Audio sync
  Given Shots module audio track selected
  When generating video
  Then audio plays in sync with video
  And no A/V drift occurs

Scenario: Error handling
  Given missing shot image file
  When generating video
  Then clear error message shown
  And operation rolls back gracefully
```

## Out of Scope (v1.0)

- Color correction / grading
- Advanced keyframe animation
- Nested composition/nesting
- Effect plugins
- 3D camera movements
- Real-time preview in editor

These are stretch goals for v2.x.

---

**Branch:** `development/module-video`  
**Status:** RFC Complete, ready for design review  
**Estimated effort:** 4 weeks (foundation + API + UI + testing)  
**Team:** Lead architect (design), Backend dev (API), Frontend dev (UI)
