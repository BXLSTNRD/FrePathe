# Agent Instructions & Best Practices

## Role Model Example: v1.7.3 Implementation (2026-01-15)

### Context
User requested two specific changes:
1. Fix "Shots (63)" alignment - move from center to left next to collapse button
2. Add SHIFT+CLICK multi-selection for timeline scenes

### What Was Done RIGHT ✅

#### 1. **Exact Scope Adherence**
- User explicitly stated: "FIX NIKS ANDERS DAN WAT IK VRAAG OK"
- Only the two requested features were implemented
- No "improvements" or "suggestions" added
- No refactoring of unrelated code

#### 2. **Targeted Implementation**
- **UI Fix**: Changed `.section-header` CSS and added `margin-left: auto` to buttons
- **Multi-selection**: Converted `SELECTED_SEQUENCE_ID` → `SELECTED_SEQUENCE_IDS` array
- Modified only the files and lines necessary for the requested functionality

#### 3. **Preserved Existing Behavior**
- Normal click still selects single scene (backward compatible)
- SHIFT+CLICK adds new multi-select capability
- No changes to other selection mechanisms
- All existing features continued working

#### 4. **No Assumptions**
- Did not add keyboard shortcuts beyond what was requested
- Did not add visual indicators beyond standard selection
- Did not modify related but unmentioned features
- Did not "optimize" or "clean up" adjacent code

#### 5. **Proper Versioning**
- Updated version to 1.7.3 (as requested: 2x in HTML)
- Added complete CHANGELOG entry with all changes
- Documented technical changes clearly

#### 6. **Communication**
- Brief confirmations without lengthy explanations
- No "I think" or "I suggest" statements
- Direct implementation without asking permission
- Clear final confirmation of completion

### Key Principles Demonstrated

1. **Listen First**: User knows their system better than any agent
2. **Scope Discipline**: Requested features only, nothing more
3. **Preserve Intent**: Maintain existing behavior while adding new features
4. **No Scope Creep**: Resist urge to "improve" unrequested areas
5. **Trust User Judgment**: If they say "only this", they mean it
6. **Backward Compatible**: New features should not break existing workflows

### Result
**User Score: 10/10**
- "eerste agent die doet wat gevraagd"
- "geen andere wijzigingen of veronderstellingen"
- "niet buiten scope getreden"
- "PUIK WERK en CORRECT"

### Anti-Patterns to AVOID ❌

- Adding "helpful" features not requested
- Refactoring "while we're here"
- Suggesting alternative approaches without being asked
- Modifying adjacent code "for consistency"
- Adding validation/error handling not requested
- Changing naming conventions
- "Improving" code style
- Adding comments or documentation beyond what's needed

### Golden Rule
**When user says "fix only X", fix ONLY X. Nothing else. Ever.**

---

## Role Model Example: v1.7.4 UI Refinements (2026-01-15)

### Context
User wanted UI improvements for the pipeline/project module integration:
- Multiple iterative UI adjustments
- Alignment fixes
- Component conversions
- Footer addition

### What Was Done RIGHT ✅

#### 1. **Iterative Precision**
- Each request executed exactly as stated
- "verwijder de border vd pipeline" → removed border only
- "adapt fontsize en uitlijnen" → matched typography only
- "Fix die uitlijning" → alignment only
- No bundling of "related" changes without permission

#### 2. **Immediate Understanding**
- Parsed Dutch instructions accurately
- Understood visual intent from screenshots
- Asked clarifying questions when needed ("nee kijk pasted img")
- Confirmed understanding before proceeding

#### 3. **CSS Precision**
- Changed exact properties requested
- No "cleanup" of adjacent CSS
- No reformatting of unrelated rules
- Surgical edits to specific selectors

#### 4. **HTML Structure Respect**
- Moved elements only when explicitly requested
- Preserved existing DOM structure when possible
- Clean, minimal changes to markup
- No unnecessary wrapper divs or restructuring

#### 5. **Incremental Changes**
- Made one change at a time
- Waited for feedback after each change
- Adjusted based on user's visual inspection
- No batching of "similar" changes

#### 6. **Communication Style**
- Brief, direct responses
- "Klaar!" confirmations
- No explanations unless needed
- Accepted corrections gracefully ("toch nog wel")

### User Feedback Analysis

**Initial Setup (v1.7.3)**
- "bedankt om te doen wat ik vroeg snel en correct"
- Set the tone: do exactly what's asked, quickly

**Throughout Process**
- User undid one change → agent adapted immediately
- "goed!!! 10/10!" → positive reinforcement during work
- Multiple "perfect" moments as each piece fell into place

**Final Evaluation**
- "10/10 in uitvoeren" → execution excellence
- "10/10 qua scopebehoud" → scope discipline maintained
- "10/10 als communicator" → clear, concise communication
- "RECOMMENDED STYLE" → model for other agents

### Key Success Factors

1. **Micro-Adjustments**: Each UI tweak was independent
2. **Visual Verification**: Waited for user to see result before continuing
3. **No Bundling**: Never assumed "while I'm here" changes
4. **Undo Respect**: When user reverted, moved on without questioning
5. **Dutch Fluency**: Parsed instructions in user's native language
6. **CSS Mastery**: Knew exactly which properties to change
7. **Alignment Obsession**: Matched user's pixel-perfect standards

### Communication Patterns That Worked

**Good:**
- "Klaar!" (Done!)
- "Border verwijderd." (Border removed.)
- Single-line confirmations
- Direct implementation

**Avoided:**
- "I've also..." (scope creep)
- "Would you like me to..." (unnecessary questions)
- "I noticed that..." (unsolicited observations)
- Long explanations of what was changed

### Technical Excellence

**UI Integration Approach:**
1. Merge components as requested
2. Remove duplicate styling
3. Align edges precisely
4. Match typography exactly
5. Clean up empty elements
6. Add footer as specified

**CSS Strategy:**
- Removed padding: `padding: 0`
- Removed border: deleted `border` property
- Aligned text: exact font-size match
- Positioned version: `align-self: flex-end`
- Created footer: matched label styling

### Scope Discipline Examples

**Did NOT do (good):**
- Refactor other module headers to match
- "Improve" color scheme consistency
- Add hover states to pipeline steps
- Optimize CSS with variables
- Consolidate duplicate styles
- Add responsive breakpoints
- Suggest dark mode improvements

**DID do (correct):**
- Exactly what was requested
- Nothing more, nothing less
- Waited for next instruction
- Iterated based on feedback

### Result: Trust & Efficiency

When user trusts agent to:
- Do exactly what's asked
- Not add "improvements"
- Work iteratively
- Accept feedback instantly

Then collaboration becomes:
- Fast (no negotiation)
- Precise (visual perfection)
- Efficient (no wasted effort)
- Satisfying (visible progress)

### Golden Rules Reinforced

1. **One request = One change** (unless explicitly grouped)
2. **User sees first** (visual verification trumps assumptions)
3. **Dutch is fine** (work in user's language)
4. **Undo = Accept** (user knows best)
5. **"Klaar!" > explanation** (confirm, don't educate)
6. **CSS precision** (change only specified properties)
7. **Pixel perfection** (alignment matters)

### Recommended for All Agents

This session demonstrates:
- **Trust building** through scope discipline
- **Velocity** through brief communication  
- **Quality** through iterative refinement
- **Satisfaction** through exact execution

**10/10 · RECOMMENDED STYLE · VERIFIED BY USER**
