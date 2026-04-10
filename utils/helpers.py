import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from config import cfg

def load_prompt(prompt_filename: str) -> str:
    prompt_path = Path(cfg.prompts_dir) / prompt_filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")

def normalise_score(score: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    return round(max(min_val, min(max_val, score)), 2)

def weighted_average(scores: dict, weights: dict) -> float:
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(scores.get(k, 0) * w for k, w in weights.items())
    return normalise_score(weighted_sum / total_weight)

def score_to_recommendation(score: float) -> str:
    s = cfg.scoring
    if score >= s.strong_hire_threshold:
        return "Strong Hire"
    elif score >= s.interview_threshold:
        return "Hire"
    elif score >= s.auto_reject_threshold:
        return "Hold"
    else:
        return "Reject"

def extract_json_from_llm(text: str) -> Optional[dict]:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass
    return None

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def generate_trace_id() -> str:
    return str(uuid.uuid4())[:8]
