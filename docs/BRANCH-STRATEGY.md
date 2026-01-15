# Branch Strategy & Development Overview

**Created:** 2026-01-15  
**Scope:** Two parallel branches from main (v1.7.0)

---

## 📋 Branch Status Summary

| Branch | Type | Status | RFC | Owner | ETA |
|--------|------|--------|-----|-------|-----|
| `bugfix/1.7.1-preview-player` | Bugfix | 🟢 Ready | RFC-002 | Opus 4.5 | 1 week |
| `development/module-video` | Feature | 🟢 Ready | RFC-003 | Opus 4.5 | 4 weeks |

---

## 🚀 Quick Branch Checkout

```powershell
# Bugfix branch
git checkout bugfix/1.7.1-preview-player

# Feature branch
git checkout development/module-video

# Return to main
git checkout main
```

---

## 1️⃣ BUGFIX: Preview Player (v1.7.1)

### What's broken?
1. **API waste:** Preview loads images via HTTP when they're locally available
2. **Broken transitions:** Fade/dissolve not working on scene changes
3. **Export crashes:** 500 errors on video export

### Impact
🔴 **Blocks user workflow** - must be priority 1

### Timeline
- **Duration:** 5-7 days
- **Complexity:** Medium (debugging required)
- **Risk:** Low (localized fixes)

### Development tasks
```
Phase 1: Local-first image loading (2 days)
Phase 2: Fix transitions (2 days)  
Phase 3: Debug export errors (3 days, includes diagnostics)
Testing: 1 day
```

### Success criteria
✅ No API calls for images in local renders dir  
✅ Transitions smooth & on-time  
✅ Export completes without 500 error  

### Files to modify
- `services/render_service.py`
- `static/app.js`
- `static/style.css`
- `services/export_service.py`

**Full roadmap:** `docs/DEVLOG-bugfix-1.7.1.md`

---

## 2️⃣ FEATURE: SHOTS TO VID Module

### What is it?
New module: Images + timing + transitions → MP4 video file

Similar to Shots module, but renders to video instead of static image sequences.

### Why?
- Completes authoring → delivery pipeline
- No external tool dependency
- Competitive feature
- Quick client previews

### Timeline
- **Duration:** 4 weeks
- **Complexity:** High (new service layer)
- **Risk:** Medium (FFmpeg dependency)

### Development phases
```
Week 1: Foundation (services, schema, tests)
Week 2: Backend API (endpoints, FFmpeg wrapper)
Week 3: Frontend UI (timeline editor, generate button)
Week 4: Testing, polish, documentation
```

### Success criteria
✅ Generate valid MP4 from image sequence  
✅ Transitions work (cut, fade, dissolve, wipe)  
✅ Audio sync with video  
✅ Performance: 30 shots @ 1080p in < 5 min  

### New files to create
```
services/video_composition_service.py
services/timeline_builder.py
services/ffmpeg_builder.py
Contracts/video_composition.schema.json
docs/GUIDE-video-export.md
```

**Full roadmap:** `docs/DEVLOG-module-video.md`

---

## 🔀 Branch Strategy

### Parallel development
Both branches work independently on different modules:
- **bugfix/1.7.1** → fixes existing issues
- **development/module-video** → new feature

No conflicts expected (separate codebases).

### Merge sequence
```
1. bugfix/1.7.1-preview-player → main (Week 1)
   └─ v1.7.1 released

2. development/module-video → main (Week 5)
   └─ v1.8.0 released (with SHOTS TO VID)
```

---

## 📚 Documentation Structure

```
docs/
├── rfcs/
│   ├── rfc-002-preview-player-bugfix.md       (Problem + Solution)
│   └── rfc-003-shots-to-video-module.md       (Design + Architecture)
├── DEVLOG-bugfix-1.7.1.md                     (Dev tasks + checklist)
├── DEVLOG-module-video.md                     (Phase breakdown)
└── GUIDE-video-export.md                      (User guide - created Week 4)
```

### How to read the docs
1. **Overview:** This file (you are here)
2. **RFC (detailed problem/solution):**
   - RFC-002 for bugfix context
   - RFC-003 for feature design
3. **Development roadmap:**
   - DEVLOG-bugfix-1.7.1.md (tasks + checklists)
   - DEVLOG-module-video.md (phase breakdown)

---

## 🎯 For Claude Opus 4.5

### Development approach
1. **Read RFC first** → understand scope & design
2. **Follow DEVLOG checklist** → break into sub-tasks
3. **Commit incrementally** → frequent, descriptive commits
4. **Test continuously** → unit + integration tests
5. **Document as you go** → keep DEVLOG updated

### Code standards
- Follow existing patterns in `services/`
- Use docstrings (all public methods)
- Add comments for complex logic
- Unit test coverage ≥ 80%
- Validate against schemas

### Debugging resources
Each DEVLOG section includes:
- Debugging tips (curl commands, dev tools)
- Code references (which files to modify)
- Test scenarios (what to verify)

---

## 🧪 Testing Strategy

### Bugfix (v1.7.1)
```
Manual smoke tests:
  - Preview loads without API calls
  - Transitions smooth on scene change
  - Export completes successfully
```

### Feature (module-video)
```
Unit tests:
  - Services layer (composition, timeline, FFmpeg)
  
Integration tests:
  - API endpoints return correct responses
  - Video generates from timeline
  - Audio syncs with video
  
Manual testing:
  - UI drag-drop works
  - Quality presets produce correct sizes
  - Progress bar updates during encode
```

---

## 📦 Dependencies

### Existing
- FastAPI (main.py)
- Python 3.8+
- Schema validation (jsonschema)

### New (for module-video)
- **FFmpeg** (required for video encoding)
  - Check installed: `ffmpeg -version`
  - Install: `choco install ffmpeg` (Windows) or `brew install ffmpeg` (macOS)

---

## 🚨 Risk Mitigation

### Bugfix (v1.7.1)
| Risk | Mitigation |
|------|-----------|
| Breaking changes | Localized changes only, no API changes |
| Performance regression | Measure API calls before/after |
| Export still broken | Detailed logging to identify root cause |

### Feature (module-video)
| Risk | Mitigation |
|------|-----------|
| FFmpeg not installed | Startup check, clear error message |
| Slow video encoding | Async jobs + progress polling |
| Audio/video sync drift | Test with actual audio files |
| Memory overflow | Chunk processing for large files |

---

## 📞 For User Onboarding (VSCode Tips)

Since you're new to VSCode branch workflows:

### Switch branches safely
```powershell
# See current branch
git branch

# Switch to another
git checkout bugfix/1.7.1-preview-player

# Switch back
git checkout main
```

### Avoid common mistakes
❌ Don't commit to main by accident  
→ Always check `git status` first  
→ VSCode shows branch in bottom-left corner

❌ Don't lose local changes  
→ Commit or stash before switching branches  
→ `git stash` if unsure

✅ Safe workflow:
```powershell
git status                          # Check clean
git checkout bugfix/1.7.1-preview-player
# ... make changes, test ...
git add .
git commit -m "descriptive message"
git push origin bugfix/1.7.1-preview-player
```

---

## 📅 Next Steps

### Immediate (Today)
- ✅ Branches created (bugfix/1.7.1, development/module-video)
- ✅ RFCs written (RFC-002, RFC-003)
- ✅ Development roadmaps prepared (DEVLOG files)
- 👉 **Opus 4.5:** Review RFCs & roadmaps, ask clarifications if needed

### Week 1: Bugfix sprint
- Opus 4.5 starts bugfix development
- Run tests continuously
- Update DEVLOG with progress
- Commit to branch regularly

### Week 2-4: Feature sprint
- Opus 4.5 starts module-video Phase 1
- Parallel to bugfix (if bugfix not merged yet)
- Follow phase breakdown in DEVLOG-module-video.md

### Week 5+: Merge & release
- bugfix/1.7.1 → main (v1.7.1 release)
- development/module-video → main (v1.8.0 release)

---

## 📄 Document Links

| Document | Purpose |
|----------|---------|
| `rfc-002-preview-player-bugfix.md` | Problem analysis + solution design |
| `rfc-003-shots-to-video-module.md` | Feature architecture + workflow options |
| `DEVLOG-bugfix-1.7.1.md` | Dev tasks, checklist, debugging tips |
| `DEVLOG-module-video.md` | Phase breakdown, implementation details |
| `GUIDE-video-export.md` | User guide (created Week 4) |

---

**Status:** 🟢 All branches & docs ready  
**Next action:** Opus begins development  
**Contact:** Review RFCs or DEVLOG if questions
