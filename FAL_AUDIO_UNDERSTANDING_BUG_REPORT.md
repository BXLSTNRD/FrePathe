# FAL Audio-Understanding API Bug Report
**Date:** January 23, 2026  
**Issue:** Audio analysis truncates at ~117 seconds for tracks longer than 2 minutes

---

## Summary
The `fal-ai/audio-understanding` API appears to stop processing audio after approximately 117 seconds, regardless of the actual track duration. This results in incomplete lyrics transcription, truncated structure analysis, and incorrect duration reporting.

---

## Evidence

### Working Example (January 12, 2026)
**Track:** La Chaudasse  
**Actual Duration:** 177.11 seconds (validated with librosa)  
**FAL Analysis:**
- ✅ 47 lyrics entries  
- ✅ Timestamps extend to 252s  
- ✅ Complete track analysis  

### Broken Example (January 23, 2026)
**Track:** No Excuses  
**Actual Duration:** 254.17 seconds (validated with librosa)  
**FAL Analysis:**
- ❌ Only 12 lyrics entries  
- ❌ Last timestamp: 119.64s  
- ❌ Reported duration: 117s  
- ❌ Analysis stops after ~46% of track  

**Debug File:** `8b587dc0-3cf9-4c11-bf87-b7ae8e210c64_fal_1769138510.json`

---

## Reproduction

### API Call
```json
{
  "audio_url": "https://v3b.fal.media/files/b/0a8b7dba/zSyFq5l1k_z6vKa3hzQsp_4_No_excuses.wav",
  "prompt": "Analyze this audio and return ONLY a JSON object with this exact structure (no markdown, no prose):\n{\n  \"bpm\": 120,\n  \"style\": [\"genre1\", \"genre2\"],\n  \"structure\": [{\"type\": \"intro\", \"start\": 0, \"end\": 15}, {\"type\": \"verse\", \"start\": 15, \"end\": 45}],\n  \"dynamics\": [{\"start\": 0, \"end\": 30, \"energy\": 0.5}],\n  \"vocal_delivery\": {\"pace\": \"medium\", \"tone\": [\"emotional\"]},\n  \"story_arc\": {\"theme\": \"description of theme\", \"start\": \"beginning state\", \"conflict\": \"tension\", \"end\": \"resolution\"},\n  \"lyrics\": [{\"start\": 0, \"text\": \"lyric line\"}],\n  \"duration_sec\": 180\n}\nInclude: BPM detection, music style/genre, song structure sections with timestamps, dynamics/energy levels, vocal delivery analysis, narrative story arc, and full lyrics transcription with timestamps."
}
```

### Response (Truncated)
```json
{
  "bpm": 185,
  "style": ["Pop Punk", "Alternative Rock"],
  "structure": [
    {"type": "intro", "start": 0.0, "end": 29.02},
    {"type": "verse", "start": 29.02, "end": 43.19},
    {"type": "verse", "start": 43.19, "end": 58.11},
    {"type": "chorus", "start": 58.11, "end": 117.0},
    {"type": "instrumental", "start": 87.52, "end": 117.0}
  ],
  "lyrics": [
    {"start": 29.02, "text": "Don't change my mind I won't stay long"},
    {"start": 33.09, "text": "Give me a minute 'til I'm gone"},
    // ... only 12 entries total ...
    {"start": 119.64, "text": "Don't close your eyes when I see it"}
  ],
  "duration_sec": 117
}
```

**Note:** Last lyric timestamp (119.64s) exceeds reported duration (117s), indicating internal inconsistency.

---

## Testing Performed

1. **Multiple Tracks:** Tested with different audio files - truncation varies (observed ~117s, but not consistent across all tracks)
2. **Different Timestamps:** Tested at various times of day - same truncation behavior persists
3. **FAL Playground:** Reproduced issue in FAL.ai playground interface
4. **Application Testing:** Reproduced via API calls from application

---

## Expected Behavior
API should analyze the **entire audio file** and return:
- Complete lyrics transcription for full duration
- Structure analysis spanning entire track
- Accurate `duration_sec` matching actual file length
- Consistent timestamps (no values exceeding duration)

---

## Actual Behavior
API stops processing at ~117 seconds:
- Lyrics truncated to first ~2 minutes
- Structure sections capped at 117s
- Reported duration incorrect for longer tracks
- Timestamp inconsistencies (119.64s > 117s duration)

---

## Timeline
- **January 12, 2026:** API working correctly (177s track fully analyzed)
- **January 23, 2026:** API truncating at 117s (254s track only 46% analyzed)

**Hypothesis:** Server-side API change or processing timeout introduced between these dates.

---

## Impact
- Incomplete song analysis for tracks > 2 minutes
- Missing lyrics for final portions of songs
- Incorrect BPM/structure detection due to partial analysis
- Workaround required: use separate transcription service (e.g., `fal-ai/whisper`) at additional cost

---

## Request
Please investigate and restore full-duration audio analysis capability, or document the 117s limit if intentional.

**Contact:** [Your email/account identifier]  
**Account:** [Your FAL account ID]
