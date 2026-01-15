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
