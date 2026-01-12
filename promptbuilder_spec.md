# PromptBuilder Spec (BXLSTNRD Video Generator)

## Inputs
- project.style_preset (string)
- project.aspect (square|vertical|horizontal)
- scene.prompt_base (string)
- scene.camera_language (string)
- scene.environment (string)
- scene.symbolic_elements (array)
- scene.energy (0..1)
- cast[] VisualDNA for scene.cast cast_ids

## Output A: Model prompt (string)
A single text prompt concatenating:
1) global style preset tokens
2) aspect/camera lens tokens
3) scene intent + environment + camera_language
4) cast text_tokens (per cast_id)
5) negative tokens (global)
6) safety: "no text, no subtitles, no watermark" unless user toggles subtitles

## Output B: Conditioning payload (model-agnostic object)
{
  "reference_images": [
    { "cast_id": "...", "urls": ["...","..."], "strength": 0.75 }
  ],
  "lora": [
    { "cast_id": "...", "lora_id": "...", "strength": 0.9 }
  ],
  "seed": { "scene_seed": 123, "cast_seeds": { "lead": 456 } }
}

## Style preset example tokens
- "anamorphic cinema": ["anamorphic lens", "cinematic lighting", "shallow depth of field", "film grain", "high dynamic range"]
- "8mm vintage": ["8mm film", "dust and scratches", "soft halation", "vignette"]

## Energy mapping (0..1) -> prompt emphasis
- 0.0–0.3: "quiet, minimal motion, slow camera"
- 0.3–0.7: "steady motion, medium intensity"
- 0.7–1.0: "high intensity, aggressive motion, dramatic lighting"

## Negative prompt (global default)
"low quality, blurry, distorted face, extra limbs, text, watermark, logo, subtitles"
