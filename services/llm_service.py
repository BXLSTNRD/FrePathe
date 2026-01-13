"""
LLM Service - v1.6.9
Handles all LLM API calls (Claude, OpenAI) with cascade fallback.
"""

import json
import time
import requests
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import HTTPException

from .config import (
    CLAUDE_KEY, OPENAI_KEY, UPLOADS_DIR,
    require_key, track_cost
)


# ========= JSON Extraction/Repair =========

def extract_json_object(text: str) -> str:
    """Extract first valid JSON object from text."""
    if not text:
        return ""
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    start = s.find("{")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    return ""


# ========= OpenAI API =========

def call_openai_json(
    system: str, 
    user: str, 
    model: str = "gpt-4o-mini", 
    temperature: float = 0.0
) -> Dict[str, Any]:
    """Call OpenAI API and return parsed JSON response."""
    require_key("OPENAI_KEY", OPENAI_KEY)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    if r.status_code >= 300:
        raise HTTPException(502, f"OpenAI failed: {r.status_code} {r.text}")
    txt = r.json()["choices"][0]["message"]["content"]
    return json.loads(txt)


# ========= Claude API =========

def call_claude_json(
    system: str, 
    user: str, 
    model: str = "claude-sonnet-4-5-20250929", 
    max_tokens: int = 5000
) -> Dict[str, Any]:
    """Call Claude API and return parsed JSON response."""
    require_key("CLAUDE_KEY", CLAUDE_KEY)
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": CLAUDE_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": model,
        "max_tokens": int(max_tokens),
        "temperature": 0.7,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=240)
    if r.status_code >= 300:
        raise HTTPException(502, f"Claude failed: {r.status_code} {r.text}")
    
    data = r.json()
    blocks = data.get("content", [])
    txt = "".join([b.get("text", "") for b in blocks if b.get("type") == "text"]).strip()
    
    # Debug: save raw response
    try:
        (UPLOADS_DIR / f"claude_last_raw_{int(time.time())}.txt").write_text(
            txt or "<EMPTY>", encoding="utf-8"
        )
    except Exception:
        pass
    
    # Try to extract JSON
    js_txt = extract_json_object(txt)
    if js_txt:
        try:
            return json.loads(js_txt)
        except Exception:
            pass
    
    # Fallback: use OpenAI to repair JSON
    if OPENAI_KEY and txt:
        return call_openai_json(
            "You are a strict JSON repair tool. Output ONLY a single valid JSON object.",
            txt
        )
    
    raise HTTPException(502, "Claude returned no JSON. Check data/uploads/claude_last_raw_*.txt")


# ========= Model Cascade =========

# v1.6.1: Claude model cascade (most capable → fastest)
CLAUDE_MODEL_CASCADE = [
    "claude-sonnet-4-5-20250929",      # Primary - latest Sonnet 4.5
    "claude-3-5-sonnet-latest",        # Latest stable
    "claude-3-5-sonnet-20241022",      # Older specific
    "claude-3-haiku-20240307",         # Fast fallback
]


def call_llm_json(
    system: str, 
    user: str, 
    preferred: str = "claude", 
    max_tokens: int = 5000, 
    state: Dict = None
) -> Dict[str, Any]:
    """
    v1.6.1: Call LLM with Claude cascade fallback.
    OpenAI only as last resort. Tracks cost automatically.
    """
    require_key("CLAUDE_KEY", CLAUDE_KEY)
    last_error = None
    
    # Try Claude cascade first
    for model in CLAUDE_MODEL_CASCADE:
        try:
            print(f"[INFO] Calling Claude API with {model}...")
            result = call_claude_json(system, user, model=model, max_tokens=max_tokens)
            # Track cost for successful call
            track_cost(model, 1, state=state)
            return result
        except HTTPException as e:
            last_error = e
            print(f"[WARN] {model} failed ({e.status_code}): {str(e.detail)[:100]}")
            if e.status_code == 400:
                # Bad request - don't retry with different model
                break
        except Exception as e:
            last_error = HTTPException(502, str(e))
            print(f"[WARN] {model} failed: {str(e)[:100]}")
    
    # OpenAI as absolute last resort
    if OPENAI_KEY:
        try:
            print(f"[INFO] All Claude models failed, trying OpenAI as last resort...")
            result = call_openai_json(system, user)
            track_cost("gpt-4o-mini", 1, state=state)
            return result
        except Exception as e:
            print(f"[ERROR] OpenAI also failed: {str(e)[:100]}")
    
    raise last_error or HTTPException(502, "All LLM providers failed")


# ========= Prompt Loading =========

def load_prompt(name: str, base_path: Path = None) -> str:
    """Load a prompt template from Prompts/ directory."""
    if base_path is None:
        base_path = Path(__file__).parent.parent / "Prompts"
    
    prompt_file = base_path / f"{name}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    
    raise FileNotFoundError(f"Prompt not found: {name}")


def save_llm_debug(
    endpoint: str, 
    system: str, 
    user: str, 
    response: Any, 
    project_id: str = "unknown"
) -> None:
    """Save LLM call for debugging."""
    from .config import DEBUG_DIR
    try:
        ts = int(time.time())
        log_file = DEBUG_DIR / f"{project_id}_llm_{ts}.json"
        log_file.write_text(json.dumps({
            "timestamp": ts,
            "endpoint": endpoint,
            "system_prompt": system,
            "user_prompt": user,
            "response": response,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to log LLM call: {e}")
