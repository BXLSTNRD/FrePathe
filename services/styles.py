"""
Style Presets - v1.6.9
All visual style definitions for FrePathe.
"""

from typing import Dict, Any, List


# ========= Style Presets (45+) =========
STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    # === Original Styles ===
    "anamorphic_cinema": {
        "label": "Anamorphic Cinema",
        "tokens": ["anamorphic lens", "cinematic lighting", "shallow depth of field", "film grain", "high dynamic range"],
        "script_notes": "Modern cinematic coverage with motivated camera and emotional blocking.",
    },
    "8mm_vintage": {
        "label": "8mm Vintage",
        "tokens": ["8mm film", "dust and scratches", "soft halation", "vignette", "handheld drift"],
        "script_notes": "Nostalgic memory texture. Lean on match-cuts and time-jumps.",
    },
    "noir_monochrome": {
        "label": "Noir Monochrome",
        "tokens": ["black and white", "film noir lighting", "high contrast", "smoke haze", "hard shadows"],
        "script_notes": "Noir grammar: silhouettes, blinds, reflections, rain, moral tension.",
    },
    "neon_noir": {
        "label": "Neon Noir",
        "tokens": ["neon reflections", "wet asphalt", "cyan-magenta glow", "urban night", "hard contrast"],
        "script_notes": "City pulse, reflective surfaces, forward motion.",
    },
    "documentary_handheld": {
        "label": "Documentary Handheld",
        "tokens": ["handheld camera", "natural light", "documentary realism", "imperfect framing", "authentic moment"],
        "script_notes": "Observational shots, organic camera reactivity.",
    },
    "dreamlike_softfocus": {
        "label": "Dreamlike Softfocus",
        "tokens": ["soft focus", "bloom", "hazy atmosphere", "gentle lens flare", "slow motion feel"],
        "script_notes": "Elliptical transitions, symbolism over plot.",
    },
    "gritty_urban": {
        "label": "Gritty Urban",
        "tokens": ["gritty texture", "streetlight sodium glow", "high ISO grain", "raw realism", "urban decay"],
        "script_notes": "Hard cuts, kinetic beats, street-level tension.",
    },
    "period_70s": {
        "label": "Period 70s",
        "tokens": ["1970s film", "warm tones", "zoom lens", "film grain", "practical lighting"],
        "script_notes": "Zoom language, longer takes, character staging.",
    },
    "period_90s_indie": {
        "label": "90s Indie",
        "tokens": ["1990s indie film", "muted palette", "handheld intimacy", "natural window light"],
        "script_notes": "Lo-fi sincerity, intimate coverage.",
    },
    "hyperreal_clean": {
        "label": "Hyperreal Clean",
        "tokens": ["ultra clean", "sharp detail", "stable camera", "modern commercial lighting", "minimal grain"],
        "script_notes": "Precise compositions, premium polish.",
    },
    "surreal_symbolism": {
        "label": "Surreal Symbolism",
        "tokens": ["surreal", "symbolic props", "unexpected scale", "dream logic", "metaphoric staging"],
        "script_notes": "Metaphor-first transitions.",
    },
    "one_take_energy": {
        "label": "One-Take Energy",
        "tokens": ["long take feel", "continuous camera", "blocking choreography", "fluid movement"],
        "script_notes": "Each segment as a coherent mini-arc.",
    },
    "stop_motion_look": {
        "label": "Stop‑Motion Look",
        "tokens": ["stop motion aesthetic", "tactile texture", "miniature set feel", "slight frame jitter"],
        "script_notes": "Tangible props; playful but precise continuity.",
    },
    "anime_cinematic": {
        "label": "Anime Cinematic",
        "tokens": ["anime cinematic framing", "dramatic angles", "stylized lighting", "dynamic motion"],
        "script_notes": "Bold compositions, emotional punch-ins.",
    },
    "western_dust": {
        "label": "Western Dust",
        "tokens": ["western", "dusty air", "backlit sun", "wide landscapes", "gritty close-ups"],
        "script_notes": "Wide establishing + intense close-ups.",
    },
    "horror_suspense": {
        "label": "Horror Suspense",
        "tokens": ["low key lighting", "negative space", "uneasy framing", "fog", "subtle dread"],
        "script_notes": "Unease via pacing and framing; payoff on peaks.",
    },
    "romcom_bright": {
        "label": "Romcom Bright",
        "tokens": ["bright soft light", "warm highlights", "playful composition", "colorful props", "gentle contrast"],
        "script_notes": "Readable emotions, charming beats.",
    },
    "music_doc_backstage": {
        "label": "Music Doc / Backstage",
        "tokens": ["backstage", "available light", "close handheld", "authentic gear", "crowd energy"],
        "script_notes": "Candid moments + inserts; quick coverage.",
    },
    "sci_fi_retro": {
        "label": "Retro Sci‑Fi",
        "tokens": ["retro sci-fi", "chrome", "analog controls", "practical neon", "fogged glass"],
        "script_notes": "World-building via set detail; beats as system states.",
    },
    "art_nouveau_poetic": {
        "label": "Art Nouveau Poetic",
        "tokens": ["art nouveau curves", "ornate ironwork", "stained glass glow", "poetic framing", "elegant motifs"],
        "script_notes": "Repeating motifs; transitions echo rhythms.",
    },
    "minimalist_monochrome": {
        "label": "Minimalist Monochrome",
        "tokens": ["minimalism", "monochrome", "negative space", "clean lines", "quiet composition"],
        "script_notes": "Sparse storytelling; musically motivated cuts.",
    },
    
    # === v1.5.7: Pop Culture & Director Styles ===
    "vaporwave_aesthetic": {
        "label": "Vaporwave Aesthetic",
        "tokens": ["vaporwave", "pink purple gradients", "greek statues", "retro tech", "glitch effects", "palm trees"],
        "script_notes": "Nostalgic irony, consumer culture visuals.",
    },
    "cyberpunk_2077": {
        "label": "Cyberpunk 2077",
        "tokens": ["cyberpunk", "holographic ads", "rain-slicked streets", "neon kanji", "chrome implants", "dark future"],
        "script_notes": "Tech noir, body modification themes.",
    },
    "studio_ghibli": {
        "label": "Studio Ghibli",
        "tokens": ["studio ghibli style", "hand painted backgrounds", "soft watercolor", "whimsical nature", "magical realism"],
        "script_notes": "Environmental storytelling, wonder.",
    },
    "wes_anderson": {
        "label": "Wes Anderson",
        "tokens": ["symmetrical framing", "pastel palette", "vintage props", "whimsical staging", "centered composition"],
        "script_notes": "Deadpan humor, meticulous mise-en-scène.",
    },
    "tarantino_grindhouse": {
        "label": "Tarantino Grindhouse",
        "tokens": ["grindhouse", "film damage", "exploitation aesthetic", "bold typography", "retro violence"],
        "script_notes": "Pulpy dialogue, chapter structure.",
    },
    "blade_runner": {
        "label": "Blade Runner",
        "tokens": ["blade runner", "rain", "neon advertisements", "industrial fog", "noir future", "flying vehicles"],
        "script_notes": "Existential themes, rain-soaked melancholy.",
    },
    "wong_kar_wai": {
        "label": "Wong Kar-Wai",
        "tokens": ["step printing", "smeared motion", "saturated colors", "loneliness", "neon reflections", "romantic melancholy"],
        "script_notes": "Time manipulation, unrequited love.",
    },
    "lynch_surreal": {
        "label": "David Lynch Surreal",
        "tokens": ["surreal", "red curtains", "industrial hum", "uncanny valley", "dream nightmare", "slow dread"],
        "script_notes": "Subconscious imagery, unsettling ordinary.",
    },
    "kubrick_symmetry": {
        "label": "Kubrick Symmetry",
        "tokens": ["one point perspective", "symmetrical", "cold precision", "clinical lighting", "unsettling stillness"],
        "script_notes": "Geometric perfection, human fragility.",
    },
    "instagram_lifestyle": {
        "label": "Instagram Lifestyle",
        "tokens": ["lifestyle photography", "golden hour", "soft bokeh", "aspirational", "clean minimal", "influencer aesthetic"],
        "script_notes": "Aspirational beauty, product integration.",
    },
    "90s_mtv": {
        "label": "90s MTV",
        "tokens": ["90s mtv", "quick cuts", "dutch angles", "fish eye lens", "grunge aesthetic", "video effects"],
        "script_notes": "Energetic editing, youth rebellion.",
    },
    "polaroid_nostalgia": {
        "label": "Polaroid Nostalgia",
        "tokens": ["polaroid", "instant film", "light leaks", "vintage colors", "snapshot aesthetic", "authentic moments"],
        "script_notes": "Intimate memories, imperfect beauty.",
    },
    "fashion_editorial": {
        "label": "Fashion Editorial",
        "tokens": ["high fashion", "editorial lighting", "stark backgrounds", "dramatic poses", "vogue aesthetic", "model photography"],
        "script_notes": "Striking poses, visual impact.",
    },
    "music_video_glam": {
        "label": "Music Video Glam",
        "tokens": ["music video", "lens flares", "smoke machines", "dramatic lighting", "performance shots", "glamorous"],
        "script_notes": "Star power, visual spectacle.",
    },
    "pixel_art_retro": {
        "label": "Pixel Art Retro",
        "tokens": ["pixel art", "8-bit aesthetic", "retro gaming", "limited palette", "chunky pixels", "nostalgic"],
        "script_notes": "Gaming nostalgia, simplified forms.",
    },
    "comic_book_pop": {
        "label": "Comic Book Pop",
        "tokens": ["comic book style", "bold outlines", "halftone dots", "speech bubbles", "pop art colors", "dynamic panels"],
        "script_notes": "Sequential energy, graphic impact.",
    },
    "renaissance_painting": {
        "label": "Renaissance Painting",
        "tokens": ["renaissance", "chiaroscuro", "oil painting", "classical composition", "religious light", "old masters"],
        "script_notes": "Timeless beauty, dramatic lighting.",
    },
    "soviet_propaganda": {
        "label": "Soviet Constructivism",
        "tokens": ["constructivism", "red and black", "bold geometry", "propaganda poster", "worker imagery", "revolutionary"],
        "script_notes": "Bold graphics, ideological power.",
    },
    "japanese_woodblock": {
        "label": "Japanese Woodblock",
        "tokens": ["ukiyo-e", "woodblock print", "flat perspective", "nature scenes", "edo period", "stylized waves"],
        "script_notes": "Elegant simplicity, natural beauty.",
    },
    "miami_vice": {
        "label": "Miami Vice",
        "tokens": ["miami vice", "pastel suits", "sunset colors", "palm trees", "speedboats", "80s glamour", "tropical noir"],
        "script_notes": "Sun-soaked crime, style over substance.",
    },
    
    # === v1.5.7: Noir Variants & Art Styles ===
    "noir_classic": {
        "label": "Noir Classic",
        "tokens": ["1940s film noir", "fedora hats", "trench coats", "venetian blinds", "cigarette smoke", "rain-slicked streets", "black and white", "hard boiled detective"],
        "script_notes": "Classic detective genre, moral ambiguity, femme fatale.",
    },
    "noir_neo": {
        "label": "Neo Noir",
        "tokens": ["neo noir", "modern noir", "neon and shadow", "urban nightscape", "contemporary crime", "stylized violence", "no hats", "no trenchcoats", "sleek modern"],
        "script_notes": "Modern crime drama aesthetics, stylish but grounded.",
    },
    "glitch_art": {
        "label": "Glitch Art",
        "tokens": ["glitch art", "data corruption", "pixel sorting", "RGB split", "digital artifacts", "scan lines", "VHS damage", "broken signal"],
        "script_notes": "Digital decay, technological anxiety, broken beauty.",
    },
    "lo_fi_bedroom": {
        "label": "Lo-Fi Bedroom",
        "tokens": ["lo-fi aesthetic", "warm lamp light", "cozy bedroom", "soft textures", "vintage electronics", "plants", "warm grain", "intimate space"],
        "script_notes": "Intimate, comfortable, nostalgic warmth.",
    },
    "brutalist_concrete": {
        "label": "Brutalist Concrete",
        "tokens": ["brutalist architecture", "raw concrete", "geometric shadows", "monumental scale", "cold modernism", "stark angles", "urban fortress"],
        "script_notes": "Imposing structures, human vs architecture tension.",
    },
    "acid_trip": {
        "label": "Acid Trip",
        "tokens": ["psychedelic", "kaleidoscopic patterns", "color distortion", "melting reality", "fractal geometry", "saturated hues", "visual hallucination"],
        "script_notes": "Reality bending, sensory overload, altered states.",
    },
    "french_new_wave": {
        "label": "French New Wave",
        "tokens": ["nouvelle vague", "jump cuts", "natural light", "parisian streets", "handheld camera", "intellectual cool", "cigarette aesthetic", "black and white option"],
        "script_notes": "Rule-breaking editing, philosophical undertones, effortless style.",
    },
    "afrofuturism": {
        "label": "Afrofuturism",
        "tokens": ["afrofuturism", "african patterns", "futuristic technology", "cosmic imagery", "gold accents", "ancestral future", "wakanda aesthetic"],
        "script_notes": "Heritage meets tomorrow, empowered futures, cultural pride.",
    },
    "silent_film_era": {
        "label": "Silent Film Era",
        "tokens": ["silent film", "sepia tone", "iris shots", "intertitles", "theatrical acting", "vintage vignette", "1920s aesthetic", "expressionist shadows"],
        "script_notes": "Exaggerated emotion, visual storytelling, nostalgic charm.",
    },
    
    # === v1.5.9.1: Puppet & Animation Styles ===
    "muppet_show": {
        "label": "Muppet Show",
        "tokens": ["jim henson muppets", "felt puppet", "googly eyes", "fabric texture", "theatrical stage", "warm lighting", "expressive puppet faces", "handcrafted aesthetic"],
        "script_notes": "Warm comedy, vaudeville energy, breaking fourth wall.",
    },
    "claymation": {
        "label": "Claymation",
        "tokens": ["claymation", "stop motion clay", "plasticine texture", "aardman style", "fingerprint details", "smooth animation", "tactile characters", "handmade charm"],
        "script_notes": "Tactile humor, physical comedy, Wallace and Gromit vibes.",
    },
    "thunderbirds": {
        "label": "Thunderbirds",
        "tokens": ["supermarionation", "1960s puppet", "marionette strings visible", "retro futurism", "practical miniatures", "wooden movement", "tracy island aesthetic"],
        "script_notes": "Retro sci-fi heroics, dramatic rescues, stiff-upper-lip.",
    },
    "spitting_image": {
        "label": "Spitting Image",
        "tokens": ["latex puppet", "caricature", "satirical puppet", "grotesque features", "exaggerated expressions", "political satire", "rubber mask aesthetic"],
        "script_notes": "Sharp satire, exaggerated features, biting commentary.",
    },
    "team_america": {
        "label": "Team America",
        "tokens": ["team america puppets", "action movie parody", "marionette action", "miniature explosions", "puppet violence", "satirical patriotism", "string puppets"],
        "script_notes": "Action parody, irreverent humor, puppet chaos.",
    },
}


# ========= Helper Functions =========

def _find_style(key_or_label: str) -> Dict[str, Any]:
    """
    v1.7.0: Find style by key OR label.
    UI sends labels like "Anamorphic Cinema" but keys are "anamorphic_cinema".
    """
    # Direct key match
    if key_or_label in STYLE_PRESETS:
        return STYLE_PRESETS[key_or_label]
    
    # Try to match by label
    for k, v in STYLE_PRESETS.items():
        if v.get("label", "").lower() == key_or_label.lower():
            return v
    
    # Fallback: return default with key as single token
    return {"tokens": [key_or_label], "label": key_or_label, "script_notes": ""}


def style_tokens(key: str) -> List[str]:
    """Get prompt tokens for a style preset."""
    return _find_style(key).get("tokens", [key])


def style_script_notes(key: str) -> str:
    """Get script notes for a style preset."""
    return _find_style(key).get("script_notes", "")


def get_style_label(key: str) -> str:
    """Get human-readable label for a style."""
    return _find_style(key).get("label", key)


def list_styles() -> List[Dict[str, str]]:
    """List all available styles with key and label."""
    return [
        {"key": k, "label": v["label"]}
        for k, v in STYLE_PRESETS.items()
    ]


def get_style_options_html() -> str:
    """Generate HTML <option> tags for style dropdown."""
    return "\n".join([
        f'<option value="{k}">{v["label"]}</option>'
        for k, v in STYLE_PRESETS.items()
    ])
