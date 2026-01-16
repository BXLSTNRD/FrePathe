# Fré Pathé v1.8.1 - Img2Vid Module Release

**Release Date:** January 16, 2026  
**Branch:** `Img2Vid---Integration`

## 🎬 Major Features

### Image-to-Video Generation (Img2Vid)
Complete AI-powered video generation pipeline transforming static rendered shots into animated video clips.

**Supported Models:**
- **Wan v2.6** - Cost-effective, 4-15s duration, 720p/1080p ($0.15)
- **LTX-2 19B** - Fast generation with audio support, 3-10s ($0.10)
- **Kling v2.6 Pro** - Cinematic quality, 5-10s with audio ($0.25)
- **Veo 3.1** - Google SOTA, 5-8s ($0.20)

**Features:**
- ✅ Per-shot video generation with "🎬 GEN VIDEO" button
- ✅ Batch video generation for all shots
- ✅ Intelligent motion prompts from shot metadata (camera language, energy, environment)
- ✅ Local video storage in project folders
- ✅ Video model selection in PROJECT settings (persistent)
- ✅ FAL upload cache integration
- ✅ Video statistics tracking

## 🔧 Backend Changes

### New Services
- **`services/video_service.py`** (456 lines)
  - `call_img2vid()` - Core FAL API integration
  - `generate_shot_video()` - Single shot video generation
  - `generate_videos_for_shots()` - Batch processing
  - `build_shot_motion_prompt()` - AI prompt generation from metadata
  - `upload_image_to_fal()` - Image upload with cache
  - `list_video_models()` - Model discovery
  - Model-specific parameter handling (Wan, LTX-2, Kling, Veo)

### Updated Services
- **`services/config.py`**
  - Added FAL img2vid endpoints (4 models)
  - Video model pricing configuration
  - Model-to-endpoint mappings

- **`services/export_service.py`**
  - `export_video_with_img2vid()` - Export pipeline with video clips
  - FFmpeg concatenation of generated videos

- **`services/__init__.py`**
  - Exported video_service functions

### API Endpoints
- `GET /api/video/models` - List available video models
- `POST /api/project/{id}/video/generate-shot` - Generate single shot video
- `POST /api/project/{id}/video/generate-batch` - Batch generation
- `POST /api/project/{id}/video/export-img2vid` - Export with video clips

## 🎨 Frontend Changes

### UI Components
- **Video Model Dropdown** (PROJECT tab)
  - 4 FAL models + "None (Preview Only)"
  - Auto-save selection to project state
  
- **ANIMATE Section**
  - "GENERATE ALL VIDEOS" button with batch processing
  - Stop button for queue management
  - Progress tracking and status updates

- **Shot Cards**
  - "🎬 GEN VIDEO" button per rendered shot
  - Video status badge: "✓ VIDEO (Xs)"
  - Conditional rendering (button → badge after generation)

- **VIDEO Section**
  - "EXPORT ANIMATED" button for img2vid export
  - Video statistics display

### JavaScript Functions
- **`static/app.js`**
  - `generateAllVideos()` - Batch generation workflow
  - `generateShotVideo()` - Core generation logic
  - `generateShotVideoUI()` - UI wrapper with validation
  - `exportVideoImg2Vid()` - Export handler
  - `updateVideoStats()` - Statistics tracking
  - Video model auto-save on change

## 🐛 Bug Fixes

### Critical Fixes
1. **Aspect Ratio Mapping**
   - Fixed: Project uses `aspect: "horizontal/vertical/square"`
   - Maps to FAL formats: `16:9`, `9:16`, `1:1`
   - Location: `video_service.py` line 280

2. **Wan v2.6 API Parameters**
   - Fixed: `duration` must be string ("5", "10", "15"), not int
   - Fixed: `resolution` uses "720p"/"1080p", not aspect ratios
   - Location: `video_service.py` lines 177-182

3. **Image Upload Path Conversion**
   - Fixed: `/files/` URLs converted to absolute paths using `PATH_MANAGER.from_url()`
   - Ensures FAL can read local image files
   - Location: `video_service.py` lines 88-94

4. **Video Download Without Thumbnails**
   - Fixed: Videos downloaded directly without thumbnail generation
   - Prevents "cannot identify image file" errors
   - Custom download logic replacing `download_image_locally()`
   - Location: `video_service.py` lines 301-322

5. **Duplicate Video Button**
   - Removed: Duplicate "🎬 VIDEO" and "🎬 GEN VIDEO" buttons
   - Single button per shot card
   - Location: `app.js` lines 2335-2340

## 📊 Data Structure

### Shot Video Object
```json
{
  "render": {
    "image_url": "/files/projects/.../renders/shot.png",
    "video": {
      "video_url": "/files/projects/.../video/video_shot.mp4",
      "local_path": "C:/FrePathe/data/projects/.../video/video_shot.mp4",
      "duration": 5.0,
      "model": "wan_i2v",
      "has_audio": false,
      "generated_at": "2026-01-16T...",
      "motion_prompt": "..."
    }
  }
}
```

### Project Settings
```json
{
  "project": {
    "video_model": "wan_i2v",
    "fal_upload_cache": {
      "/files/...": "https://v3b.fal.media/..."
    }
  }
}
```

## ⚡ Performance

- **Upload Cache:** Reuses FAL CDN URLs to avoid re-uploading images
- **Timeout:** 300s for video generation (matching render_service pattern)
- **Local Storage:** Videos saved in project folders for offline access
- **Queue System:** Max 2 concurrent generations to respect FAL rate limits

## 📝 Motion Prompt Generation

Automatically builds intelligent prompts from shot metadata:
- **Camera Language:** Pan, zoom, tracking, static shots
- **Energy Level:** Dynamic (>0.7) vs subtle (<0.3) motion
- **Environment:** Setting/location context
- **Symbolic Elements:** First 2 elements for thematic consistency
- **Default:** "Natural cinematic motion, smooth camera movement"

## 🔄 Migration Notes

- No database migrations required
- Video model selection defaults to empty (user must select)
- Existing projects compatible (video generation is opt-in)
- FAL_KEY environment variable required for video generation

## 🧪 Testing

- ✅ Single shot video generation
- ✅ FAL upload with cache
- ✅ Local video download
- ✅ Video model persistence
- ✅ Wan v2.6 API integration
- ⏳ Batch generation (ready, needs user testing)
- ⏳ Other models (LTX-2, Kling, Veo - needs testing)
- ⏳ Export with video clips (implemented, needs testing)

## 📚 Documentation

- `IMG2VID_IMPLEMENTATION.md` - Complete implementation guide
- `Builders/promptbuilder_spec.md` - Motion prompt builder specs
- Inline code documentation in `video_service.py`

## 🎯 Known Limitations

- Video generation requires FAL_KEY environment variable
- Models have different duration ranges (respect limits)
- Audio support varies by model (Wan/Veo: no audio, LTX-2/Kling: audio)
- No video preview in UI yet (download only)
- Thumbnail generation not implemented for video files

## 🚀 Next Steps

1. Test batch video generation workflow
2. Verify LTX-2, Kling, Veo model parameters
3. Test export with video clip concatenation
4. Add video preview/playback in UI
5. Implement video thumbnails (first frame extraction)
6. Add progress indicators for long generations

---

**Total Changes:**
- 3 new files
- 6 modified files
- ~600 lines of new code
- 4 API endpoints
- 8 new JavaScript functions
