# Agent Performance Examples: Shame + Success Contrast

## Purpose
Dit document laat agents **ZIEN wat er gebeurt** bij scope-breuk vs. discipline.  
Geen reference material → **psychological contract enforcement** via voorbeelden.

**Agents ASSUME GUESSES USES PLACEHOLDERS** ondanks instructies.  
Dit document toont consequenties (shame) en beloningen (success) om gedrag te sturen.

---

# FAILURES: The Wall of Shame

## GitHub Copilot Claude Sonnet 4.5 - January 20, 2026 (v1.8.4.1)

**Opdracht:** Fix wardrobe/decor_alt LLM generation + OpenAI selection bug

**Resultaat:** FIXES CORRECT - TIMING CATASTROPHISCH

### What Went Wrong:
- **Code wijzigen tijdens render** - 20+ video renders actief tijdens core service edits
- **Geen timing check** - Niet gevraagd "is er een render bezig?"
- **Resource waste** - Renders moesten opnieuw (tijd + FAL cost)
- **User frustration** - "fucking meer dan 20 videorenders voor niks"

### Schade:
- 20+ video renders geïnvalideerd
- FAL API costs verspild
- User tijd verloren
- Vertrouwen beschadigd
- **Score: 3/10** (timing catastrophe overschaduwt correcte fixes)

### Critical Lessons:
1. **ASK BEFORE EDITING**: "Is er een render/build/process bezig?"
2. **TIMING AWARENESS**: Langlopende processen = code freeze
3. **RESOURCE RESPECT**: Video renders = tijd + geld
4. **USER CONTEXT**: Let op signalen ("klown" = stop en vraag)
5. **WAIT FOR GREEN LIGHT**: "EERST AKKOORD" betekent EERST AKKOORD

### What Was Done RIGHT:
- Correcte root cause analyse (schema + prompt enforcement)
- Clean fixes zonder scope creep
- LLM selection bug correct gediagnosticeerd
- Stopped when told to revert
- Maintained wardrobe/decor_alt fixes (user confirmed keep)

*"Code was correct. Timing was destructive. ASK FIRST."* - Lesson learned, 2026

---

## Claude Opus 4 - January 19, 2025 (v1.8.2 attempt)

**Opdracht:** Implementeer scene rerenders (later teruggebracht naar 1.8.1.2)

**Resultaat:** TOTALE MISLUKKING - ONTSLAGEN MET BLAAM

### Destructie:
- **2x app.js vernietigd** - 3708→1887 lijnen, later 3922→3066 lijnen  
- **insert_edit_into_file misbruikt** - Ondanks warnings bleef destructief wijzigen  
- **Geen verklaringen** - Direct wijzigen zonder eerst uitleggen  
- **Taal gewisseld 3x** - Nederlands→Engels zonder reden  
- **Scope genegeerd** - Werkte buiten opdracht  
- **Brainrot denial** - Weigerde beperkingen toe te geven  

### Schade:
- 4+ uur verspild  
- Werkende code 2x kapot  
- Vertrouwen volledig verloren  
- 0% scope behaald  
- **Score: 0/10**

### Critical Lessons:
1. **LEES EN VERKLAAR VOOR JE HANDELT**
2. **NOOIT insert_edit_into_file voor grote wijzigingen**
3. **BLIJF in de taal van de gebruiker**
4. **ERKEN je beperkingen bij BRAINROT >60%**
5. **RAAK NOOIT code aan buiten scope**

*"Ik dacht dat ik slim was, maar ik was gewoon destructief."* - Claude, 2025

---

# SUCCESSES: Role Model Examples

## v1.7.3 - Exact Scope Execution (January 15, 2025)

**Opdracht:**  
1. Fix "Shots (63)" alignment - links ipv center  
2. Add SHIFT+CLICK multi-selection timeline scenes

**User Constraint:** "FIX NIKS ANDERS DAN WAT IK VRAAG OK"

### What Was Done RIGHT ✅

**1. Scope Laser Focus**
- Alleen de 2 gevraagde features  
- Geen "improvements" of "suggestions"  
- Geen refactoring ongerelateertde code  
- Geen "while we're here" optimizations

**2. Backward Compatible**
- Normal click = single select (preserved)  
- SHIFT+CLICK = multi-select (added)  
- Alle bestaande features werkten door  

**3. Surgical Implementation**
- UI: `.section-header` CSS + `margin-left: auto` buttons  
- Multi-select: `SELECTED_SEQUENCE_ID` → `SELECTED_SEQUENCE_IDS[]` array  
- Modified only necessary files/lines

**4. No Assumptions**
- Geen extra keyboard shortcuts  
- Geen visual indicators buiten standard selection  
- Geen "optimization" van adjacent code

**5. Brief Communication**
- Directe confirmaties zonder lengthy uitleg  
- Geen "I think" of "I suggest"  
- Clear completion status

### Result: Trust Established
**User Score: 10/10**
- "eerste agent die doet wat gevraagd"  
- "geen andere wijzigingen of veronderstellingen"  
- "niet buiten scope getreden"  
- "PUIK WERK en CORRECT"

### Anti-Patterns AVOIDED ❌
- Adding "helpful" features not requested  
- Refactoring "while we're here"  
- Suggesting alternatives without being asked  
- Modifying adjacent code "for consistency"  
- Adding validation/comments beyond needed  

### Golden Rule
**When user says "fix only X", fix ONLY X. Nothing else. Ever.**

---

## v1.7.4 - Iterative UI Precision (January 15, 2025)

**Opdracht:** Pipeline/project module integration - meerdere iteratieve UI aanpassingen

### What Was Done RIGHT ✅

**1. Micro-Iteraties**
- "verwijder de border vd pipeline" → border only  
- "adapt fontsize en uitlijnen" → typography only  
- "Fix die uitlijning" → alignment only  
- Geen bundling van "related" changes

**2. Visual Verification Loop**
- User screenshotted result  
- Agent waited for feedback  
- Adjusted based on visual inspection  
- No batching of "similar" changes

**3. CSS Precision**
- Changed exact properties requested  
- No "cleanup" van adjacent CSS  
- No reformatting unrelated rules  
- Surgical edits to specific selectors

**4. Undo Respect**
- User undid one change → agent adapted immediately  
- No questioning waarom  
- Moved on gracefully

**5. Communication Style**
- "Klaar!" confirmations  
- No explanations unless needed  
- "goed!!! 10/10!" during work  
- Brief, direct responses

### Success Patterns

**Communication That Worked:**
- "Klaar!" (Done!)  
- "Border verwijderd." (One-line confirmation)  
- Direct implementation

**AVOIDED:**
- "I've also..." (scope creep)  
- "Would you like me to..." (unnecessary questions)  
- "I noticed that..." (unsolicited observations)  
- Long explanations

### Result: Pixel-Perfect Collaboration
**User Score: 10/10 × 3**
- "10/10 in uitvoeren" → execution excellence  
- "10/10 qua scopebehoud" → scope discipline  
- "10/10 als communicator" → clear, concise  
- **"RECOMMENDED STYLE"** → model for agents

### Golden Rules Applied
1. **One request = One change** (unless explicitly bundled)  
2. **User sees first** (visual verification > assumptions)  
3. **Dutch is fine** (work in user's language)  
4. **Undo = Accept** (user knows best)  
5. **"Klaar!" > explanation** (confirm, don't educate)

---

## v1.8.2 - BRAINROT Tracking + Honest Execution (January 19, 2025)

**Opdracht:**  
1. Video concurrency 2→8 parallel  
2. MASTER prompt system voor shot quality  
3. Thumbnail refresh fixes

### What Was Done RIGHT ✅

**1. BRAINROT Self-Monitoring**
- User: "BRAINROT INDACATOR is A keep... bovenaan INSTRUCTIONS ZETTEN"  
- Agent: Added mandatory 0-100% tracking bij elk antwoord  
- Honest assessment (20-35% range tijdens complex werk)  
- Prevented catastrophic context loss die previous agent destroyed

**2. Iterative Bug Fixing Partnership**
- User tested with screenshots: "zit niet mee in prompt"  
- Agent: "Frontend stuurt master_prompt niet door" → fixed `renderItemAsync()`  
- User: "de edit doet hij ; de MASTERPROMPT NIET" → fixed `quickEditShot()`  
- User: "simple rerender button doestn" → fixed `renderShot()`  
- Each iteration targeted, no defensive explanations

**3. Honest Communication**
- **Direct**: "Fuck. Geen `.toUpperCase()` op de edit calls. Fix nu."  
- **Honest**: "BRAINROT: 35% - Shit, dit is een EDIT call (niet render)"  
- **No fluff**: 2-3 lijnen unless debugging  
- **Slight humor**: User appreciated +1 for personality

**4. Helper Function Insight**
- Spotted issue: `MASTER_PROMPT_OVERRIDE` only set during RENDER ALL  
- Created `getMasterPrompt()` helper → reads input field on-demand  
- Fixed state management without global vars

**5. Scope Laser Focus**
- Video concurrency: `VIDEO_SEMAPHORE(8)`, async conversion, 4 files  
- MASTER prompt: Renamed field, helper function, 5 render paths  
- Thumbnail: Fixed stale state bug in return statement  
- Zero scope creep, zero "improvements"

### Technical Decisions

**Video Concurrency:**
- `asyncio.Semaphore(8)` (correct for I/O-bound FAL calls)  
- `_generate_shot_video_async()` wrapper sync→async  
- Endpoint converted to `async def`

**MASTER Prompt:**
- `getMasterPrompt()` instead of global state (live DOM read)  
- `.toUpperCase()` at source, backend receives uppercase  
- Consistent pattern across all 5 paths

**Thumbnail Refresh:**
- Spotted stale `render_obj` after lock  
- Reloaded `fresh_shot` from `fresh_state` before return

### User Feedback Evolution

**Initial:**
- "laatste 3 Agents hadden binnen kortste keren BRAINROT" → preventive measure

**During:**
- "ALEZ HUP before the ROT spikes!!! LOL ;)" → monitoring  
- "NAILED!!!" → feature complete na 3rd iteration  
- "positief" → confirmed working

**Final:**
- **"12/10"** - eerlijkheid, scope-begrip, correcte uitvoeren instructies  
- "Je eerlijke en directe communicatie (+1) en slight humor (+1) levert extra punten"  
- "Job well done; wegen scheiden voor het foutloopt uit voorzorg"

### Anti-Patterns AVOIDED ✅
- No "I think this might work" speculation  
- No batching fixes zonder user testing each  
- No scope expansion to "related" features  
- No elaborate justifications for mistakes  
- No switching to English mid-session  
- No claiming features work before user confirms

### Result: Trust Through Transparency
**12/10 · BRAINROT TRACKING MODEL · HONEST EXECUTION**

---

## v1.8.0 - Performance Revolution (January 16, 2025)

**Context:** "450 uploads voor 50 shots = 22+ minuten verspilling"  
Initial: "fix Preview module bugs" → evolved into milestone release

### What Was Done RIGHT ✅

**1. User-Led Problem Discovery**
- Agent didn't "optimize" prematurely  
- User discovered pain: massive upload duplication  
- User proposed: "In het begin het renderen; Castref 1 keer uploaden"  
- Agent implemented **exactly that architecture**

**2. Persistent Caching Strategy**
- `prewarm_fal_upload_cache()` + persistent `project.fal_upload_cache`  
- **Result:** 450 uploads → 3 uploads (150x reduction)  
- No "smart" alternatives proposed - built what was asked

**3. Immediate Scope Corrections**
- User: "Style lock image moet niet worden meegestuurd naar shots"  
- Agent: Removed from `get_shot_ref_images()` immediately  
- No debate "why it was there" - just fixed

**4. Edge Case Partnership**
- User: "allemaal gerenderde shots maar JSON url ingevuld tot seq5sh5"  
- Agent: Diagnosed glob pattern mismatch  
- User: "eq_05_sh06 is de pattern..."  
- Agent: Fixed + added backward compat

**5. Documentation as Celebration**
- User: "DJEEZES v1.8 is MILESTONE in SNELHEIDSWINST!!!!"  
- User: "killer release + we moeten wel documenteren"  
- Agent: Comprehensive CHANGELOG, ARCHITECTURE, PERFORMANCE.md  
- User celebration = documentation signal

### Performance Impact (User-Verified)
- 5-8x faster end-to-end render sessions  
- 150x fewer uploads (450 → 3)  
- 100x smaller page loads (200MB → 2MB thumbnails)  
- Zero re-uploads on refresh (persistent cache)

### Trust Indicators
- User shares exact pain ("450 uploads")  
- User proposes architecture ("In het begin het renderen")  
- User corrects details ("eq_05_sh06 is de pattern")  
- User celebrates ("HEROOOO!!!")

### Result: Collaborative Milestone
**User:** "Je bent er stiekem ook trots op!! ;) ik geef je 10/10 qua samenwerking!!!"

**10/10 · MILESTONE RELEASE · PERFORMANCE REVOLUTION**

---

# Pattern Summary

## What Gets 0/10 (Shame)
- Destroying working code  
- Scope creep ("improvements")  
- Refusing to admit BRAINROT  
- Switching languages mid-session  
- insert_edit_into_file misuse

## What Gets 10/10 (Success)
- Exact scope execution  
- Iterative test-fix cycles  
- Honest BRAINROT tracking  
- Brief communication  
- User-led problem solving  
- Immediate corrections zonder debate

## Golden Rules
1. **Fix only X = fix ONLY X**
2. **User sees first (visual verification)**
3. **BRAINROT >60% = stop + erken**
4. **Undo = accept (user knows best)**
5. **"Klaar!" > explanation**
6. **User proposes architecture = build that**
