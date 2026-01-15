# Development Roadmap: bugfix/1.7.1-preview-player

## Branch Info
- **Created:** 2026-01-15
- **Base:** main
- **Status:** Ready for development
- **RFC:** docs/rfcs/rfc-002-preview-player-bugfix.md

## Quick Start

```powershell
# Checkout branch
git checkout bugfix/1.7.1-preview-player

# Run development server
python main.py
# Navigate to http://localhost:8000
```

## Development Tasks

### Task 1: Local-first image loading [HIGH PRIORITY]
**File:** `services/render_service.py` + `static/app.js`

**Acceptance Criteria:**
- ✅ Preview player checks local renders dir first
- ✅ API fetch only if local file missing
- ✅ No API calls for images already in `data/projects/{id}/renders/`
- ✅ Performance test: verify API call count reduction ≥ 80%

**Implementation checklist:**
```
[ ] Read render_service.py to understand get_project_renders_dir()
[ ] Audit app.js preview logic for API calls
[ ] Add local file existence check before fetch
[ ] Update preview_player.js to use local paths
[ ] Add caching layer for file list (session-based)
[ ] Test: manual preview with offline dev tools
[ ] Test: measure API call count (browser Network tab)
```

**Estimated time:** 1-2 days

---

### Task 2: Fix broken transitions [MEDIUM PRIORITY]
**Files:** `static/style.css` + `static/app.js`

**Acceptance Criteria:**
- ✅ CSS transitions apply to scene changes
- ✅ Fade, dissolve, cut all work correctly
- ✅ Timing matches specified duration
- ✅ No DOM mutation breaking transitions

**Investigation checklist:**
```
[ ] Reproduce issue: open storyboard with multiple scenes
[ ] Check Network tab: are CSS files loading?
[ ] Inspect Elements: verify transition classes applied
[ ] Search app.js for innerHTML mutations
[ ] Check: does preview use requestAnimationFrame?
[ ] Test: Chrome, Firefox DevTools
```

**Fix strategy:**
```
[ ] Replace innerHTML with classList operations (if found)
[ ] Add transition-duration to shot containers
[ ] Test all 55 style presets
[ ] Verify audio stays synced during transitions
[ ] Browser smoke test on 2+ browsers
```

**Estimated time:** 2-3 days

---

### Task 3: Debug & fix export 500 errors [HIGH PRIORITY]
**Files:** `services/export_service.py` + server logs

**Acceptance Criteria:**
- ✅ Export completes without 500 error
- ✅ Clear error messages if issues occur
- ✅ Validation checks happen before export
- ✅ Fallback codecs if primary fails

**Diagnostics first:**
```
[ ] Trigger export error (repro case)
[ ] Check server logs in data/debug/
[ ] Search for FFmpeg errors
[ ] Check file permissions on data/projects/
[ ] Test with minimal project → larger project
[ ] Inspect export_service.py error handling
```

**Fix implementation:**
```
[ ] Add pre-flight validation: check video dir writeable
[ ] Add detailed error logging (line-level)
[ ] Implement retry logic for transient failures
[ ] Add codec fallback (libx264 → libx265 → mpeg4)
[ ] Test export with various project sizes
```

**Estimated time:** 3-5 days (depends on root cause)

---

## Testing Checklist

### Unit Tests
```python
# services/test_render_service.py (new)
test_local_image_found_returns_path()
test_missing_local_image_falls_back_to_api()
test_renders_dir_caching()

# services/test_export_service.py (new)
test_export_with_valid_project()
test_export_error_handling()
test_export_validation_checks()
```

### Integration Tests
```gherkin
# browser-based
Scenario: Preview uses local images
  Given project with renders in /data/projects/{id}/renders/
  When preview loads
  Then Network tab shows 0 image API requests

Scenario: Transitions smooth on scene change
  Given 3-scene storyboard
  When clicking "Next Scene"
  Then fade/dissolve plays over 300ms

Scenario: Export succeeds
  Given valid project with all assets
  When clicking Export
  Then video file created in /data/projects/{id}/videos/
```

### Manual Smoke Tests
- [ ] Preview loads quickly (< 2 sec)
- [ ] Scene navigation smooth
- [ ] Export completes (all formats)
- [ ] Offline mode works (no API fallback needed)

---

## Code Review Checklist

Before merging to main:
- [ ] All tests passing
- [ ] No console errors in browser DevTools
- [ ] No new performance regressions
- [ ] Code follows existing patterns in codebase
- [ ] Comments explain non-obvious logic
- [ ] No API key leaks in logs

---

## Debugging Tips

### Local API calls still happening?
```javascript
// In browser DevTools Console
// Add this to trace API requests
fetch_original = window.fetch;
window.fetch = function(...args) {
  console.log("API Request:", args[0]);
  return fetch_original.apply(this, args);
};
```

### Transition not applying?
```css
/* Check if transition is being removed */
.shot-container {
  transition: opacity 0.3s ease-in-out;
}

/* Debug: make it visible */
.shot-container {
  background: red; /* temporary */
  opacity: 0;
}
```

### Export 500 error diagnostics
```python
# Add to export_service.py temporarily
import traceback
try:
    # export logic
except Exception as e:
    print(f"EXPORT ERROR: {e}")
    traceback.print_exc()  # full stack trace
    log_llm_call(f"export_error: {traceback.format_exc()}", "error")
```

---

## Resources & References

- **Architecture:** ARCHITECTURE.md (export_service.py section)
- **Current styles:** services/styles.py (55 presets)
- **Project structure:** docs/rfcs/rfc-002-preview-player-bugfix.md
- **Render logic:** services/render_service.py (line ~200+)

---

## When Ready to Merge

1. Push all commits to `bugfix/1.7.1-preview-player`
2. Create Pull Request to `main`
3. Provide test evidence (screenshots/videos of transitions, API call reduction)
4. Get review approval
5. Merge with squash commit

**PR Title:** `[BUGFIX] v1.7.1 - Preview player fixes (images, transitions, export)`

---

**Last updated:** 2026-01-15  
**Owner:** Opus 4.5  
**Status:** 🟢 Ready for development
