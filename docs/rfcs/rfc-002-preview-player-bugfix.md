# RFC-002: Preview Player - Bugfixes v1.7.1

## Samenvatting
Deze RFC stelt drie kritieke bugs voor in de preview player die de UX ernstig beperken:
1. **Redundante API-calls**: Player haalt images op via API terwijl deze lokaal beschikbaar zijn
2. **Transitions breken**: Transition-effecten werken niet correct
3. **Export failures**: 500-errorcodes bij export-operaties

## Motivatie
De preview player is een kritiek onderdeel van het authoring-experience. Deze bugs:
- Verslaan performance (onnodig network overhead)
- Breken de visuele flow (transitions)
- Maken export onbetrouwbaar (crashes/errors)

Dit verhindert productief werk en moet Priority 1 zijn.

## Gedetailleerde Uitleg

### 1. Redundante API-calls voor lokale images
**Probleem:** Player maakt HTTP requests naar images die al in `project/renders/` beschikbaar zijn.

**Impact:**
- Extra latency (network roundtrip)
- Wastes API quota
- Fails offline mode
- Unnecessary bandwidth

**Workaround gelijk:** Controleer `get_project_renders_dir()` voordat externe fetch
- Prioriteit: lokale file > API fallback
- Cache bestandslijsten per sessie

**Technische aanpak:**
```python
# render_service.py / preview logic
def get_image_path(shot_id, project_id, image_data):
    # 1. Check local renders directory first
    local_path = get_project_renders_dir(state) / f"{shot_id}_render.png"
    if local_path.exists():
        return str(local_path)
    
    # 2. Fallback to API URL only if not local
    return image_data.get('url')
```

### 2. Transitions breken
**Probleem:** CSS/JavaScript transitions in preview niet toepast op scene-switches.

**Symptomen:**
- Abrupte scene changes (geen fade/dissolve)
- Timing bugs (transition sneller dan expected)
- Looping issues bij auto-play

**Oorzaak:** Waarschijnlijk DOM manipulation die CSS transitions negeerd.

**Fix-strategy:**
- Audit `app.js` preview render logic
- Zoek naar `innerHTML` mutations → vervang door class toggles
- Voeg `transition-duration` properties toe aan shot containers
- Test met alle transition presets

### 3. 500-errors bij export
**Probleem:** Export-endpoint crashes met 500-errors.

**Waarschijnlijke oorzaken:**
- File permission issues (`get_project_video_dir()` onbereikbaar?)
- Memory overflow (large video files)
- FFmpeg/codec errors
- Null pointer bij video metadata

**Diagnostics vereist:**
- Check `export_service.py` error handling
- Inspect server logs (`debug/` folder)
- Test export met minimal project

**Implementatieplan:**
1. Better error messages (specifieke errors loggen)
2. Validate video dir antes export start
3. Memory management voor large files
4. FFmpeg fallback codecs

## Alternatieven

### Lazy-load images (vs local-first)
- ❌ Hierbij gaan we gewoon network-first aanhouding
- ✅ Local-first respects offline mode en is sneller

### Remove transitions entirely
- ❌ Negated UX quality
- ✅ Fix them properly

### Disable export feature
- ❌ Fundamenteel broken user workflow
- ✅ Fix root causes

## Impact

- **Performance**: ✅ Significantly improved (fewer API calls, faster preview)
- **Compatibility**: ✅ No breaking changes
- **Offline mode**: ✅ Now functional
- **Technical debt**: ⚠️ May reveal other file-path issues

## Implementatieplan

### Phase 1: Local-first image loading (Low risk, high impact)
1. Modify `preview_player` logic in `app.js`
2. Add local file existence check
3. Unit test: verify local paths used when available
4. Load test: measure API call reduction

### Phase 2: Transition fixes (Medium risk)
1. Audit transition CSS in `style.css`
2. Fix DOM mutation patterns in `app.js`
3. Test with all 55 styles
4. Browser-test (Chrome, Firefox)

### Phase 3: Export error handling (High risk - requires debugging)
1. Add detailed logging to `export_service.py`
2. Add validation checks before export
3. Test export with minimal → large projects
4. Implement fallback codecs

## Testplan

```gherkin
Scenario: Preview loads images locally first
  Given a project with renders in /data/projects/{id}/renders/
  When preview opens a shot
  Then no API calls for images
  And images load instantly

Scenario: Transitions work smoothly
  Given a multi-scene storyboard
  When transitioning between scenes
  Then fade/dissolve plays (based on preset)
  And timing matches specified duration

Scenario: Export succeeds without 500 error
  Given a valid project
  When export is initiated
  Then video file generates successfully
  And no 500 error occurs
```

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Local file sync issues | Verify renders dir consistency in save_project() |
| Transition timing breaks audio sync | Test A/V sync after changes |
| Export regression on other formats | Test all export presets |

## Feedback

**Questions to resolve:**
- Is the 500 error consistent or intermittent?
- Are transitions broken for all styles or specific ones?
- What's the typical size of projects experiencing export failure?

---

**Branch:** `bugfix/1.7.1-preview-player`  
**Status:** Ready for implementation  
**Estimated effort:** 3-5 days (depends on export diagnostics)
