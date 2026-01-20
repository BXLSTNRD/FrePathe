# Cast Matrix Future Optimizations

**Versie:** 1.8.3+  
**Status:** Backlog voor v1.9+

---

## 4. Cast Refs Queue System

**Probleem:**  
Cast matrix heeft geen queue systeem zoals Shots/Scenes. Als user snel meerdere CREATE knoppen klikt bij verschillende CastIDs, kunnen responses door elkaar lopen.

**Huidige situatie:**
- `PENDING_CAST_REFS` Set voorkomt duplicate clicks voor ZELFDE cast_id
- Geen globale queue → meerdere CastIDs kunnen parallel renderen
- Geen tracking van "welke render hoort bij welke card"
- Risk: Bij 3 simultane CREATE clicks kunnen refs bij verkeerde card terechtkomen

**Shots hebben (werkt goed):**
```javascript
const RENDER_QUEUE = [];
const ACTIVE_RENDERS = new Set();
const MAX_CONCURRENT = 6;

function addToRenderQueue(shot) {
  RENDER_QUEUE.push(shot);
  generateNextInQueue();
}

async function generateNextInQueue() {
  while (ACTIVE_RENDERS.size < MAX_CONCURRENT && RENDER_QUEUE.length > 0) {
    const shot = RENDER_QUEUE.shift();
    ACTIVE_RENDERS.add(shot.shot_id);
    await renderItemAsync(shot);
    ACTIVE_RENDERS.delete(shot.shot_id);
  }
}
```

**Voorgestelde oplossing:**

### Frontend (app.js)
```javascript
const CAST_REF_QUEUE = [];
const ACTIVE_CAST_RENDERS = new Set();
const MAX_CONCURRENT_CAST = 2; // FAL rate limits

async function queueCastRefGeneration(castId, operation) {
  CAST_REF_QUEUE.push({ castId, operation, timestamp: Date.now() });
  processCastRefQueue();
}

async function processCastRefQueue() {
  while (ACTIVE_CAST_RENDERS.size < MAX_CONCURRENT_CAST && CAST_REF_QUEUE.length > 0) {
    const task = CAST_REF_QUEUE.shift();
    ACTIVE_CAST_RENDERS.add(task.castId);
    
    try {
      switch (task.operation) {
        case 'create':
          await createCastRefsInternal(task.castId);
          break;
        case 'rerender_both':
          await rerenderCastWithPromptInternal(task.castId);
          break;
        case 'rerender_a':
          await rerenderSingleRefInternal(task.castId, 'a');
          break;
        case 'rerender_b':
          await rerenderSingleRefInternal(task.castId, 'b');
          break;
      }
    } finally {
      ACTIVE_CAST_RENDERS.delete(task.castId);
      processCastRefQueue(); // Process next in queue
    }
  }
}
```

**Voordelen:**
- Voorkomt response-chaos bij meerdere CastIDs
- Rate limit respect (FAL heeft max concurrent requests)
- Duidelijke feedback welke renders actief zijn
- Queue visualisatie mogelijk (zoals timeline segments)

**Implementatie-inspanning:** ~2-3 uur  
**Prioriteit:** Medium (alleen nodig bij >3 cast members)

---

## 5. Backend Async Concurrency voor RefA/RefB

**Probleem:**  
Cast ref generation is TRAAG omdat RefA + RefB sequentieel gegenereerd worden.

**Huidige situatie:**
```python
# main.py lijn 940-942
ref_a_url = call_img2img_editor(editor, prompt_a, ref_images, aspect, project_id, state=state)
track_cost(...)
ref_b_url = call_img2img_editor(editor, prompt_b, ref_images, aspect, project_id, state=state)
```

**Timing:**
- RefA: ~8-12s (FAL img2img)
- RefB: ~8-12s (FAL img2img)
- **Total: 16-24s sequentieel**

**Shots hebben (werkt goed):**
```python
# Video generation async (v1.8.2)
async with VIDEO_SEMAPHORE:
    result = await asyncio.to_thread(generate_video_sync, ...)
```

**Voorgestelde oplossing:**

### Backend (main.py)
```python
import asyncio
from services.config import RENDER_SEMAPHORE

@app.post("/api/project/{project_id}/cast/{cast_id}/canonical_refs")
async def api_cast_generate_canonical_refs(project_id: str, cast_id: str):
    """Generate both ref_a and ref_b in parallel."""
    state = load_project(project_id)
    editor = locked_editor_key(state)
    require_key("FAL_KEY", FAL_KEY)

    cast = find_cast(state, cast_id)
    if not cast:
        raise HTTPException(404, "Cast not found")

    # ... prep work (style, prompts, etc.)

    # v1.9: Parallel generation with semaphore
    async def gen_ref_a():
        async with RENDER_SEMAPHORE:
            return await asyncio.to_thread(
                call_img2img_editor, editor, prompt_a, ref_images, aspect, project_id, state
            )

    async def gen_ref_b():
        async with RENDER_SEMAPHORE:
            return await asyncio.to_thread(
                call_img2img_editor, editor, prompt_b, ref_images, aspect, project_id, state
            )

    # Parallel execution
    ref_a_url, ref_b_url = await asyncio.gather(gen_ref_a(), gen_ref_b())

    # ... download, save, track costs
```

**Timing na optimalisatie:**
- RefA + RefB parallel: ~8-12s (max van beide)
- **Speedup: 2x sneller**

**Extra optimalisatie: Upload concurrency**
```python
# Download refs in parallel
async def download_a():
    return await asyncio.to_thread(
        download_image_locally, ref_a_url, project_id, f"cast_{cast_id}_ref_a", state, friendly_name
    )

async def download_b():
    return await asyncio.to_thread(
        download_image_locally, ref_b_url, project_id, f"cast_{cast_id}_ref_b", state, friendly_name
    )

ref_a, ref_b = await asyncio.gather(download_a(), download_b())
```

**Total speedup: 2-2.5x sneller (16-24s → 8-12s)**

**Voordelen:**
- Halveert wachttijd voor CREATE knop
- Consistent met video generation async pattern (v1.8.2)
- Respecteert RENDER_SEMAPHORE (max 6 concurrent)

**Risico's:**
- FAL rate limits (max ~10 concurrent API calls)
- State-writing threading issues (oplossing: keep lock)

**Implementatie-inspanning:** ~1-2 uur  
**Prioriteit:** High (directe UX improvement)

---

## Performance Impact Summary

| Optimalisatie | Speedup | Prioriteit | Inspanning |
|--------------|---------|------------|------------|
| Queue systeem | Stabiliteit | Medium | 2-3h |
| Async RefA/RefB | 2x | High | 1-2h |
| **Combined** | 2x + stabiliteit | - | 3-5h |

**Aanbevolen volgorde:**
1. Implementeer async RefA/RefB (v1.9) → directe snelheidswinst
2. Add queue systeem indien >3 cast members in productie

---

## Related Issues

- v1.8.0: FAL upload cache optimization (150x reduction) → apply same pattern to cast refs
- v1.8.2: Video concurrency 2→8 → apply async pattern to cast generation
- Performance parity: Shots render async (6 concurrent), Cast refs sequential (1 at a time)

---

**Laatst bijgewerkt:** 2026-01-20  
**Status:** Documentatie compleet, wacht op implementatie in v1.9+
