// BXLSTNRD Video Studio v1.6.9

const DEFAULT_AUDIO_PROMPT = `Analyze this audio and return ONLY a JSON object with this exact structure (no markdown, no prose):
{
  "bpm": 120,
  "style": ["genre1", "genre2"],
  "structure": [{"type": "intro", "start": 0, "end": 15}, {"type": "verse", "start": 15, "end": 45}],
  "dynamics": [{"start": 0, "end": 30, "energy": 0.5}],
  "vocal_delivery": {"pace": "medium", "tone": ["emotional"]},
  "story_arc": {"theme": "description of theme", "start": "beginning state", "conflict": "tension", "end": "resolution"},
  "lyrics": [{"start": 0, "text": "lyric line"}],
  "duration_sec": 180
}
Include: BPM detection, music style/genre, song structure sections with timestamps, dynamics/energy levels, vocal delivery analysis, narrative story arc, and full lyrics transcription with timestamps.`;

let PROJECT_STATE = null;
let SELECTED_SEQUENCE_ID = null;
let AUDIO_DATA = {};

// v1.5.3: Unified Render Queue System for shots, scenes, and cast refs
let RENDER_QUEUE = [];  // Array of {type: "shot"|"scene"|"cast", id: string}
let ACTIVE_RENDERS = 0;
const MAX_CONCURRENT = 6;  // v1.6.6: Balanced for stability (FAL limit is 20, but uploads need breathing room)

// v1.5.8: Track pending canonical ref renders to prevent duplicates
let PENDING_CAST_REFS = new Set();  // Set of cast_ids currently generating refs

// ========= Utility =========
function pid() { return document.getElementById("projectId").value.trim(); }

// v1.6.5: Cache-busting for images - prevents browser from showing stale renders
function cacheBust(url) {
  if (!url) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}t=${Date.now()}`;
}

// v1.5.9: Per-module status system with domain-specific jokes
const MODULE_JOKES = {
  audio: [
    "Is that a cowbell?",
    "Please sing in tune",
    "Not my taste, but I'm paid for this",
    "Another guitar solo, great",
    "Is that AI generated?",
    "They didn't fix that in the mix",
    "Is that 12/8? I'm not Danny Carey",
    "I hate odd meters",
    "Syncopated? Are you fooling me?",
    "Great, another Steve Vai wannabe",
    "Is that Axl or a dying cat?",
    "The bassist is asleep again",
    "Who approved these lyrics?",
    "Autotune can't save this",
    "The drummer is rushing"
  ],
  cast: [
    "That's your best angle?",
    "Lighting won't fix everything",
    "The camera adds 10 pounds of regret",
    "Method acting isn't for everyone",
    "Your agent lied to you",
    "Headshots don't lie. Unfortunately",
    "Blue steel? More like rusty iron",
    "The costume hides nothing",
    "Makeup can only do so much",
    "Have you considered radio?",
    "That's... a choice",
    "The stand-in looked better",
    "Wardrobe malfunction pending",
    "Your motivation is money",
    "Less face, more shadow"
  ],
  storyboard: [
    "The script was better",
    "We'll fix it in post",
    "That's one interpretation",
    "The focus puller quit",
    "Continuity is overrated",
    "Nobody reads the shotlist",
    "That's not what I envisioned",
    "The DP is crying",
    "Budget? What budget",
    "Art direction by committee",
    "The blocking is 'creative'",
    "Coverage? Never heard of it",
    "That's technically a shot",
    "The storyboard artist left",
    "Visual storytelling is hard"
  ],
  preview: [
    "Rendering your life choices",
    "Export in progress. Go outside",
    "Almost watchable",
    "The algorithm is judging you",
    "Pixels aren't free",
    "Compression artifacts are features",
    "Your hard drive is crying",
    "RAM is screaming",
    "Thermal throttling engaged",
    "The GPU needs therapy",
    "Encoding with thoughts and prayers",
    "Quality is subjective",
    "It's called 'artistic'",
    "Buffering your dreams",
    "Almost cinema. Almost"
  ]
};

// Track joke state per module
let moduleJokeState = {};

function getModuleJoke(moduleType) {
  const jokes = MODULE_JOKES[moduleType] || MODULE_JOKES.storyboard;
  if (!moduleJokeState[moduleType]) {
    moduleJokeState[moduleType] = { index: Math.floor(Math.random() * jokes.length), showJoke: false };
  }
  const state = moduleJokeState[moduleType];
  state.showJoke = !state.showJoke;
  if (state.showJoke) {
    const joke = jokes[state.index % jokes.length];
    state.index++;
    return joke;
  }
  return null;
}

// Module status timers
let moduleTimers = {};

function setModuleStatus(moduleId, text, isDone = false, moduleType = null) {
  const el = document.getElementById(moduleId);
  if (!el) return;
  
  // Clear existing timer
  if (moduleTimers[moduleId]) {
    clearInterval(moduleTimers[moduleId]);
    moduleTimers[moduleId] = null;
  }
  
  el.textContent = text || "";
  
  if (isDone) {
    el.classList.remove("active");
    // Clear after 7s
    setTimeout(() => { if (el) el.textContent = ""; }, 7000);
  } else if (text) {
    el.classList.add("active");
    // v1.6.3: Start joke rotation if moduleType provided
    // Shows ONLY joke OR ONLY baseText (not both), 7s interval
    if (moduleType) {
      moduleJokeState[moduleType] = { index: Math.floor(Math.random() * MODULE_JOKES[moduleType]?.length || 0), showJoke: false };
      let baseText = text;
      moduleTimers[moduleId] = setInterval(() => {
        const joke = getModuleJoke(moduleType);
        // v1.6.3: Show joke OR base text, not both combined
        el.textContent = joke ? joke : baseText;
      }, 7000);  // 7s interval
    }
  }
}

// Global status - NO jokes, serious only
function setGlobalStatus(text, isError = false) {
  const label = document.getElementById("statusLabel");
  if (!label) return;
  
  label.textContent = text || "Ready";
  label.classList.toggle("error", isError);
  label.classList.toggle("active", !!text && text !== "Ready");
  
  // Clear after 10s if not error
  if (text && !isError) {
    setTimeout(() => {
      if (label.textContent === text) {
        label.textContent = "Ready";
        label.classList.remove("active");
      }
    }, 10000);
  }
}

// v1.5.9: Unified setStatus that routes to appropriate handler
function setStatus(text, pct, moduleId = null, moduleType = null) {
  // v1.6.3: Progress bar removed - using module-specific status only
  
  // Map moduleId to moduleType if not provided
  const typeMap = {
    "audioStatus": "audio",
    "castStatus": "cast", 
    "storyboardStatus": "storyboard",
    "previewStatus": "preview"
  };
  const effectiveType = moduleType || typeMap[moduleId] || null;
  
  // Module-specific status with jokes
  if (moduleId && moduleId !== "projectStatus") {
    const isDone = pct === 100;
    setModuleStatus(moduleId, text, isDone, effectiveType);
    return;
  }
  
  // Global/pipeline status - serious only
  const isError = text?.startsWith("Error");
  setGlobalStatus(text, isError);
}

function showError(msg) {
  setGlobalStatus("Error: " + msg, true);
  console.error(msg);
}

async function apiCall(url, options = {}) {
  const res = await fetch(url, options);
  const txt = await res.text();
  if (!res.ok) throw new Error(txt || "HTTP " + res.status);
  // v1.4: Update cost counter after API calls
  updateCostCounter();
  return txt ? JSON.parse(txt) : null;
}

// v1.4.9.1: Update cost counter from project state
async function updateCostCounter() {
  try {
    if (pid()) {
      // Get project-specific costs
      const res = await fetch(`/api/project/${pid()}/costs`);
      const data = await res.json();
      document.getElementById("costValue").textContent = "$" + data.total.toFixed(2);
    } else {
      // Fallback to session costs
      const res = await fetch("/api/costs");
      const data = await res.json();
      document.getElementById("costValue").textContent = "$" + data.total.toFixed(2);
    }
  } catch (e) {
    // Ignore errors
  }
}

// ========= Project Management =========
async function ensureProject() {
  if (pid()) return pid();
  setStatus("Creating project…", null);
  // v1.6.5: Include use_whisper from checkbox when creating project
  const useWhisperEl = document.getElementById("useWhisper");
  const data = {
    title: document.getElementById("title").value || "New Production",
    style_preset: document.getElementById("style").value,
    aspect: document.getElementById("aspect").value,
    llm: document.getElementById("llm").value,
    image_model: document.getElementById("imageModel").value,
    use_whisper: useWhisperEl?.checked || false
  };
  const result = await apiCall("/api/project/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  document.getElementById("projectId").value = result.project.id;
  PROJECT_STATE = result;
  return result.project.id;
}

async function autosave() {
  if (!pid()) return;
  try {
    PROJECT_STATE = await apiCall(`/api/project/${pid()}`);
    updateUI();
  } catch (e) {
    console.warn("Autosave failed:", e);
  }
}

// v1.6.3: Update project style preset
async function updateProjectStyle(newStyle) {
  if (!pid()) return;
  try {
    // Check if there are existing cast refs
    const charRefs = PROJECT_STATE?.cast_matrix?.character_refs || {};
    const hasRefs = Object.values(charRefs).some(r => r.ref_a || r.ref_b);
    
    if (hasRefs) {
      const confirm = window.confirm(
        "Style changed! Existing cast renders use the old style.\\n\\n" +
        "Do you want to update the style?\\n" +
        "(You'll need to re-render cast members for the new style to apply)"
      );
      if (!confirm) {
        // Revert dropdown
        document.getElementById("style").value = PROJECT_STATE?.project?.style_preset || "";
        return;
      }
    }
    
    await apiCall(`/api/project/${pid()}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style_preset: newStyle })
    });
    
    if (PROJECT_STATE?.project) {
      PROJECT_STATE.project.style_preset = newStyle;
    }
    
    if (hasRefs) {
      setStatus("Style updated - re-render cast for new style", 100, "castStatus");
    } else {
      setStatus("Style updated", 100);
    }
  } catch (e) {
    showError("Failed to update style: " + e.message);
  }
}

// Save/Load full project
async function saveProjectToFile() {
  try {
    await ensureProject();
    setStatus("Preparing save…", null);
    const state = await apiCall(`/api/project/${pid()}`);
    
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const title = (state.project?.title || "project").replace(/[^a-z0-9]/gi, "_");
    a.download = `BXLSTNRD_${title}_${pid().slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    setStatus("Project saved", 100);
  } catch (e) {
    showError(e.message);
  }
}

function loadProjectFromFile() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json";
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      setStatus("Loading project…", null);
      const text = await file.text();
      const state = JSON.parse(text);
      
      if (!state.project?.id) throw new Error("Invalid project file");
      
      await apiCall("/api/project/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text
      });
      
      document.getElementById("projectId").value = state.project.id;
      document.getElementById("title").value = state.project.title || "";
      document.getElementById("style").value = state.project.style_preset || "";
      document.getElementById("aspect").value = state.project.aspect || "horizontal";
      document.getElementById("llm").value = state.project.llm || "claude";
      
      // v1.5.6: Load video model and whisper settings
      const videoModelEl = document.getElementById("videoModel");
      if (videoModelEl) videoModelEl.value = state.project.video_model || "none";
      const useWhisperEl = document.getElementById("useWhisper");
      if (useWhisperEl) useWhisperEl.checked = state.project.use_whisper || false;
      
      // Load image model
      const imageModelEl = document.getElementById("imageModel");
      if (imageModelEl && state.project.image_model_choice) {
        imageModelEl.value = state.project.image_model_choice;
      }
      
      // Fetch fresh state from server and refresh UI
      setStatus("Refreshing…", 80);
      await refreshFromServer();
      
      if (PROJECT_STATE?.audio_dna) {
        parseAudioDNA(PROJECT_STATE.audio_dna);
        updateAudioButtons();  // v1.6.3: 3-stage button flow
      }
      
      setStatus("Project loaded", 100);
    } catch (e) {
      showError(e.message);
    }
  };
  input.click();
}

function updateUI() {
  if (!PROJECT_STATE) {
    // Show empty state with 3 default cast slots
    renderCastList({ cast: [], cast_matrix: {} });
    return;
  }
  renderAudioInfo(PROJECT_STATE);
  renderCastList(PROJECT_STATE);
  renderTimeline(PROJECT_STATE);
  renderScenes(PROJECT_STATE);
  renderShots(PROJECT_STATE);
  updateButtonStates();
  updatePipelineNav(PROJECT_STATE);
}

function updateButtonStates() {
  const seqs = PROJECT_STATE?.storyboard?.sequences || [];
  const scenes = PROJECT_STATE?.cast_matrix?.scenes || [];
  // v1.7.0: Explicit true checks to handle undefined
  const castLocked = PROJECT_STATE?.project?.cast_locked === true;
  const audioLocked = PROJECT_STATE?.project?.audio_locked === true;
  // v1.5.8: Fix audio loaded check - audio_dna.meta exists when audio is imported
  const dna = PROJECT_STATE?.audio_dna;
  const audioLoaded = !!(dna && (dna.meta?.duration_sec > 0 || dna.style || dna.lyrics?.length > 0));
  
  // v1.6.3: Debug logging
  console.log(`[ButtonStates] audioLoaded=${audioLoaded}, audioLocked=${audioLocked}, castLocked=${castLocked}, scenes=${scenes.length}`);
  
  // v1.6.3: Storyboard buttons require both audio AND cast locked
  const bothLocked = audioLocked && castLocked;

  const createBtn = document.getElementById("createTimelineBtn");
  const allShotsBtn = document.getElementById("allShotsBtn");
  const renderAllBtn = document.getElementById("renderAllShotsBtn");

  if (createBtn) {
    createBtn.disabled = !bothLocked;
    createBtn.title = !audioLoaded ? "Import audio first" : (!audioLocked ? "Lock audio first" : (!castLocked ? "Lock cast first" : ""));
    console.log(`[ButtonStates] CREATE TIMELINE disabled=${!bothLocked}`);
  }

  if (allShotsBtn) {
    // v1.6.5: Also require both locked for All Shots
    allShotsBtn.disabled = !bothLocked || scenes.length === 0;
    allShotsBtn.title = !bothLocked ? "Lock audio and cast first" : "";
  }

  // v1.6.5: Render All also requires both locked
  if (renderAllBtn) {
    renderAllBtn.disabled = !bothLocked;
    renderAllBtn.title = !bothLocked ? "Lock audio and cast first" : "";
  }
  
  // v1.6.3: Collapsible sections - manual toggle
  updateCollapsibleSections();
}

// v1.6.3: Track manual collapse state
const COLLAPSED_SECTIONS = new Set();
// v1.6.5: Track which sections have been auto-collapsed (to avoid repeated auto-collapse)
const AUTO_COLLAPSED_SECTIONS = new Set();

// v1.6.5: Update collapsible sections - auto-collapse when individually locked, manual toggle always works
function updateCollapsibleSections() {
  // v1.7.0: Explicit true checks
  const audioLocked = PROJECT_STATE?.project?.audio_locked === true;
  const castLocked = PROJECT_STATE?.project?.cast_locked === true;

  // v1.6.5: Auto-collapse audio section when audio is locked (only once per lock)
  if (audioLocked && !AUTO_COLLAPSED_SECTIONS.has("section-audio")) {
    COLLAPSED_SECTIONS.add("section-audio");
    AUTO_COLLAPSED_SECTIONS.add("section-audio");
  }
  // If unlocked, clear auto-collapse tracking so it can auto-collapse again if re-locked
  if (!audioLocked) {
    AUTO_COLLAPSED_SECTIONS.delete("section-audio");
  }

  // v1.6.5: Auto-collapse cast section when cast is locked (only once per lock)
  if (castLocked && !AUTO_COLLAPSED_SECTIONS.has("section-cast")) {
    COLLAPSED_SECTIONS.add("section-cast");
    AUTO_COLLAPSED_SECTIONS.add("section-cast");
  }
  // If unlocked, clear auto-collapse tracking so it can auto-collapse again if re-locked
  if (!castLocked) {
    AUTO_COLLAPSED_SECTIONS.delete("section-cast");
  }

  // Audio section
  const audioSection = document.getElementById("section-audio");
  if (audioSection) {
    const audioContent = audioSection.querySelector(".module-content");
    const isCollapsed = COLLAPSED_SECTIONS.has("section-audio");

    if (isCollapsed) {
      audioSection.classList.add("collapsed");
      if (audioContent) audioContent.style.display = "none";
    } else {
      audioSection.classList.remove("collapsed");
      if (audioContent) audioContent.style.display = "";
    }
  }

  // Cast section
  const castSection = document.getElementById("section-cast");
  if (castSection) {
    const castContent = castSection.querySelector(".module-content");
    const isCollapsed = COLLAPSED_SECTIONS.has("section-cast");

    if (isCollapsed) {
      castSection.classList.add("collapsed");
      if (castContent) castContent.style.display = "none";
    } else {
      castSection.classList.remove("collapsed");
      if (castContent) castContent.style.display = "";
    }
  }

  // v1.6.5: Timeline section - auto-collapse when all decors and wardrobes are locked
  const scenes = PROJECT_STATE?.cast_matrix?.scenes || [];
  const allDecorsLocked = scenes.length > 0 && scenes.every(s => s.decor_locked);
  const allWardrobesLocked = scenes.length > 0 && scenes.every(s => s.wardrobe_locked || !s.wardrobe);

  if (allDecorsLocked && allWardrobesLocked && !AUTO_COLLAPSED_SECTIONS.has("section-timeline")) {
    COLLAPSED_SECTIONS.add("section-timeline");
    AUTO_COLLAPSED_SECTIONS.add("section-timeline");
  }
  // If any decor/wardrobe is unlocked, allow re-collapse next time
  if (!allDecorsLocked || !allWardrobesLocked) {
    AUTO_COLLAPSED_SECTIONS.delete("section-timeline");
  }

  // Apply timeline collapse
  const timelineContainer = document.getElementById("timelineContainer");
  const timelineHeader = document.querySelector(".subsection .section-header");
  if (timelineContainer) {
    const isTimelineCollapsed = COLLAPSED_SECTIONS.has("section-timeline");
    timelineContainer.style.display = isTimelineCollapsed ? "none" : "";
    // Add visual indicator for collapsible state
    if (timelineHeader && allDecorsLocked && allWardrobesLocked) {
      timelineHeader.classList.add("collapsible");
      timelineHeader.onclick = () => toggleSectionCollapse("section-timeline");
    }
  }

  // v1.6.5: Shots section - auto-collapse when all shots are rendered
  const shots = PROJECT_STATE?.storyboard?.shots || [];
  const allShotsRendered = shots.length > 0 && shots.every(s => s.render?.image_url);

  if (allShotsRendered && !AUTO_COLLAPSED_SECTIONS.has("section-shots")) {
    COLLAPSED_SECTIONS.add("section-shots");
    AUTO_COLLAPSED_SECTIONS.add("section-shots");
  }
  if (!allShotsRendered) {
    AUTO_COLLAPSED_SECTIONS.delete("section-shots");
  }

  // Apply shots collapse
  const shotsGrid = document.getElementById("shotsGrid");
  const shotsHeader = document.querySelector(".subsection:last-child .section-header");
  if (shotsGrid) {
    const isShotsCollapsed = COLLAPSED_SECTIONS.has("section-shots");
    shotsGrid.style.display = isShotsCollapsed ? "none" : "";
    // Add visual indicator for collapsible state
    if (shotsHeader && allShotsRendered) {
      shotsHeader.classList.add("collapsible");
      shotsHeader.onclick = () => toggleSectionCollapse("section-shots");
    }
  }
}

// v1.6.6: Toggle section collapse on header click - handles both card modules and subsections
function toggleSectionCollapse(sectionId) {
  // For card modules (audio, cast), the section has id directly
  const section = document.getElementById(sectionId);
  
  // For subsections (timeline, shots), we need to find the content element directly
  let contentElement = null;
  if (sectionId === "section-timeline") {
    contentElement = document.getElementById("timelineContainer");
  } else if (sectionId === "section-shots") {
    contentElement = document.getElementById("shotsGrid");
  } else if (section) {
    contentElement = section.querySelector(".module-content");
  }
  
  const isCollapsed = COLLAPSED_SECTIONS.has(sectionId);
  
  if (isCollapsed) {
    // Expand
    COLLAPSED_SECTIONS.delete(sectionId);
    if (section) section.classList.remove("collapsed");
    if (contentElement) contentElement.style.display = "";
  } else {
    // Collapse
    COLLAPSED_SECTIONS.add(sectionId);
    if (section) section.classList.add("collapsed");
    if (contentElement) contentElement.style.display = "none";
  }
}

// v1.5.8: Edit BPM - opens popup with edit option
function editBpm() {
  showAudioPopup('bpm');
}

// ========= Popups =========
function showAudioPopup(field) {
  const titles = { bpm: "BPM", style: "STYLE", structure: "STRUCTURE", dynamics: "DYNAMICS", delivery: "VOCAL DELIVERY", story: "STORY ARC", lyrics: "LYRICS" };
  document.getElementById("audioPopupTitle").textContent = titles[field] || field.toUpperCase();
  
  // v1.5.8: BPM is editable
  if (field === "bpm") {
    const currentBpm = AUDIO_DATA.bpm || 120;
    document.getElementById("audioPopupContent").innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <span>Detected: ${currentBpm}</span>
        <input type="number" id="bpmEditInput" value="${currentBpm}" min="40" max="240" style="width: 80px; padding: 6px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: var(--text);"/>
        <button class="accent-btn" onclick="updateBpm()">UPDATE</button>
      </div>
      <p class="muted" style="margin-top: 12px; font-size: 11px;">If auto-detection is wrong, enter the correct BPM here.</p>
    `;
  // v1.7.0: Lyrics is editable (for when transcription hallucinates)
  } else if (field === "lyrics") {
    const currentLyrics = AUDIO_DATA.lyrics || "No lyrics detected";
    document.getElementById("audioPopupContent").innerHTML = `
      <p class="muted" style="margin-bottom: 8px; font-size: 11px;">⚠️ Auto-transcription can hallucinate on fast-paced or non-English tracks. Paste correct lyrics below:</p>
      <textarea id="lyricsEditInput" style="width: 100%; height: 300px; padding: 12px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-family: monospace; font-size: 12px; resize: vertical;">${currentLyrics}</textarea>
      <div style="margin-top: 12px; display: flex; gap: 8px; justify-content: flex-end;">
        <button class="accent-btn" onclick="updateLyrics()">SAVE LYRICS</button>
      </div>
    `;
  } else {
    document.getElementById("audioPopupContent").textContent = AUDIO_DATA[field] || "No data";
  }
  document.getElementById("audioPopup").classList.remove("hidden");
}

// v1.5.8: Update BPM manually
async function updateBpm() {
  const newBpm = parseInt(document.getElementById("bpmEditInput").value);
  if (!newBpm || newBpm < 40 || newBpm > 240) {
    showError("BPM must be between 40 and 240");
    return;
  }
  
  try {
    setStatus("Updating BPM…", null);
    await apiCall(`/api/project/${pid()}/audio/bpm`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bpm: newBpm })
    });
    
    // Update local state
    AUDIO_DATA.bpm = newBpm;
    document.getElementById("audioBpm").textContent = newBpm;
    hidePopup("audioPopup");
    setStatus("BPM updated", 100);
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.7.0: Update lyrics manually (for hallucinated transcriptions)
async function updateLyrics() {
  const newLyrics = document.getElementById("lyricsEditInput").value.trim();
  if (!newLyrics) {
    showError("Lyrics cannot be empty");
    return;
  }
  
  try {
    setStatus("Updating lyrics…", null);
    await apiCall(`/api/project/${pid()}/audio/lyrics`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lyrics: newLyrics })
    });
    
    // Update local state
    AUDIO_DATA.lyrics = newLyrics;
    document.getElementById("audioLyrics").textContent = newLyrics.substring(0, 500) + (newLyrics.length > 500 ? "…" : "");
    hidePopup("audioPopup");
    setStatus("Lyrics updated", 100);
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

function showImagePopup(src) {
  if (!src) return;
  document.getElementById("popupImage").src = src;
  document.getElementById("imagePopup").classList.remove("hidden");
}

function hidePopup(id) {
  document.getElementById(id).classList.add("hidden");
}

// v1.5.3: Show cost breakdown popup
function showCostBreakdown() {
  const costs = PROJECT_STATE?.costs;
  const container = document.getElementById("costBreakdownContent");
  
  if (!costs || !costs.calls || costs.calls.length === 0) {
    container.innerHTML = '<p class="muted">No API calls recorded yet.</p>';
    document.getElementById("costPopup").classList.remove("hidden");
    return;
  }
  
  // Group costs by model
  const byModel = {};
  for (const call of costs.calls) {
    const model = call.model || "unknown";
    if (!byModel[model]) {
      byModel[model] = { count: 0, total: 0 };
    }
    byModel[model].count++;
    byModel[model].total += call.cost;
  }
  
  // Sort by total cost descending
  const sorted = Object.entries(byModel).sort((a, b) => b[1].total - a[1].total);
  
  // Build HTML
  let html = `
    <table style="width: 100%; border-collapse: collapse;">
      <thead>
        <tr style="border-bottom: 1px solid var(--border);">
          <th style="text-align: left; padding: 8px 4px;">Model</th>
          <th style="text-align: right; padding: 8px 4px;">Calls</th>
          <th style="text-align: right; padding: 8px 4px;">Cost</th>
        </tr>
      </thead>
      <tbody>
  `;
  
  for (const [model, data] of sorted) {
    // Shorten model name for display
    const shortName = model.replace("fal-ai/", "").replace("/edit", "");
    html += `
      <tr style="border-bottom: 1px solid var(--border-light);">
        <td style="padding: 8px 4px; font-size: 13px;">${shortName}</td>
        <td style="text-align: right; padding: 8px 4px;">${data.count}</td>
        <td style="text-align: right; padding: 8px 4px;">$${data.total.toFixed(2)}</td>
      </tr>
    `;
  }
  
  html += `
      </tbody>
      <tfoot>
        <tr style="font-weight: bold;">
          <td style="padding: 8px 4px;">Total</td>
          <td style="text-align: right; padding: 8px 4px;">${costs.calls.length}</td>
          <td style="text-align: right; padding: 8px 4px;">$${costs.total.toFixed(2)}</td>
        </tr>
      </tfoot>
    </table>
  `;
  
  container.innerHTML = html;
  document.getElementById("costPopup").classList.remove("hidden");
}

// ========= Audio =========
async function importAudio() {
  try {
    const f = document.getElementById("audioFile").files[0];
    if (!f) return;
    
    await ensureProject();
    
    // v1.5.4: More detailed status updates
    setStatus("Uploading audio…", null, "audioStatus");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("prompt", DEFAULT_AUDIO_PROMPT);
    
    setStatus("Analyzing audio DNA…", null, "audioStatus");
    const result = await fetch(`/api/project/${pid()}/audio`, { method: "POST", body: fd });
    const txt = await result.text();
    if (!result.ok) throw new Error(txt);
    
    const js = JSON.parse(txt);
    
    // v1.7.0: Update PROJECT_STATE with new audio_dna BEFORE parsing
    if (!PROJECT_STATE) PROJECT_STATE = js;
    else PROJECT_STATE.audio_dna = js.audio_dna;
    
    parseAudioDNA(js.audio_dna);
    
    // v1.6.3: 3-stage button flow - after import, show LOCK button
    updateAudioButtons();
    
    setStatus("Audio loaded", 100, "audioStatus");
    updateButtonStates();  // v1.5.4: Enable storyboard buttons if cast also locked
    await autosave();
  } catch (e) {
    showError(e.message);
  }
}

// v1.6.3: Update audio button states based on current state
function updateAudioButtons() {
  // v1.7.0: More robust audio loaded check - check multiple indicators
  const dna = PROJECT_STATE?.audio_dna;
  const duration = dna?.meta?.duration_sec || dna?.duration_sec || 0;
  const audioLoaded = !!dna && (parseFloat(duration) > 0 || dna?.style || dna?.lyrics?.length > 0);
  const audioLocked = PROJECT_STATE?.project?.audio_locked === true;  // v1.7.0: Explicit true check
  
  console.log("[updateAudioButtons] dna:", !!dna, "duration:", duration, "loaded:", audioLoaded, "locked:", audioLocked);
  
  const importBtn = document.getElementById("importAudioBtn");
  const lockBtn = document.getElementById("lockAudioBtn");
  const lockedBadge = document.getElementById("audioLockedBadge");
  
  // v1.7.0: Show LOCK button when audio is loaded but NOT locked
  const showLockBtn = audioLoaded && !audioLocked;
  
  if (importBtn) importBtn.classList.toggle("hidden", audioLoaded);
  if (lockBtn) lockBtn.classList.toggle("hidden", !showLockBtn);
  if (lockedBadge) lockedBadge.classList.toggle("hidden", !audioLocked);
}

// v1.6.3: Toggle audio lock
async function toggleAudioLock() {
  try {
    await ensureProject();
    const isLocked = PROJECT_STATE?.project?.audio_locked || false;
    const newState = !isLocked;
    
    await apiCall(`/api/project/${pid()}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_locked: newState })
    });
    
    PROJECT_STATE.project.audio_locked = newState;
    updateAudioButtons();
    updateButtonStates();
    updateCollapsibleSections();
    
    setStatus(newState ? "Audio locked" : "Audio unlocked", 100, "audioStatus");
  } catch (e) {
    showError(e.message);
  }
}

// Patch 2: Fix parsing - extract fields correctly
function parseAudioDNA(dna) {
  if (!dna) return;
  
  // If raw_text_blob contains JSON, try to parse it first (fallback for older data)
  let parsedFromBlob = null;
  if (dna.raw_text_blob && typeof dna.raw_text_blob === 'string') {
    let text = dna.raw_text_blob.trim();
    // Remove markdown code blocks
    if (text.startsWith('```json')) text = text.slice(7);
    else if (text.startsWith('```')) text = text.slice(3);
    if (text.endsWith('```')) text = text.slice(0, -3);
    text = text.trim();
    try {
      parsedFromBlob = JSON.parse(text);
    } catch (e) {
      // Not JSON, that's fine
    }
  }
  
  // Use parsed blob data if available and main fields are empty
  const src = parsedFromBlob || dna;
  
  // v1.7.0: Handle both nested and flat structures from normalize_audio_understanding
  const bpm = dna.meta?.bpm || src.bpm || null;
  // v1.7.0: style is now at root level from Python, also check meta for legacy
  const style = dna.style || dna.meta?.style || src.style || [];
  const structure = dna.sections?.length ? dna.sections : (dna.structure?.length ? dna.structure : (src.structure || []));
  const dynamics = dna.dynamics?.length ? dna.dynamics : (src.dynamics || []);
  // v1.7.0: delivery and story are now strings from Python normalize
  const deliveryStr = dna.delivery || "";
  const storyStr = dna.story || "";
  // Legacy support for object formats
  const vocal = typeof deliveryStr === 'string' ? {} : (dna.vocal_delivery || src.vocal_delivery || {});
  const story = typeof storyStr === 'string' ? {} : (dna.story_arc || src.story_arc || {});
  const lyrics = dna.lyrics?.length ? dna.lyrics : (src.lyrics || []);
  const duration = dna.meta?.duration_sec || src.duration_sec || src.duration || 0;
  
  // v1.5.4: Extract lyrics text with line breaks
  let lyricsText = "—";
  if (lyrics.length) {
    // v1.5.4: Use line breaks between lyric lines
    lyricsText = lyrics.map(l => l.text || l).join("\n");
  } else if (dna.raw_text_blob && !parsedFromBlob) {
    // Keep raw blob with line breaks
    lyricsText = dna.raw_text_blob.trim();
  }
  
  // Store parsed data
  // v1.7.0: Handle both new string formats and legacy object formats
  AUDIO_DATA = {
    bpm: bpm ? `${bpm}` : "—",
    style: Array.isArray(style) ? style.join(", ") : (style || "—"),
    structure: structure.length 
      ? structure.map(s => `${s.type}: ${(s.start||0).toFixed(1)}s - ${(s.end||0).toFixed(1)}s`).join("\n") 
      : "—",
    dynamics: dynamics.length 
      ? dynamics.map(d => `${(d.start||0).toFixed(1)}s: Energy ${Math.round((d.energy||0)*100)}%`).join("\n") 
      : "—",
    // v1.7.0: deliveryStr is now a string from Python, fallback to legacy object format
    delivery: deliveryStr || [
      vocal.pace && `Pace: ${vocal.pace}`,
      vocal.tone?.length && `Tone: ${vocal.tone.join(", ")}`
    ].filter(Boolean).join("\n") || "—",
    // v1.7.0: storyStr is now a string from Python, fallback to legacy object format
    story: storyStr || [
      story.theme && `Theme: ${story.theme}`,
      story.conflict && `Conflict: ${story.conflict}`
    ].filter(Boolean).join("\n") || "—",
    lyrics: lyricsText,
    duration: duration
  };
  
  // Update UI fields
  document.getElementById("audioBpm").textContent = AUDIO_DATA.bpm;
  document.getElementById("audioStyle").textContent = Array.isArray(style) ? style.slice(0,2).join(", ") : (style || "—");
  document.getElementById("audioStructure").textContent = structure.length 
    ? [...new Set(structure.map(s => s.type))].slice(0,3).join("-") 
    : "—";
  
  const avgEnergy = dynamics.length ? dynamics.reduce((a,d) => a + (d.energy||0), 0) / dynamics.length : 0;
  document.getElementById("audioDynamics").textContent = avgEnergy > 0.7 ? "High" : avgEnergy > 0.4 ? "Medium" : "Low";
  // v1.7.0: Use deliveryStr directly or fallback to legacy object
  document.getElementById("audioDelivery").textContent = deliveryStr 
    ? deliveryStr.split(" - ")[0].slice(0, 15) 
    : (vocal.pace || (vocal.tone?.slice(0,2).join(", ")) || "—");
  // v1.7.0: Use storyStr directly or fallback to legacy object  
  document.getElementById("audioStory").textContent = storyStr 
    ? storyStr.slice(0, 25) + (storyStr.length > 25 ? "…" : "")
    : (story.theme || "—").slice(0, 18);
  document.getElementById("audioLyrics").textContent = AUDIO_DATA.lyrics;
}

function renderAudioInfo(state) {
  const dna = state.audio_dna;
  if (!dna) return;
  
  parseAudioDNA(dna);
  updateAudioButtons();  // v1.6.3: 3-stage button flow
}

// ========= Cast Matrix =========
// Patch 3: Default 3 empty cards
function renderDefaultCast() {
  const list = document.getElementById("castList");
  const roles = ["LEAD", "SUPPORTING", "EXTRA"];
  
  list.innerHTML = roles.map((role, idx) => `
    <div class="cast-row" data-idx="${idx}">
      <input type="file" class="cast-file-input" accept="image/*" onchange="uploadNewCast(${idx}, '${role.toLowerCase()}', this)"/>
      <div class="cast-thumb-placeholder" onclick="this.previousElementSibling.click()">+</div>
      <span class="cast-role-label">${role}</span>
      <input type="text" class="cast-name-input" placeholder="Name (optional)"/>
      <div class="cast-refs">
        <div class="cast-ref-placeholder">A</div>
        <div class="cast-ref-placeholder">B</div>
      </div>
    </div>
  `).join("");
}

function renderCastList(state) {
  const list = document.getElementById("castList");
  const cast = state.cast || [];
  const charRefs = state.cast_matrix?.character_refs || {};
  const isLocked = state.project?.cast_locked || false;
  
  // v1.4.9.1: Default impact per role
  const defaultImpacts = { lead: 0.7, supporting: 0.5, extra: 0.1 };
  const minSlots = 3;
  const totalSlots = Math.max(minSlots, cast.length);
  
  let html = "";
  
  for (let idx = 0; idx < totalSlots; idx++) {
    const c = cast[idx];
    const defaultRole = idx === 0 ? "lead" : (idx === 1 ? "supporting" : "extra");
    
    if (c) {
      const refs = charRefs[c.cast_id] || {};
      const mainImg = c.reference_images?.[0]?.url;
      const role = c.role || defaultRole;
      const impact = c.impact ?? defaultImpacts[role];
      const promptExtra = c.prompt_extra || "";
      const hasRefs = refs.ref_a && refs.ref_b;
      
      html += `
        <div class="cast-card" data-cast-id="${c.cast_id}">
          ${!isLocked ? `<button class="cast-delete" onclick="deleteCastMember('${c.cast_id}')" title="Delete">×</button>` : ''}
          <input type="file" class="cast-file-input" data-type="main" accept="image/*" onchange="updateCastImage('${c.cast_id}', this)" ${isLocked ? 'disabled' : ''}/>
          <input type="file" class="cast-file-input" data-type="ref_a" accept="image/*" onchange="updateCastRefImage('${c.cast_id}', 'a', this)" ${isLocked ? 'disabled' : ''}/>
          <input type="file" class="cast-file-input" data-type="ref_b" accept="image/*" onchange="updateCastRefImage('${c.cast_id}', 'b', this)" ${isLocked ? 'disabled' : ''}/>
          
          <div class="cast-thumb" onclick="${isLocked ? `showImagePopup('${mainImg}')` : `this.parentElement.querySelector('input[data-type=main]').click()`}">
            ${mainImg
              ? `<img src="${cacheBust(mainImg)}"/>`
              : `<span>+</span>`
            }
          </div>
          
          <select class="cast-dropdown" onchange="updateCastRole('${c.cast_id}', this.value)" ${isLocked ? 'disabled' : ''}>
            <option value="lead" ${role === 'lead' ? 'selected' : ''}>LEAD</option>
            <option value="supporting" ${role === 'supporting' ? 'selected' : ''}>SUPPORT</option>
            <option value="extra" ${role === 'extra' ? 'selected' : ''}>EXTRA</option>
          </select>
          
          <div class="cast-slider-wrap">
            <input type="range" class="cast-slider" min="0" max="1" step="0.1" value="${impact}" 
              oninput="this.nextElementSibling.textContent=Math.round(this.value*100)+'%'"
              onchange="updateCastImpact('${c.cast_id}', this.value)" ${isLocked ? 'disabled' : ''}/>
            <span class="cast-slider-val">${Math.round(impact * 100)}%</span>
          </div>
          
          <div class="cast-name-row">
            <input type="text" class="cast-name" placeholder="Name *" value="${c.name || ''}" 
              onchange="updateCastName('${c.cast_id}', this.value)" ${isLocked ? 'disabled' : ''}/>
            ${hasRefs 
              ? '<span class="cast-ready">READY</span>' 
              : (!isLocked ? `<button class="cast-create-btn" onclick="createCastRefs('${c.cast_id}')">CREATE</button>` : '')
            }
          </div>
          
          <div class="cast-prompt-row">
            <input type="text" class="cast-prompt" placeholder="Extra prompt..." value="${promptExtra}" 
              onchange="updateCastPrompt('${c.cast_id}', this.value)" ${isLocked ? 'disabled' : ''}/>
            ${!isLocked && hasRefs ? `<button class="cast-prompt-rerender" onclick="rerenderCastWithPrompt('${c.cast_id}')" title="Rerender with prompt">↻</button>` : ''}
          </div>
          
          <div class="cast-ref-a" onclick="${isLocked ? (refs.ref_a ? `showImagePopup('${refs.ref_a}')` : '') : `this.parentElement.querySelector('input[data-type=ref_a]').click()`}" style="cursor: pointer;">
            ${refs.ref_a
              ? `<img src="${cacheBust(refs.ref_a)}"/>`
              : `<span>A</span>`
            }
            ${!isLocked && refs.ref_a ? `<button class="cast-rerender" onclick="event.stopPropagation(); rerenderSingleRef('${c.cast_id}', 'a')" title="Rerender A">↻</button>` : ''}
          </div>

          <div class="cast-ref-b" onclick="${isLocked ? (refs.ref_b ? `showImagePopup('${refs.ref_b}')` : '') : `this.parentElement.querySelector('input[data-type=ref_b]').click()`}" style="cursor: pointer;">
            ${refs.ref_b
              ? `<img src="${cacheBust(refs.ref_b)}"/>`
              : `<span>B</span>`
            }
            ${!isLocked && refs.ref_b ? `<button class="cast-rerender" onclick="event.stopPropagation(); rerenderSingleRef('${c.cast_id}', 'b')" title="Rerender B">↻</button>` : ''}
          </div>
        </div>
      `;
    } else {
      // v1.4.9.1: Empty slot with full UI (same as filled)
      const defaultImpact = defaultImpacts[defaultRole];
      html += `
        <div class="cast-card empty" data-idx="${idx}">
          <input type="file" class="cast-file-input" accept="image/*" onchange="uploadNewCast(${idx}, '${defaultRole}', this)" ${isLocked ? 'disabled' : ''}/>
          
          <div class="cast-thumb" onclick="this.previousElementSibling.click()">
            <span>+</span>
          </div>
          
          <div class="cast-dropdown empty">${defaultRole.toUpperCase()}</div>
          
          <div class="cast-slider-wrap empty">
            <input type="range" class="cast-slider" min="0" max="1" step="0.1" value="${defaultImpact}" disabled/>
            <span class="cast-slider-val">${Math.round(defaultImpact * 100)}%</span>
          </div>
          
          <div class="cast-name-row">
            <input type="text" class="cast-name" placeholder="Name *" disabled/>
          </div>
          
          <input type="text" class="cast-prompt" placeholder="Extra prompt..." disabled/>
          
          <div class="cast-ref-a"><span>A</span></div>
          <div class="cast-ref-b"><span>B</span></div>
        </div>
      `;
    }
  }
  
  list.innerHTML = html;
  updateCastLockUI(isLocked);
  
  // v1.6.3: Update style lock UI
  const styleLocked = state.project?.style_locked || false;
  updateStyleLockUI(styleLocked);
  
  // v1.5.9: Toggle cast-expanded class when 4+ cast members
  const twoColumn = document.querySelector('.two-column');
  if (twoColumn) {
    if (cast.length > 3) {
      twoColumn.classList.add('cast-expanded');
    } else {
      twoColumn.classList.remove('cast-expanded');
    }
  }
}

async function uploadNewCast(idx, role, input) {
  const f = input.files[0];
  if (!f) return;
  try {
    await ensureProject();
    setStatus("Adding cast member…", null, "castStatus");
    
    const fd = new FormData();
    fd.append("file", f);
    fd.append("role", role);
    fd.append("name", "");
    
    await apiCall(`/api/project/${pid()}/cast`, { method: "POST", body: fd });
    
    // v1.5.4: No auto-ref generation - user clicks CREATE button
    setStatus("Cast added - click CREATE to generate refs", 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.3: Update cast ref image (a or b) from file
async function updateCastRefImage(castId, refType, input) {
  const f = input.files[0];
  if (!f) return;
  try {
    setStatus(`Uploading ref ${refType.toUpperCase()}…`, null, "castStatus");
    
    const fd = new FormData();
    fd.append("file", f);
    
    await apiCall(`/api/project/${pid()}/cast/${castId}/ref/${refType}`, { method: "POST", body: fd });
    
    setStatus(`Ref ${refType.toUpperCase()} updated`, 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.4: Delete cast member
async function deleteCastMember(castId) {
  if (!confirm("Delete this cast member?")) return;
  try {
    setStatus("Deleting cast member…", null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/${castId}`, { method: "DELETE" });
    setStatus("Cast member deleted", 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.4: Create refs for cast member (manual trigger instead of auto)
// v1.5.8: Track pending to disable button, but don't hard block
async function createCastRefs(castId) {
  // Check if already pending - warn but don't hard block
  if (PENDING_CAST_REFS.has(castId)) {
    console.log(`Cast ${castId} refs already in progress`);
    setStatus("Already generating…", null, "castStatus");
    return;
  }
  
  try {
    PENDING_CAST_REFS.add(castId);
    // Disable the button visually
    const btn = document.querySelector(`.cast-create-btn[onclick*="${castId}"]`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = "...";
    }
    
    setStatus("Generating refs…", null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/${castId}/canonical_refs`, { method: "POST" });
    setStatus("Refs created", 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  } finally {
    PENDING_CAST_REFS.delete(castId);
  }
}

async function addCastMember() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      await ensureProject();
      setStatus("Adding cast member…", null, "castStatus");
      
      const castCount = PROJECT_STATE?.cast?.length || 0;
      const role = castCount < 3 ? ["lead","supporting","extra"][castCount] : "extra";
      
      const fd = new FormData();
      fd.append("file", f);
      fd.append("role", role);
      fd.append("name", "");
      
      await apiCall(`/api/project/${pid()}/cast`, { method: "POST", body: fd });
      
      // v1.5.4: No auto-ref generation - user clicks CREATE button
      setStatus("Cast added - click CREATE", 100, "castStatus");
      await refreshFromServer();
    } catch (e) {
      showError(e.message);
    }
  };
  input.click();
}

// v1.4.9.1: Update cast member via API
async function updateCastField(castId, field, value) {
  try {
    const payload = {};
    payload[field] = value;
    await apiCall(`/api/project/${pid()}/cast/${castId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    // Update local state
    const cast = PROJECT_STATE?.cast || [];
    const member = cast.find(c => c.cast_id === castId);
    if (member) member[field] = value;
  } catch (e) {
    console.warn(`Failed to update ${field}:`, e);
  }
}

// v1.4: Update cast member name
async function updateCastName(castId, name) {
  await updateCastField(castId, "name", name);
}

// v1.4: Update cast member role
async function updateCastRole(castId, role) {
  await updateCastField(castId, "role", role);
}

// v1.4: Update cast member impact (screen time)
async function updateCastImpact(castId, impact) {
  const val = parseFloat(impact);
  // Label is updated via oninput handler on slider
  await updateCastField(castId, "impact", val);
}

// v1.4: Update cast member extra prompt
async function updateCastPrompt(castId, promptExtra) {
  await updateCastField(castId, "prompt_extra", promptExtra);
}

// v1.4.9.1: Rerender single ref (A or B)
async function rerenderSingleRef(castId, refType) {
  try {
    setStatus(`Regenerating ref ${refType.toUpperCase()}…`, null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/${castId}/rerender/${refType}`, { method: "POST" });
    setStatus(`Ref ${refType.toUpperCase()} regenerated`, 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.6.3: Rerender both refs with current extra prompt
async function rerenderCastWithPrompt(castId) {
  if (PENDING_CAST_REFS.has(castId)) {
    console.log(`Cast ${castId} refs already in progress`);
    return;
  }
  
  try {
    PENDING_CAST_REFS.add(castId);
    setStatus("Regenerating with extra prompt…", null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/${castId}/canonical_refs`, { method: "POST" });
    setStatus("References regenerated", 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  } finally {
    PENDING_CAST_REFS.delete(castId);
  }
}

// Legacy: Rerender both refs
// v1.5.8: Track pending to prevent duplicates
async function rerenderRef(castId) {
  if (PENDING_CAST_REFS.has(castId)) {
    console.log(`Cast ${castId} refs already in progress`);
    return;
  }
  
  try {
    PENDING_CAST_REFS.add(castId);
    setStatus("Regenerating references…", null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/${castId}/canonical_refs`, { method: "POST" });
    setStatus("References regenerated", 100, "castStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  } finally {
    PENDING_CAST_REFS.delete(castId);
  }
}

// v1.4: Cast lock system
async function toggleCastLock() {
  try {
    await ensureProject();
    const isLocked = PROJECT_STATE?.project?.cast_locked || false;
    const newState = !isLocked;
    
    // v1.5.3: Confirm unlock if timeline exists
    if (isLocked && !newState) {
      const hasTimeline = PROJECT_STATE?.storyboard?.sequences?.length > 0;
      if (hasTimeline) {
        const ok = confirm("Unlocking cast may require regenerating the timeline if you change cast members. Continue?");
        if (!ok) return;
      }
    }
    
    // Check if we have at least one cast member before locking
    if (newState && (!PROJECT_STATE?.cast || PROJECT_STATE.cast.length === 0)) {
      showError("Add at least one cast member before locking");
      return;
    }
    
    // Check if all cast members have names (required)
    if (newState) {
      const noName = PROJECT_STATE.cast.find(c => !c.name?.trim());
      if (noName) {
        showError("All cast members must have names before locking");
        return;
      }
    }
    
    setStatus(newState ? "Locking cast…" : "Unlocking cast…", null, "castStatus");
    await apiCall(`/api/project/${pid()}/cast/lock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locked: newState })
    });
    
    PROJECT_STATE.project.cast_locked = newState;
    updateCastLockUI(newState);
    renderCastList(PROJECT_STATE);  // v1.5.3: Re-render to enable/disable inputs
    setStatus(newState ? "Cast locked" : "Cast unlocked", 100, "castStatus");
  } catch (e) {
    showError(e.message);
  }
}

function updateCastLockUI(isLocked) {
  const lockBtn = document.getElementById("lockCastBtn");
  const lockedBadge = document.getElementById("castLockedBadge");
  const addBtn = document.getElementById("addCastBtnContainer");
  
  if (isLocked) {
    lockBtn?.classList.add("hidden");
    lockedBadge?.classList.remove("hidden");
    addBtn?.classList.add("hidden");
    // Disable cast editing
    document.querySelectorAll(".cast-card input, .cast-card select").forEach(el => el.disabled = true);
    document.querySelectorAll(".cast-card .cast-rerender").forEach(el => el.disabled = true);
  } else {
    lockBtn?.classList.remove("hidden");
    lockedBadge?.classList.add("hidden");
    addBtn?.classList.remove("hidden");
    // Enable cast editing
    document.querySelectorAll(".cast-card input, .cast-card select").forEach(el => el.disabled = false);
    document.querySelectorAll(".cast-card .cast-rerender").forEach(el => el.disabled = false);
  }
  
  // v1.5.4: Update storyboard buttons based on both audio and cast lock
  updateButtonStates();
}

/// v1.6.5: Style lock UI removed - no badge shown
// Style lock still functions internally, just no UI indicator
function updateStyleLockUI(isLocked) {
  // v1.6.5: Badge completely removed from UI per bugfix 4
  // Style lock is handled internally without visual indicator
}

// v1.6.3: Clear style lock
async function clearStyleLock() {
  if (!pid()) return;
  
  const confirm = window.confirm(
    "Clear style lock?\n\n" +
    "This will remove the style anchor image.\n" +
    "New cast refs may have different visual styles."
  );
  if (!confirm) return;
  
  try {
    await apiCall(`/api/project/${pid()}/clear_style_lock`, { method: "POST" });
    if (PROJECT_STATE?.project) {
      PROJECT_STATE.project.style_locked = false;
      PROJECT_STATE.project.style_lock_image = null;
    }
    updateStyleLockUI(false);
    setStatus("Style lock cleared", 100, "castStatus");
  } catch (e) {
    showError("Failed to clear style lock: " + e.message);
  }
}

// ========= Storyboard =========
async function createTimeline() {
  try {
    await ensureProject();
    if (!PROJECT_STATE?.audio_dna) {
      showError("Import audio first");
      return;
    }
    
    // v1.5.4: Check both audio and cast lock
    if (!PROJECT_STATE?.project?.cast_locked) {
      showError("Lock cast first");
      return;
    }
    
    setStatus("Creating timeline…", null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/sequences/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm: document.getElementById("llm").value })
    });
    
    // v1.5.4: Automatically build scenes after timeline
    setStatus("Building scenes…", 30, "storyboardStatus");
    await refreshFromServer();
    
    // Get sequences and generate scenes
    const seqs = PROJECT_STATE?.storyboard?.sequences || [];
    if (seqs.length > 0) {
      const result = await apiCall(`/api/project/${pid()}/castmatrix/scenes/autogen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: seqs.length, llm: document.getElementById("llm").value })
      });
      
      const scenes = result.scenes || [];
      
      // Render each scene with UI refresh
      for (let i = 0; i < scenes.length; i++) {
        const sc = scenes[i];
        const pct = 40 + Math.round((i / scenes.length) * 50);
        setStatus(`Rendering scene ${i + 1}/${scenes.length}…`, pct, "storyboardStatus");
        
        try {
          await apiCall(`/api/project/${pid()}/castmatrix/scene/${sc.scene_id}/render`, {
            method: "POST"
          });
          // v1.5.4: Refresh UI after each scene to show progress
          const state = await apiCall(`/api/project/${pid()}`);
          PROJECT_STATE = state;
          renderTimeline(state);
        } catch (e) {
          console.warn(`Scene ${sc.scene_id} render failed:`, e);
        }
      }
    }
    
    setStatus(`${seqs.length} scenes created`, 100, "storyboardStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.3: Repair timeline - fix sequences exceeding audio duration
async function repairTimeline() {
  try {
    if (!pid()) {
      showError("No project loaded");
      return;
    }
    
    setStatus("Repairing timeline…", null);
    const result = await apiCall(`/api/project/${pid()}/sequences/repair`, {
      method: "POST"
    });
    
    let msg = `Repaired: ${result.repaired_sequences} scenes, ${result.repaired_shots} shots`;
    if (result.removed_sequences?.length > 0) {
      msg += ` (removed: ${result.removed_sequences.join(", ")})`;
    }
    if (result.capped_sequences?.length > 0) {
      msg += ` (capped: ${result.capped_sequences.join(", ")})`;
    }
    
    setStatus(msg, 100);
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// Legacy: Build scenes separately (kept for compatibility)
async function buildScenes() {
  try {
    const seqs = PROJECT_STATE?.storyboard?.sequences || [];
    if (!seqs.length) {
      showError("Create timeline first");
      return;
    }
    
    setStatus("Building scenes…", 10);
    
    const result = await apiCall(`/api/project/${pid()}/castmatrix/scenes/autogen`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count: seqs.length, llm: document.getElementById("llm").value })
    });
    
    const scenes = result.scenes || [];
    
    // v1.5.3: Add all scenes to unified render queue
    scenes.forEach(sc => {
      const item = {type: "scene", id: sc.scene_id};
      if (!RENDER_QUEUE.some(q => q.type === "scene" && q.id === sc.scene_id)) {
        RENDER_QUEUE.push(item);
      }
    });
    
    setStatus(`Queued ${scenes.length} scenes for rendering…`, null);
    await refreshFromServer();  // Update UI with new scenes
    
    // Start processing
    processRenderQueue();
  } catch (e) {
    showError(e.message);
  }
}

// Re-render single scene
async function rerenderScene(sceneId) {
  // v1.6.3: Check if decor is locked
  const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
  if (scene?.decor_locked) {
    showError("Scene decor is locked. Unlock to re-render.");
    return;
  }
  
  try {
    setStatus(`Re-rendering scene…`, null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/render`, { method: "POST" });
    setStatus("Scene re-rendered", 100, "storyboardStatus");
    await refreshFromServer();
    // Refresh popup if open
    if (!document.getElementById("scenePopup").classList.contains("hidden")) {
      showScenePopup(sceneId);
    }
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.4: Edit scene with custom prompt (img2img on current scene image)
async function editSceneWithPrompt(sceneId, editPrompt) {
  if (!editPrompt?.trim()) {
    showError("Enter an edit prompt");
    return;
  }
  
  // v1.6.3: Check if decor is locked
  const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
  if (scene?.decor_locked) {
    showError("Scene decor is locked. Unlock to edit.");
    return;
  }
  
  try {
    setStatus(`Editing scene…`, null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edit_prompt: editPrompt.trim() })
    });
    setStatus("Scene edited", 100, "storyboardStatus");
    // Clear the popup input
    const input = document.getElementById("sceneRepromptInput");
    if (input) input.value = "";
    await refreshFromServer();
    // Refresh popup if open
    if (!document.getElementById("scenePopup").classList.contains("hidden")) {
      showScenePopup(sceneId);
    }
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.7: Import custom image for scene
function importSceneImage(sceneId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    try {
      setStatus("Uploading scene image…", null, "storyboardStatus");
      const formData = new FormData();
      formData.append("file", file);
      
      const result = await fetch(`/api/project/${pid()}/castmatrix/scene/${sceneId}/import`, {
        method: "POST",
        body: formData
      });
      
      if (!result.ok) {
        const err = await result.json();
        throw new Error(err.detail || "Upload failed");
      }
      
      setStatus("Scene image imported", 100, "storyboardStatus");
      await refreshFromServer();
    } catch (err) {
      showError(err.message);
    }
  };
  input.click();
}

function updateSceneCard(sceneId) {
  const scenes = PROJECT_STATE?.cast_matrix?.scenes || [];
  const sc = scenes.find(s => s.scene_id === sceneId);
  if (!sc) return;
  
  const sceneIdx = scenes.indexOf(sc);
  const cards = document.querySelectorAll('.scene-card');
  if (sceneIdx < cards.length) {
    const card = cards[sceneIdx];
    const rendersContainer = card.querySelector('.scene-card-renders');
    if (rendersContainer && sc.decor_refs?.length && sc.decor_refs[0]) {
      rendersContainer.innerHTML = `
        <div class="scene-render-container">
          <img class="scene-render-img" src="${cacheBust(sc.decor_refs[0])}" onclick="showImagePopup('${sc.decor_refs[0]}')"/>
          <button class="rerender-btn" onclick="rerenderScene('${sc.scene_id}')" title="Re-render">↻</button>
        </div>
      `;
    }
  }
}

async function sceneToShots() {
  if (!SELECTED_SEQUENCE_ID) {
    showError("Select a scene from timeline");
    return;
  }
  try {
    setStatus("Expanding to shots…", null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/shots/expand_sequence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sequence_id: SELECTED_SEQUENCE_ID })
    });
    setStatus("Shots created", 100, "storyboardStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

async function allShots() {
  try {
    setStatus("Expanding all to shots…", null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/shots/expand_all`, { method: "POST" });
    setStatus("All shots created", 100, "storyboardStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// Patch 5: Show scenes count + actual duration
function renderTimeline(state) {
  const container = document.getElementById("timelineContainer");
  const info = document.getElementById("timelineInfo");
  const summaryBox = document.getElementById("storySummaryBox");
  const summaryText = document.getElementById("storySummaryText");
  
  const seqs = state.storyboard?.sequences || [];
  const scenes = state.cast_matrix?.scenes || [];
  const duration = AUDIO_DATA.duration || state.audio_dna?.duration_sec || state.audio_dna?.meta?.duration_sec || 0;
  const storySummary = state.storyboard?.story_summary || "";
  
  // v1.5.4: Queue tracking for scenes
  const inQueueScenes = RENDER_QUEUE.filter(q => q.type === "scene").map(q => q.id);
  
  // v1.4.9.1: Show scenes count and actual duration
  info.textContent = scenes.length 
    ? `${scenes.length} scenes • ${Math.round(duration)}s` 
    : (seqs.length ? `${seqs.length} scenes • ${Math.round(duration)}s` : "");
  
  // Show story summary above timeline
  if (storySummary) {
    summaryText.textContent = storySummary;
    summaryBox.classList.remove("hidden");
  } else {
    summaryBox.classList.add("hidden");
  }
  
  if (!seqs.length) {
    container.innerHTML = '<div class="muted" style="padding:16px;text-align:center;">Click "Create Timeline" to generate scenes</div>';
    return;
  }
  
  // v1.5.4: Timeline with scene cards including edit prompt
  container.innerHTML = `<div class="timeline-segments-v2">${seqs.map((seq, idx) => {
    const selected = SELECTED_SEQUENCE_ID === seq.sequence_id ? "selected" : "";
    const scene = scenes.find(s => s.sequence_id === seq.sequence_id) || scenes[idx];
    const hasScene = !!scene;
    const thumb = scene?.decor_refs?.[0] || "";
    const sceneTitle = scene?.title || seq.label || `Scene ${idx + 1}`;
    const queuePos = inQueueScenes.indexOf(scene?.scene_id);
    const inQueue = queuePos >= 0;
    const hasWardrobe = scene?.wardrobe?.trim();
    
    return `
      <div class="timeline-seg-v2 ${selected} ${inQueue ? 'in-queue' : ''}" onclick="selectSequence('${seq.sequence_id}')" data-scene-id="${scene?.scene_id || ''}">
        <div class="timeline-seg-thumb" onclick="event.stopPropagation(); ${thumb ? `showScenePopup('${scene?.scene_id}')` : ''}">
          ${thumb
            ? `<img src="${cacheBust(thumb)}"/>`
            : (inQueue ? `<span class="queue-num">#${queuePos + 1}</span>` : `<span>${idx + 1}</span>`)
          }
          ${hasScene && !thumb && !inQueue ? `<button class="scene-import-btn" onclick="event.stopPropagation(); importSceneImage('${scene.scene_id}')" title="Import image">📁</button>` : ''}
          ${hasWardrobe ? `<span class="wardrobe-indicator" title="${scene.wardrobe}"><svg viewBox="0 0 512 512" width="12" height="12" fill="currentColor"><path d="M256 96c-66 0-128 32-160 80-16 24-16 56 0 80 8 12 8 28 0 40l-32 48c-8 12-8 28 0 40 16 24 48 40 80 40h224c32 0 64-16 80-40 8-12 8-28 0-40l-32-48c-8-12-8-28 0-40 16-24 16-56 0-80-32-48-94-80-160-80z"/></svg></span>` : ''}
          ${scene?.decor_locked ? `<span class="decor-lock-indicator"><svg viewBox="0 0 24 24" width="10" height="10" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM12 17c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z"/></svg></span>` : ''}
        </div>
        <div class="timeline-seg-info">
          <div class="timeline-seg-title">${sceneTitle}</div>
          <div class="timeline-seg-sub">${seq.structure_type || ""}</div>
        </div>
      </div>
    `;
  }).join("")}</div>`;
}

function selectSequence(seqId) {
  SELECTED_SEQUENCE_ID = seqId;
  renderTimeline(PROJECT_STATE);
  renderShots(PROJECT_STATE);
  updateButtonStates();
}

// v1.6.5: Show scene details popup with 3 preview boxes
function showScenePopup(sceneId) {
  const scenes = PROJECT_STATE?.cast_matrix?.scenes || [];
  const scene = scenes.find(s => s.scene_id === sceneId);
  if (!scene) return;

  const thumb = scene.decor_refs?.[0] || "";
  const thumbAlt = scene.decor_alt || "";
  const wardrobeRef = scene.wardrobe_ref || "";
  const title = scene.title || 'Untitled Scene';
  const prompt = scene.prompt || scene.description || 'No description';
  const wardrobe = scene.wardrobe || '';
  const decorLocked = scene.decor_locked || false;
  const wardrobeLocked = scene.wardrobe_locked || false;

  // Set title and prompt
  document.getElementById("scenePopupTitle").textContent = title;
  document.getElementById("scenePopupPrompt").textContent = prompt;

  // DECOR 1 (MAIN) - Main image
  const img = document.getElementById("scenePopupImage");
  if (img) {
    if (thumb) {
      img.src = cacheBust(thumb);
      img.style.display = "block";
      img.onclick = () => showImagePopup(thumb);
    } else {
      img.style.display = "none";
    }
  }

  // Decor lock badge
  const decorLockBadge = document.getElementById("scenePopupDecorLock");
  if (decorLockBadge) {
    decorLockBadge.classList.toggle("hidden", !decorLocked);
  }

  // v1.6.5: DECOR 1 controls with shot-card styling (input, +, →, lock)
  const decor1Prompt = document.getElementById("sceneDecor1Prompt");
  const decor1RefBtn = document.getElementById("sceneDecor1RefBtn");
  const decor1Go = document.getElementById("sceneDecor1Go");
  const decor1Lock = document.getElementById("sceneDecor1Lock");

  if (decor1Prompt) {
    decor1Prompt.value = "";
    decor1Prompt.disabled = decorLocked;
    decor1Prompt.onkeydown = (e) => {
      if (e.key === 'Enter') editSceneWithPrompt(sceneId, decor1Prompt.value);
    };
  }
  if (decor1RefBtn) {
    decor1RefBtn.onclick = () => openSceneRefPicker(sceneId, 'decor1');
    decor1RefBtn.disabled = decorLocked;
  }
  if (decor1Go) {
    decor1Go.onclick = () => decor1Prompt?.value ? editSceneWithPrompt(sceneId, decor1Prompt.value) : rerenderScene(sceneId);
    decor1Go.disabled = decorLocked;
  }
  if (decor1Lock) {
    decor1Lock.textContent = decorLocked ? "🔓" : "🔒";
    decor1Lock.title = decorLocked ? "Unlock decor" : "Lock decor";
    decor1Lock.onclick = () => toggleSceneDecorLock(sceneId);
  }

  // DECOR 2 (ALT) - Alt image
  const altImg = document.getElementById("scenePopupImageAltImg");
  if (altImg) {
    if (thumbAlt) {
      altImg.src = cacheBust(thumbAlt);
      altImg.style.display = "block";
      altImg.onclick = () => showImagePopup(thumbAlt);
    } else {
      altImg.style.display = "none";
    }
  }

  // v1.6.5: DECOR 2 controls with shot-card styling (input, +, →)
  const decor2Prompt = document.getElementById("sceneDecor2Prompt");
  const decor2RefBtn = document.getElementById("sceneDecor2RefBtn");
  const decor2Go = document.getElementById("sceneDecor2Go");

  if (decor2Prompt) {
    decor2Prompt.value = "";
    decor2Prompt.onkeydown = (e) => {
      if (e.key === 'Enter') generateAltDecor(sceneId, decor2Prompt.value);
    };
  }
  if (decor2RefBtn) {
    decor2RefBtn.onclick = () => openSceneRefPicker(sceneId, 'decor2');
  }
  if (decor2Go) {
    decor2Go.onclick = () => generateAltDecor(sceneId, decor2Prompt?.value || "");
  }

  // WARDROBE PREVIEW
  const wardrobeImg = document.getElementById("sceneWardrobePreviewImg");
  const wardrobeEmpty = document.getElementById("sceneWardrobeEmpty");

  if (wardrobeImg && wardrobeEmpty) {
    if (wardrobeRef) {
      wardrobeImg.src = cacheBust(wardrobeRef);
      wardrobeImg.style.display = "block";
      wardrobeImg.onclick = () => showImagePopup(wardrobeRef);
      wardrobeEmpty.style.display = "none";
    } else {
      wardrobeImg.style.display = "none";
      wardrobeEmpty.style.display = "block";
    }
  }

  // v1.6.5: WARDROBE controls with shot-card styling (input, +, →, lock)
  const wardrobeInput = document.getElementById("sceneWardrobeInput");
  const wardrobeRefBtn = document.getElementById("sceneWardrobeRefBtn");
  const wardrobeGo = document.getElementById("sceneWardrobeGo");
  const wardrobeLockBtn = document.getElementById("sceneWardrobeLock");

  if (wardrobeInput) {
    wardrobeInput.value = wardrobe;
    wardrobeInput.disabled = wardrobeLocked;
    wardrobeInput.onkeydown = (e) => {
      if (e.key === 'Enter') {
        updateSceneWardrobeAndGenerate(sceneId, wardrobeInput.value);
      }
    };
  }
  if (wardrobeRefBtn) {
    wardrobeRefBtn.onclick = () => openSceneRefPicker(sceneId, 'wardrobe');
    wardrobeRefBtn.disabled = wardrobeLocked;
  }
  if (wardrobeGo) {
    wardrobeGo.onclick = () => updateSceneWardrobeAndGenerate(sceneId, wardrobeInput?.value || "");
    wardrobeGo.disabled = wardrobeLocked;
  }
  if (wardrobeLockBtn) {
    wardrobeLockBtn.textContent = wardrobeLocked ? "🔓" : "🔒";
    wardrobeLockBtn.title = wardrobeLocked ? "Unlock wardrobe" : "Lock wardrobe";
    wardrobeLockBtn.onclick = () => toggleSceneWardrobeLock(sceneId);
  }

  document.getElementById("scenePopup").classList.remove("hidden");
}

// v1.6.5: Update wardrobe and generate preview in one step
async function updateSceneWardrobeAndGenerate(sceneId, wardrobeText) {
  if (!wardrobeText?.trim()) {
    showError("Enter wardrobe description first");
    return;
  }

  try {
    // First update the wardrobe text
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/wardrobe`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wardrobe: wardrobeText.trim() })
    });

    // Update local state
    const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
    if (scene) scene.wardrobe = wardrobeText.trim();

    // Then generate the preview
    await generateWardrobeRef(sceneId);
  } catch (e) {
    showError("Failed to update wardrobe: " + e.message);
  }
}

// v1.6.5: Generate alt decor image
async function generateAltDecor(sceneId, altPrompt) {
  try {
    setStatus("Generating alt decor...", null, "storyboardStatus");

    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/decor_alt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: altPrompt || "" })
    });

    await refreshFromServer();
    setStatus("Alt decor generated", 100, "storyboardStatus");
    showScenePopup(sceneId);
  } catch (e) {
    showError("Failed to generate alt decor: " + e.message);
  }
}

// v1.6.5: Scene reference picker - similar to shot ref picker
// Type can be 'decor1', 'decor2', or 'wardrobe'
window.SCENE_REF_CONTEXT = null;

function openSceneRefPicker(sceneId, type) {
  const picker = document.getElementById("shotRefPicker");  // Reuse shot ref picker popup
  const content = document.getElementById("shotRefPickerContent");

  // Get cast refs
  const cast = PROJECT_STATE?.cast || [];
  const charRefs = PROJECT_STATE?.cast_matrix?.character_refs || {};

  // Get scene decors for reference
  const scenes = PROJECT_STATE?.cast_matrix?.scenes || [];

  // Build cast refs section
  const castRefsHtml = cast.map(c => {
    const refs = charRefs[c.cast_id] || {};
    const refA = refs.ref_a;
    const refB = refs.ref_b;
    if (!refA && !refB) return '';

    return `
      <div class="ref-pick-cast">
        <div class="ref-pick-cast-name">${c.name || c.cast_id}</div>
        <div class="ref-pick-cast-imgs">
          ${refA ? `<img src="${cacheBust(refA)}" onclick="selectSceneRef('${sceneId}', '${type}', '${refA}', '${c.cast_id}_A')" title="Ref A"/>` : ''}
          ${refB ? `<img src="${cacheBust(refB)}" onclick="selectSceneRef('${sceneId}', '${type}', '${refB}', '${c.cast_id}_B')" title="Ref B"/>` : ''}
        </div>
      </div>
    `;
  }).filter(Boolean).join("");

  // Build scene decors section (for reference)
  const sceneDecorsHtml = scenes.filter(s => s.decor_refs?.[0]).map(s => `
    <div class="ref-pick-item" onclick="selectSceneRef('${sceneId}', '${type}', '${s.decor_refs[0]}', '${s.scene_id}')">
      <img src="${cacheBust(s.decor_refs[0])}"/>
      <div class="ref-pick-label">${s.title || s.scene_id}</div>
    </div>
  `).join("");

  content.innerHTML = `
    <h4 style="margin:0 0 8px;color:#888;">Select Reference for ${type === 'wardrobe' ? 'Wardrobe' : type === 'decor2' ? 'Alt Decor' : 'Main Decor'}</h4>
    ${castRefsHtml ? `
      <div class="ref-section">
        <div class="ref-section-title">CAST REFS</div>
        <div class="ref-cast-grid">${castRefsHtml}</div>
      </div>
    ` : ''}
    ${sceneDecorsHtml ? `
      <div class="ref-section">
        <div class="ref-section-title">SCENE DECORS</div>
        <div class="ref-shots-grid">${sceneDecorsHtml}</div>
      </div>
    ` : ''}
    ${!castRefsHtml && !sceneDecorsHtml ? '<div class="muted">No references available</div>' : ''}
  `;

  window.SCENE_REF_CONTEXT = { sceneId, type };
  picker.classList.remove("hidden");
}

// Select a reference for scene element
function selectSceneRef(sceneId, type, refUrl, refLabel) {
  // Visual feedback
  const btn = document.getElementById(`scene${type.charAt(0).toUpperCase() + type.slice(1)}RefBtn`);
  if (btn) {
    btn.textContent = "✓";
    btn.title = `Ref: ${refLabel}`;
  }

  // Store for later use (when go button is clicked)
  window.SCENE_REF_SELECTED = window.SCENE_REF_SELECTED || {};
  window.SCENE_REF_SELECTED[`${sceneId}_${type}`] = refUrl;

  hidePopup("shotRefPicker");
}

// v1.6.3: Update scene wardrobe
async function updateSceneWardrobe(sceneId) {
  const input = document.getElementById("sceneWardrobeInput");
  if (!input) return;
  
  const newWardrobe = input.value.trim();
  
  try {
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/wardrobe`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wardrobe: newWardrobe })
    });
    
    // Update local state
    const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
    if (scene) scene.wardrobe = newWardrobe;
    
    renderTimeline(PROJECT_STATE);
    setStatus("Wardrobe updated", 100, "storyboardStatus");
    document.getElementById("scenePopup").classList.add("hidden");
  } catch (e) {
    showError("Failed to update wardrobe: " + e.message);
  }
}

// v1.6.3: Toggle scene decor lock
async function toggleSceneDecorLock(sceneId) {
  try {
    const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
    const newState = !scene?.decor_locked;
    
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/decor_lock`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locked: newState })
    });
    
    if (scene) scene.decor_locked = newState;
    renderTimeline(PROJECT_STATE);
    showScenePopup(sceneId); // Refresh popup
  } catch (e) {
    showError("Failed to toggle decor lock: " + e.message);
  }
}

// v1.6.3: Toggle scene wardrobe lock
async function toggleSceneWardrobeLock(sceneId) {
  try {
    const scene = PROJECT_STATE?.cast_matrix?.scenes?.find(s => s.scene_id === sceneId);
    const newState = !scene?.wardrobe_locked;
    
    await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/wardrobe_lock`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locked: newState })
    });
    
    if (scene) scene.wardrobe_locked = newState;
    showScenePopup(sceneId); // Refresh popup
  } catch (e) {
    showError("Failed to toggle wardrobe lock: " + e.message);
  }
}

// v1.6.3: Generate wardrobe preview (cast ref_a + decor + wardrobe prompt)
async function generateWardrobeRef(sceneId) {
  try {
    setStatus("Generating wardrobe preview...", null, "storyboardStatus");
    
    const result = await apiCall(`/api/project/${pid()}/castmatrix/scene/${sceneId}/wardrobe_ref`, {
      method: "POST"
    });
    
    await refreshFromServer();
    setStatus("Wardrobe preview generated", 100, "storyboardStatus");
    showScenePopup(sceneId); // Refresh popup
  } catch (e) {
    showError("Failed to generate wardrobe preview: " + e.message);
  }
}

// v1.4.9.1: renderScenes now empty (scenes shown in timeline)
function renderScenes(state) {
  // Scenes are now rendered inside the timeline segments
  // This function is kept for backward compatibility
}

// v1.5: Scrollable desc, rerender buttons, queue status
function renderShots(state) {
  const grid = document.getElementById("shotsGrid");
  const badge = document.getElementById("shotsCount");
  
  const allShots = state.storyboard?.shots || [];
  const shots = SELECTED_SEQUENCE_ID 
    ? allShots.filter(s => s.sequence_id === SELECTED_SEQUENCE_ID)
    : allShots;
  
  badge.textContent = shots.length;
  
  if (!shots.length) {
    grid.innerHTML = '<div class="muted">No shots yet</div>';
    return;
  }
  
  // v1.5.4: Get cast list for name lookup
  const castList = state.cast || [];
  
  grid.innerHTML = shots.map(sh => {
    const duration = ((sh.end || 0) - (sh.start || 0)).toFixed(1);
    const energy = sh.energy ? `E${Math.round(sh.energy * 10)}` : "";
    const desc = sh.intent || sh.prompt_base || "";
    const hasRender = sh.render?.image_url;
    
    // v1.5.4: Display shot ID as sc01_sh01 (replace seq_ with sc)
    const displayId = sh.shot_id.replace(/seq_(\d+)/, 'sc$1');
    
    // v1.5.4: Get cast member names
    const castNames = (sh.cast || []).map(cid => {
      const member = castList.find(c => c.cast_id === cid);
      return member?.name || cid;
    }).join(", ");
    
    // v1.5.4: Queue status classes (object-based queue)
    const inQueue = RENDER_QUEUE.some(q => q.type === "shot" && q.id === sh.shot_id);
    const queuePos = RENDER_QUEUE.findIndex(q => q.type === "shot" && q.id === sh.shot_id);
    const statusClass = inQueue ? "in-queue" : "";
    
    return `
      <div class="shot-card ${statusClass}" data-shot-id="${sh.shot_id}">
        <div class="shot-card-title">
          <span>${displayId}</span>
          <span>${duration}s ${energy}</span>
        </div>
        <div class="shot-card-body">
          ${castNames 
            ? `<div class="shot-card-cast">${castNames}</div>`
            : `<div class="shot-card-no-cast">No cast</div>`
          }
          <div class="shot-card-desc">${desc}</div>
          <div class="shot-render-container">
            ${hasRender
              ? `<img class="shot-render-img" src="${cacheBust(sh.render.image_url)}" onclick="showImagePopup('${sh.render.image_url}')"/>
                 <button class="rerender-btn" onclick="event.stopPropagation(); renderShot('${sh.shot_id}')" title="Re-render">↻</button>`
              : inQueue
                ? `<div class="shot-render-placeholder queue-status">
                     <span>Queue #${queuePos + 1}</span>
                     ${queuePos > 0 ? `<button class="small" onclick="prioritizeShot('${sh.shot_id}')">↑</button>` : ''}
                   </div>`
                : `<div class="shot-render-placeholder">
                     <span>Not rendered</span>
                     <button class="small" onclick="renderShot('${sh.shot_id}')">Render</button>
                   </div>`
            }
          </div>
          ${hasRender ? `
          <div class="shot-edit-row">
            <input type="text" class="shot-edit-input" placeholder="Edit prompt..." data-shot-id="${sh.shot_id}" onkeydown="if(event.key==='Enter'){event.preventDefault();quickEditShot('${sh.shot_id}', event.target.value);}"/>
            <button class="shot-ref-btn" onclick="openShotRefPicker('${sh.shot_id}')" title="Add reference">+</button>
            <button class="shot-edit-go" onclick="quickEditShot('${sh.shot_id}', document.querySelector('.shot-edit-input[data-shot-id=\\'${sh.shot_id}\\']').value)" title="Apply edit">→</button>
          </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join("");
}

// v1.6.5: Track individual renders for stop button functionality
async function renderShot(shotId) {
  // Check if stopped before starting
  if (RENDER_STOPPED) {
    setStatus("Rendering stopped", 100, "storyboardStatus");
    return;
  }

  try {
    ACTIVE_RENDERS++;
    showStopButton();  // v1.6.5: Show stop button for any render

    setStatus(`Rendering ${shotId}…`, null, "storyboardStatus");

    // Check stop flag during render
    if (RENDER_STOPPED) {
      setStatus("Rendering stopped", 100, "storyboardStatus");
      return;
    }

    await apiCall(`/api/project/${pid()}/shot/${shotId}/render`, { method: "POST" });

    if (!RENDER_STOPPED) {
      setStatus("Shot rendered", 100, "storyboardStatus");
      await refreshFromServer();
    }
  } catch (e) {
    if (!RENDER_STOPPED) {
      showError(e.message);
    }
  } finally {
    ACTIVE_RENDERS--;
    if (ACTIVE_RENDERS === 0) {
      hideStopButton();  // v1.6.5: Hide stop button when all renders done
      RENDER_STOPPED = false;  // Reset flag for next render
    }
  }
}

// v1.6.5: Helper to show stop button
function showStopButton() {
  const stopBtn = document.getElementById("stopRenderBtn");
  const renderAllBtn = document.getElementById("renderAllShotsBtn");
  if (stopBtn) stopBtn.classList.remove("hidden");
  if (renderAllBtn) renderAllBtn.classList.add("hidden");
}

// v1.6.5: Helper to hide stop button
function hideStopButton() {
  const stopBtn = document.getElementById("stopRenderBtn");
  const renderAllBtn = document.getElementById("renderAllShotsBtn");
  if (stopBtn) stopBtn.classList.add("hidden");
  if (renderAllBtn) renderAllBtn.classList.remove("hidden");
}

// v1.5.4: Quick edit shot with prompt only (uses existing shot/edit endpoint)
async function quickEditShot(shotId, editPrompt) {
  if (!editPrompt?.trim()) {
    showError("Enter an edit prompt");
    return;
  }
  
  // Check if there's a reference image selected
  const refImg = window.SHOT_QUICK_REF?.[shotId] || null;
  
  try {
    setStatus(`Editing shot…`, null, "storyboardStatus");
    await apiCall(`/api/project/${pid()}/shot/${shotId}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        edit_prompt: editPrompt.trim(),
        extra_cast: [],
        ref_image: refImg  // v1.5.4: Optional reference image from another shot
      })
    });
    // Clear input and ref
    const input = document.querySelector(`.shot-edit-input[data-shot-id="${shotId}"]`);
    if (input) input.value = "";
    delete window.SHOT_QUICK_REF?.[shotId];
    
    setStatus("Shot edited", 100, "storyboardStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.5.4: Ref picker for quick shot edit - allows selecting another shot's image as reference
window.SHOT_QUICK_REF = {};

// v1.5.5: Reference picker - shows cast refs AND other rendered shots
function openShotRefPicker(shotId) {
  const picker = document.getElementById("shotRefPicker");
  const content = document.getElementById("shotRefPickerContent");
  
  // Get cast refs
  const cast = PROJECT_STATE?.cast || [];
  const charRefs = PROJECT_STATE?.cast_matrix?.character_refs || {};
  
  // Build cast refs section
  const castRefsHtml = cast.map(c => {
    const refs = charRefs[c.cast_id] || {};
    const refA = refs.ref_a;
    const refB = refs.ref_b;
    if (!refA && !refB) return '';
    
    return `
      <div class="ref-pick-cast">
        <div class="ref-pick-cast-name">${c.name || c.cast_id}</div>
        <div class="ref-pick-cast-imgs">
          ${refA ? `<img src="${cacheBust(refA)}" onclick="selectShotRef('${shotId}', '${refA}', '${c.cast_id}_A')" title="Ref A"/>` : ''}
          ${refB ? `<img src="${cacheBust(refB)}" onclick="selectShotRef('${shotId}', '${refB}', '${c.cast_id}_B')" title="Ref B"/>` : ''}
        </div>
      </div>
    `;
  }).filter(Boolean).join("");
  
  // Get other rendered shots
  const shots = PROJECT_STATE?.storyboard?.shots || [];
  const rendered = shots.filter(s => s.render?.image_url && s.shot_id !== shotId);
  
  const shotsHtml = rendered.map(s => `
    <div class="ref-pick-item" onclick="selectShotRef('${shotId}', '${s.render.image_url}', '${s.shot_id}')">
      <img src="${cacheBust(s.render.image_url)}"/>
      <div class="ref-pick-label">${s.shot_id.replace(/seq_(\d+)/, 'sc$1')}</div>
    </div>
  `).join("");
  
  content.innerHTML = `
    ${castRefsHtml ? `
      <div class="ref-section">
        <div class="ref-section-title">CAST REFS</div>
        <div class="ref-cast-grid">${castRefsHtml}</div>
      </div>
    ` : ''}
    ${shotsHtml ? `
      <div class="ref-section">
        <div class="ref-section-title">OTHER SHOTS</div>
        <div class="ref-shots-grid">${shotsHtml}</div>
      </div>
    ` : ''}
    ${!castRefsHtml && !shotsHtml ? '<div class="muted">No references available</div>' : ''}
  `;
  
  window.PICKING_REF_FOR = shotId;
  picker.classList.remove("hidden");
}

function selectShotRef(forShotId, refUrl, refLabel) {
  window.SHOT_QUICK_REF[forShotId] = refUrl;
  
  // Visual feedback - update the + button
  const btn = document.querySelector(`.shot-edit-row input[data-shot-id="${forShotId}"]`)?.parentElement?.querySelector('.shot-ref-btn');
  if (btn) {
    btn.textContent = "✓";
    btn.title = `Ref: ${refLabel}`;
  }
  
  hidePopup("shotRefPicker");
}

// v1.5.3: Shot Editor - edit rendered shots with custom prompts and extra refs
let EDITING_SHOT_ID = null;

function openShotEditor(shotId) {
  EDITING_SHOT_ID = shotId;
  const shot = PROJECT_STATE?.storyboard?.shots?.find(s => s.shot_id === shotId);
  if (!shot || !shot.render?.image_url) return;
  
  const popup = document.getElementById("shotEditorPopup");
  const img = document.getElementById("shotEditorImage");
  const promptInput = document.getElementById("shotEditPrompt");
  const castSelect = document.getElementById("shotEditorCast");
  
  img.src = cacheBust(shot.render.image_url);
  promptInput.value = "";
  
  // Populate cast selector
  const cast = PROJECT_STATE?.cast || [];
  castSelect.innerHTML = '<option value="">-- Add cast member --</option>' +
    cast.map(c => `<option value="${c.cast_id}">${c.name || c.cast_id} (${c.role})</option>`).join("");
  
  // Clear extra refs display
  document.getElementById("shotEditorExtraRefs").innerHTML = "";
  window.SHOT_EDITOR_EXTRA_CAST = [];
  
  popup.classList.remove("hidden");
}

function closeShotEditor() {
  document.getElementById("shotEditorPopup").classList.add("hidden");
  EDITING_SHOT_ID = null;
  window.SHOT_EDITOR_EXTRA_CAST = [];
}

function addCastToShotEditor() {
  const select = document.getElementById("shotEditorCast");
  const castId = select.value;
  if (!castId) return;
  
  // Check if already added
  if (window.SHOT_EDITOR_EXTRA_CAST.includes(castId)) return;
  
  window.SHOT_EDITOR_EXTRA_CAST.push(castId);
  
  // Show in UI
  const cast = PROJECT_STATE?.cast?.find(c => c.cast_id === castId);
  const refs = PROJECT_STATE?.cast_matrix?.character_refs?.[castId] || {};
  const thumb = refs.ref_a || refs.ref_b || cast?.reference_images?.[0]?.url || "";
  
  const container = document.getElementById("shotEditorExtraRefs");
  container.innerHTML += `
    <div class="extra-ref-chip" data-cast="${castId}">
      ${thumb ? `<img src="${cacheBust(thumb)}"/>` : ''}
      <span>${cast?.name || castId}</span>
      <button onclick="removeCastFromShotEditor('${castId}')">×</button>
    </div>
  `;
  
  select.value = "";
}

function removeCastFromShotEditor(castId) {
  window.SHOT_EDITOR_EXTRA_CAST = window.SHOT_EDITOR_EXTRA_CAST.filter(c => c !== castId);
  const chip = document.querySelector(`.extra-ref-chip[data-cast="${castId}"]`);
  if (chip) chip.remove();
}

async function submitShotEdit() {
  if (!EDITING_SHOT_ID) return;
  
  const editPrompt = document.getElementById("shotEditPrompt").value.trim();
  const extraCast = window.SHOT_EDITOR_EXTRA_CAST || [];
  
  if (!editPrompt && extraCast.length === 0) {
    showError("Add an edit prompt or extra cast members");
    return;
  }
  
  try {
    setStatus(`Editing ${EDITING_SHOT_ID}…`, null, "storyboardStatus");
    
    const result = await apiCall(`/api/project/${pid()}/shot/${EDITING_SHOT_ID}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        edit_prompt: editPrompt,
        extra_cast: extraCast
      })
    });
    
    closeShotEditor();
    setStatus("Shot edited", 100, "storyboardStatus");
    await refreshFromServer();
  } catch (e) {
    showError(e.message);
  }
}

// v1.6.5: Flag to stop render queue
let RENDER_STOPPED = false;
// v1.6.5: Global negative prompt override
let NEGATIVE_PROMPT_OVERRIDE = "";

async function renderAllShots() {
  try {
    const allShots = PROJECT_STATE?.storyboard?.shots || [];
    const shotsToRender = SELECTED_SEQUENCE_ID
      ? allShots.filter(s => s.sequence_id === SELECTED_SEQUENCE_ID && !s.render?.image_url)
      : allShots.filter(s => !s.render?.image_url);

    if (!shotsToRender.length) {
      setStatus("All shots already rendered", 100, "storyboardStatus");
      return;
    }

    // v1.6.5: Get negative prompt override if provided
    const negPromptInput = document.getElementById("negativePromptInput");
    NEGATIVE_PROMPT_OVERRIDE = negPromptInput?.value?.trim() || "";

    // v1.5.4: Track total for progress
    TOTAL_QUEUED = shotsToRender.length;
    COMPLETED_COUNT = 0;
    RENDER_STOPPED = false;

    // v1.5: Add all shots to queue
    shotsToRender.forEach(sh => {
      const item = {type: "shot", id: sh.shot_id};
      if (!RENDER_QUEUE.some(q => q.type === "shot" && q.id === sh.shot_id)) {
        RENDER_QUEUE.push(item);
      }
    });

    setStatus(`Queued ${shotsToRender.length} shots…`, null, "storyboardStatus");

    // v1.6.5: Use helper to show stop button
    showStopButton();

    renderShots(PROJECT_STATE);  // Update UI to show queue status

    // Start processing
    processRenderQueue();
  } catch (e) {
    showError(e.message);
  }
}

// v1.6.5: Stop the render queue - works for ANY active render
function stopRenderQueue() {
  RENDER_STOPPED = true;
  RENDER_QUEUE.length = 0;  // Clear queue
  setStatus("Rendering stopped", 100, "storyboardStatus");

  // v1.6.5: Use helper to hide stop button
  hideStopButton();

  // Refresh to show current state
  renderShots(PROJECT_STATE);
}

// v1.5.4: Unified queue processor for shots, scenes, and cast refs
let TOTAL_QUEUED = 0;  // Track total for progress
let COMPLETED_COUNT = 0;

async function processRenderQueue() {
  // v1.6.5: Check if stopped
  if (RENDER_STOPPED) {
    return;
  }

  while (RENDER_QUEUE.length > 0 && ACTIVE_RENDERS < MAX_CONCURRENT && !RENDER_STOPPED) {
    const item = RENDER_QUEUE.shift();
    ACTIVE_RENDERS++;

    // Update UI
    updateRenderStatus(item.type, item.id, "rendering");
    const remaining = RENDER_QUEUE.length;
    const done = COMPLETED_COUNT;
    const total = TOTAL_QUEUED;

    // v1.5.4: More detailed status with item identifier
    const displayId = item.id.replace(/seq_(\d+)/, 'sc$1');
    setStatus(`Rendering ${displayId} (${done + ACTIVE_RENDERS}/${total})…`, null, "storyboardStatus");

    // Start render (don't await - let it run in parallel)
    renderItemAsync(item).finally(() => {
      ACTIVE_RENDERS--;
      COMPLETED_COUNT++;
      // Process more from queue if not stopped
      if (!RENDER_STOPPED) {
        processRenderQueue();
      }
    });
  }

  // Check if all done
  if (RENDER_QUEUE.length === 0 && ACTIVE_RENDERS === 0) {
    setStatus(`Rendered ${COMPLETED_COUNT} items`, 100, "storyboardStatus");
    TOTAL_QUEUED = 0;
    COMPLETED_COUNT = 0;
    NEGATIVE_PROMPT_OVERRIDE = "";
    RENDER_STOPPED = false;  // v1.6.5: Reset flag for next batch

    // v1.6.5: Use helper to hide stop button
    hideStopButton();

    await refreshFromServer();
  }
}

// v1.5.3: Async render any item type
async function renderItemAsync(item) {
  try {
    if (item.type === "shot") {
      // v1.6.5: Include negative prompt override if set
      const options = { method: "POST" };
      if (NEGATIVE_PROMPT_OVERRIDE) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ negative_prompt: NEGATIVE_PROMPT_OVERRIDE });
      }
      const result = await apiCall(`/api/project/${pid()}/shot/${item.id}/render`, options);
      // v1.5.3: Update shot card with rendered image
      if (result?.image_url) {
        updateShotCardImage(item.id, result.image_url);
      }
    } else if (item.type === "scene") {
      await apiCall(`/api/project/${pid()}/castmatrix/scene/${item.id}/render`, { method: "POST" });
      // v1.5.3: Refresh state to get new scene image and update timeline
      const state = await apiCall(`/api/project/${pid()}`);
      PROJECT_STATE = state;
      renderTimeline(state);
    } else if (item.type === "cast") {
      // v1.5.8: Skip if already pending elsewhere
      if (PENDING_CAST_REFS.has(item.id)) {
        console.log(`Skipping cast ${item.id} - already pending`);
        updateRenderStatus(item.type, item.id, "done");  // Mark as done since it's being handled
        return;
      }
      PENDING_CAST_REFS.add(item.id);
      try {
        await apiCall(`/api/project/${pid()}/cast/${item.id}/canonical_refs`, { method: "POST" });
        // v1.7.0: Refresh state and update cast card with new refs
        const freshState = await apiCall(`/api/project/${pid()}`);
        PROJECT_STATE = freshState;
        updateCastCardRefs(item.id, freshState);
      } finally {
        PENDING_CAST_REFS.delete(item.id);
      }
    }
    updateRenderStatus(item.type, item.id, "done");
  } catch (e) {
    console.warn(`${item.type} ${item.id} render failed:`, e);
    updateRenderStatus(item.type, item.id, "error");
  }
}

// v1.7.0: Update cast card with new refs without re-rendering entire list
function updateCastCardRefs(castId, state) {
  const card = document.querySelector(`.cast-card[data-cast-id="${castId}"]`);
  if (!card) return;
  
  const charRefs = state?.cast_matrix?.character_refs || {};
  const refs = charRefs[castId] || {};
  
  // Update ref_a thumbnail
  const refAContainer = card.querySelector('.cast-ref-a');
  if (refAContainer && refs.ref_a) {
    refAContainer.innerHTML = `<img src="${cacheBust(refs.ref_a)}"/>`;
  }
  
  // Update ref_b thumbnail
  const refBContainer = card.querySelector('.cast-ref-b');
  if (refBContainer && refs.ref_b) {
    refBContainer.innerHTML = `<img src="${cacheBust(refs.ref_b)}"/>`;
  }
  
  // Hide create button, show ref containers
  const createBtn = card.querySelector('.cast-create-btn');
  if (createBtn) createBtn.classList.add('hidden');
  
  const refsRow = card.querySelector('.cast-refs-row');
  if (refsRow) refsRow.classList.remove('hidden');
  
  console.log(`[updateCastCardRefs] Updated refs for ${castId}: ref_a=${!!refs.ref_a}, ref_b=${!!refs.ref_b}`);
}

// v1.5.3: Update shot card with rendered image
// v1.6.5: Also update PROJECT_STATE to prevent loss on re-render
function updateShotCardImage(shotId, imageUrl) {
  const card = document.querySelector(`.shot-card[data-shot-id="${shotId}"]`);
  if (!card) return;

  const container = card.querySelector('.shot-render-container');
  if (!container) return;

  // v1.6.5: Update PROJECT_STATE so the image persists through re-renders
  const shots = PROJECT_STATE?.storyboard?.shots || [];
  const shot = shots.find(s => s.shot_id === shotId);
  if (shot) {
    shot.render = shot.render || {};
    shot.render.image_url = imageUrl;
    shot.render.status = "done";
  }

  // Also add the edit row if not present
  container.innerHTML = `
    <img class="shot-render-img" src="${cacheBust(imageUrl)}" onclick="showImagePopup('${imageUrl}')"/>
    <button class="rerender-btn" onclick="event.stopPropagation(); renderShot('${shotId}')" title="Re-render">↻</button>
  `;

  // v1.6.6: Add the edit row below the render if not present
  const existingEditRow = card.querySelector('.shot-edit-row');
  if (!existingEditRow) {
    const body = card.querySelector('.shot-card-body');
    if (body) {
      const editRow = document.createElement('div');
      editRow.className = 'shot-edit-row';
      editRow.innerHTML = `
        <input type="text" class="shot-edit-input" placeholder="Edit prompt..." data-shot-id="${shotId}" onkeydown="if(event.key==='Enter'){event.preventDefault();quickEditShot('${shotId}', event.target.value);}"/>
        <button class="shot-ref-btn" onclick="openShotRefPicker('${shotId}')" title="Add reference">+</button>
        <button class="shot-edit-go" onclick="quickEditShot('${shotId}', document.querySelector('.shot-edit-input[data-shot-id=\\'${shotId}\\']').value)" title="Apply edit">→</button>
      `;
      body.appendChild(editRow);
    }
  }
}

// v1.5.3: Update UI status for any render type
function updateRenderStatus(type, id, status) {
  let card;
  if (type === "shot") {
    card = document.querySelector(`.shot-card[data-shot-id="${id}"]`);
  } else if (type === "scene") {
    card = document.querySelector(`.timeline-segment[data-scene-id="${id}"]`);
  } else if (type === "cast") {
    card = document.querySelector(`.cast-card[data-cast-id="${id}"]`);
  }
  
  if (!card) return;
  
  card.classList.remove("in-queue", "rendering", "render-done", "render-error");
  
  if (status === "queue") {
    card.classList.add("in-queue");
  } else if (status === "rendering") {
    card.classList.add("rendering");
  } else if (status === "done") {
    card.classList.add("render-done");
  } else if (status === "error") {
    card.classList.add("render-error");
  }
}

// v1.5.3: Prioritize item - move to front of queue
function prioritizeItem(type, id) {
  const idx = RENDER_QUEUE.findIndex(q => q.type === type && q.id === id);
  if (idx > 0) {
    const item = RENDER_QUEUE.splice(idx, 1)[0];
    RENDER_QUEUE.unshift(item);
    if (type === "shot") renderShots(PROJECT_STATE);
    setStatus(`Prioritized ${type} ${id}`, null);
  }
}

// Legacy wrapper for shot prioritization
function prioritizeShot(shotId) {
  prioritizeItem("shot", shotId);
}

async function refreshFromServer() {
  try {
    // v1.5.8: Clear pending refs tracking on refresh
    PENDING_CAST_REFS.clear();
    
    // v1.4.9.1: Save pending cast input values before refresh
    const pendingCastEdits = {};
    document.querySelectorAll('.cast-card[data-cast-id]').forEach(card => {
      const castId = card.dataset.castId;
      const nameInput = card.querySelector('.cast-name');
      const promptInput = card.querySelector('.cast-prompt');
      if (nameInput || promptInput) {
        pendingCastEdits[castId] = {
          name: nameInput?.value || '',
          prompt: promptInput?.value || ''
        };
      }
    });
    
    PROJECT_STATE = await apiCall(`/api/project/${pid()}`);
    
    // Merge pending edits back into state before rendering
    if (Object.keys(pendingCastEdits).length > 0) {
      const cast = PROJECT_STATE?.cast || [];
      cast.forEach(c => {
        const pending = pendingCastEdits[c.cast_id];
        if (pending) {
          if (pending.name && !c.name) c.name = pending.name;
          if (pending.prompt && !c.prompt_extra) c.prompt_extra = pending.prompt;
        }
      });
    }
    
    renderAudioInfo(PROJECT_STATE);
    renderCastList(PROJECT_STATE);
    renderTimeline(PROJECT_STATE);
    renderScenes(PROJECT_STATE);
    renderShots(PROJECT_STATE);
    renderVideoSection(PROJECT_STATE);  // v1.5.3
    syncProjectSettings(PROJECT_STATE);  // v1.5.3: Sync dropdowns
    updateButtonStates();
    updatePipelineNav(PROJECT_STATE);
    setStatus("Ready", 100);
  } catch (e) {
    console.warn("Refresh failed:", e);
  }
}

// v1.5.3: Sync project settings to UI dropdowns
function syncProjectSettings(state) {
  const project = state?.project;
  if (!project) return;
  
  // Editor (image model) - v1.5.3: Read from render_models.img2img_editor
  const editorMap = {
    "seedream45_edit": "seedream45",
    "nanobanana_edit": "nanobanana",
    "flux2_edit": "flux2",
    // Legacy mappings
    "seedream/v4.5/edit": "seedream45",
    "nano-banana-pro/edit": "nanobanana",
    "flux-2/edit": "flux2"
  };
  const editorDropdown = document.getElementById("imageModel");
  const currentEditor = project.render_models?.img2img_editor || project.editor;
  if (editorDropdown && currentEditor) {
    const val = editorMap[currentEditor] || "nanobanana";
    editorDropdown.value = val;
  }
  
  // LLM
  const llmDropdown = document.getElementById("llm");
  if (llmDropdown && project.llm) {
    llmDropdown.value = project.llm;
  }
  
  // Style preset
  const styleDropdown = document.getElementById("stylePreset");
  if (styleDropdown && project.style_preset) {
    styleDropdown.value = project.style_preset;
  }
  
  // Aspect ratio
  const aspectDropdown = document.getElementById("aspect");
  if (aspectDropdown && project.aspect) {
    aspectDropdown.value = project.aspect;
  }
  
  // Project name
  const nameInput = document.getElementById("projectName");
  if (nameInput && project.name) {
    nameInput.value = project.name;
  }
  
  // v1.5.6: Video model
  const videoModelDropdown = document.getElementById("videoModel");
  if (videoModelDropdown) {
    videoModelDropdown.value = project.video_model || "none";
  }
  
  // v1.5.6: Whisper checkbox
  const whisperCheckbox = document.getElementById("useWhisper");
  if (whisperCheckbox) {
    whisperCheckbox.checked = project.use_whisper || false;
  }
}

// v1.5.3: Update image model when dropdown changes
async function updateImageModel(value) {
  if (!pid()) return;
  
  const modelMap = {
    "nanobanana": {
      image_model: "fal-ai/nano-banana-pro",
      img2img_editor: "nanobanana_edit"
    },
    "seedream45": {
      image_model: "fal-ai/bytedance/seedream/v4.5/text-to-image",
      img2img_editor: "seedream45_edit"
    },
    "flux2": {
      image_model: "fal-ai/flux-2",
      img2img_editor: "flux2_edit"
    }
  };
  
  const models = modelMap[value];
  if (!models) return;
  
  try {
    await apiCall(`/api/project/${pid()}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        render_models: models
      })
    });
    
    // Update local state
    if (PROJECT_STATE?.project) {
      PROJECT_STATE.project.render_models = {
        ...PROJECT_STATE.project.render_models,
        ...models
      };
    }
    
    setStatus(`Switched to ${value}`, 100);
  } catch (e) {
    console.error("Failed to update image model:", e);
  }
}

// v1.5.6: Update Whisper setting
async function updateWhisperSetting(enabled) {
  if (!pid()) return;
  
  try {
    await apiCall(`/api/project/${pid()}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ use_whisper: enabled })
    });
    
    // Update local state
    if (PROJECT_STATE?.project) {
      PROJECT_STATE.project.use_whisper = enabled;
    }
    
    setStatus(enabled ? "Whisper enabled" : "Whisper disabled", 100);
  } catch (e) {
    console.error("Failed to update Whisper setting:", e);
  }
}

// v1.5.3: Check for existing video and show in player
// v1.5.9: Only check if we have rendered shots (avoids 404 spam)
async function renderVideoSection(state) {
  const videoResult = document.getElementById("videoResult");
  if (!videoResult) return;
  
  const projectId = pid();
  if (!projectId) return;
  
  const shots = state?.storyboard?.shots || [];
  const renderedShots = shots.filter(s => s.render?.image_url);
  const total = shots.length;
  
  // Show status based on render progress - avoid 404 checks until all rendered
  if (renderedShots.length === 0) {
    videoResult.innerHTML = `<span class="muted">Render all shots first, then export video with audio.</span>`;
    return;
  } else if (renderedShots.length < total) {
    videoResult.innerHTML = `<span class="muted">${renderedShots.length}/${total} shots rendered. Render all shots to export video.</span>`;
    return;
  }
  
  // All shots rendered - now check if video exists
  const videoUrl = `/renders/${projectId}_video.mp4`;
  
  let videoExists = false;
  try {
    const resp = await fetch(videoUrl, { method: 'HEAD' });
    videoExists = resp.ok;
  } catch (e) {
    videoExists = false;
  }
  
  if (videoExists) {
    const projectName = state?.project?.name || "video";
    const sanitizedName = projectName.replace(/[^a-zA-Z0-9]/g, "_").toLowerCase();
    const filename = `${sanitizedName}_preview.mp4`;
    
    videoResult.innerHTML = `
      <div style="margin-top: 12px;">
        <video controls width="100%" style="max-width: 800px; border-radius: 8px;">
          <source src="${videoUrl}?t=${Date.now()}" type="video/mp4">
        </video>
        <div style="margin-top: 8px;">
          <button class="accent-btn" onclick="downloadVideo('${videoUrl}', '${filename}')">DOWNLOAD VIDEO</button>
          <span class="muted" style="margin-left: 12px;">Previously exported • Re-export to update</span>
        </div>
      </div>
    `;
  } else {
    videoResult.innerHTML = `<span class="muted">All ${total} shots ready! Click Export Preview to create your video.</span>`;
  }
}

function updateShotCard(shotId) {
  const shots = PROJECT_STATE?.storyboard?.shots || [];
  const sh = shots.find(s => s.shot_id === shotId);
  if (!sh) return;
  
  // Find the card in DOM by shot_id
  const cards = document.querySelectorAll('.shot-card');
  for (const card of cards) {
    if (card.querySelector('.shot-card-title span')?.textContent === shotId) {
      const container = card.querySelector('.shot-render-container');
      if (container && sh.render?.image_url) {
        container.innerHTML = `
          <img class="shot-render-img" src="${cacheBust(sh.render.image_url)}" onclick="showImagePopup('${sh.render.image_url}')"/>
          <button class="rerender-btn" onclick="renderShot('${sh.shot_id}')" title="Re-render">↻</button>
        `;
      }
      break;
    }
  }
}

// Pipeline Nav
function updatePipelineNav(state) {
  const steps = document.querySelectorAll(".pipeline-step");
  steps.forEach(s => s.classList.remove("active"));
  
  let active = 1;
  if (state.audio_dna) active = 2;
  if (state.cast?.length) active = 3;
  if (state.storyboard?.sequences?.length || state.cast_matrix?.scenes?.length) active = 4;
  
  // v1.5.3: Enable VIDEO step if shots are rendered
  const renderedShots = (state.storyboard?.shots || []).filter(s => s.render?.image_url);
  if (renderedShots.length > 0) active = 5;
  
  steps.forEach(s => {
    if (parseInt(s.dataset.step) <= active) s.classList.add("active");
  });
}

// v1.5.3: Export video with FFmpeg
async function exportVideo() {
  try {
    if (!pid()) {
      showError("No project loaded");
      return;
    }
    
    // Check if shots are rendered
    const shots = PROJECT_STATE?.storyboard?.shots || [];
    const renderedShots = shots.filter(s => s.render?.image_url);
    
    if (renderedShots.length === 0) {
      showError("No rendered shots. Render shots first.");
      return;
    }
    
    const fadeDuration = document.getElementById("fadeDuration").value;
    const resolution = document.getElementById("videoResolution").value;
    
    setStatus(`Exporting ${renderedShots.length} shots…`, null, "previewStatus");
    document.getElementById("videoResult").innerHTML = `<span class="muted">Encoding video... This may take a few minutes.</span>`;
    
    // v1.6.3: Start polling for status updates
    let pollInterval = setInterval(async () => {
      try {
        const status = await apiCall(`/api/project/${pid()}/export/status`);
        if (status && status.status === "processing" && status.message) {
          document.getElementById("videoResult").innerHTML = `<span class="muted">${status.message}</span>`;
          setStatus(status.message, null, "previewStatus");
        }
      } catch (e) {
        // Ignore polling errors
      }
    }, 1500);
    
    try {
      const result = await apiCall(`/api/project/${pid()}/video/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fade_duration: parseFloat(fadeDuration),
          resolution: resolution,
          fps: 30
        })
      });
      
      // Stop polling
      clearInterval(pollInterval);
      
      if (result.video_url) {
        // v1.5.4: Build proper filename for download
        const projectName = PROJECT_STATE?.project?.name || "video";
        const sanitizedName = projectName.replace(/[^a-zA-Z0-9]/g, "_").toLowerCase();
        const filename = `${sanitizedName}_preview.mp4`;
        
        document.getElementById("videoResult").innerHTML = `
          <div style="margin-top: 12px;">
            <video controls width="100%" style="max-width: 800px; border-radius: 8px;">
              <source src="${result.video_url}?t=${Date.now()}" type="video/mp4">
            </video>
            <div style="margin-top: 8px;">
              <button class="accent-btn" onclick="downloadVideo('${result.video_url}', '${filename}')">DOWNLOAD VIDEO</button>
              <span class="muted" style="margin-left: 12px;">${result.shots_exported} shots, ${result.scene_transitions} scene transitions</span>
            </div>
          </div>
        `;
        setStatus("Exported", 100, "previewStatus");
      } else {
        throw new Error("No video URL returned");
      }
    } catch (e) {
      clearInterval(pollInterval);
      throw e;
    }
  } catch (e) {
    showError(e.message);
    document.getElementById("videoResult").innerHTML = `<span style="color: #ef4444;">Export failed: ${e.message}</span>`;
  }
}

// v1.5.4: Proper video download function
async function downloadVideo(url, filename) {
  try {
    setStatus("Preparing download…", null, "previewStatus");
    const response = await fetch(url);
    const blob = await response.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(blobUrl);
    
    setStatus("Downloaded", 100, "previewStatus");
  } catch (e) {
    showError("Download failed: " + e.message);
  }
}

// Init - show default state
document.addEventListener("DOMContentLoaded", async () => {
  setStatus("Ready", 0);
  renderCastList({ cast: [], cast_matrix: {} });
  
  // v1.6.6: If projectId exists (e.g., page reload), restore full state
  const existingPid = document.getElementById("projectId")?.value?.trim();
  if (existingPid) {
    try {
      await refreshFromServer();
      if (PROJECT_STATE?.audio_dna) {
        parseAudioDNA(PROJECT_STATE.audio_dna);
        updateAudioButtons();
      }
      // syncProjectSettings already called in refreshFromServer, includes use_whisper
    } catch (e) {
      console.warn("Failed to restore project on page load:", e);
    }
  }
});
