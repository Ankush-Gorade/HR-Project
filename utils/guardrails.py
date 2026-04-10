"""
utils/guardrails.py
───────────────────
All input and output guardrail functions used across agents.
"""

import re
from config import cfg


# ─── Input Guardrails ─────────────────────────────────────────────────────────

def check_length(text, min_chars, max_chars, field_name):
    """Validate text length is within acceptable bounds."""
    errors = []
    length = len(text.strip())
    if length < min_chars:
        errors.append(f"{field_name} too short ({length} chars). Min: {min_chars}")
    if length > max_chars:
        errors.append(f"{field_name} too long ({length} chars). Max: {max_chars}")
    return errors


def detect_prompt_injection(text):
    """Scan text for known prompt injection patterns."""
    text_lower = text.lower()
    return [p for p in cfg.guardrails.injection_patterns if p.lower() in text_lower]


def validate_required_fields(data, required_keys):
    """Check all required keys exist and are non-empty."""
    errors = []
    for key in required_keys:
        value = data.get(key, "")
        if not value or (isinstance(value, str) and not value.strip()):
            errors.append(f"Required field '{key}' is missing or empty.")
    return errors


def validate_candidate_input(candidate_input):
    """
    Run all input guardrails on the raw candidate input dict.
    Returns (is_valid: bool, errors: list[str])
    """
    errors = []
    g = cfg.guardrails

    # Required fields check
    errors += validate_required_fields(
        candidate_input,
        required_keys=["resume_text", "job_description", "job_title"]
    )

    # Resume length check
    resume = candidate_input.get("resume_text", "")
    errors += check_length(
        resume,
        g.min_resume_length_chars,
        g.max_resume_length_chars,
        "Resume"
    )

    # JD length check
    jd = candidate_input.get("job_description", "")
    errors += check_length(jd, 50, g.max_jd_length_chars, "Job Description")

    # Prompt injection scan
    for field, value in [("resume_text", resume), ("job_description", jd)]:
        injections = detect_prompt_injection(value)
        if injections:
            errors.append(
                f"Prompt injection detected in '{field}': {injections}"
            )

    return len(errors) == 0, errors


# ─── Output Guardrails ────────────────────────────────────────────────────────

# PII regex patterns
_PII_PATTERNS = {
    "email": re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.I
    ),
    "phone": re.compile(
        r"(\+?\d{1,3}[\s\-.]?)?(\(?\d{2,4}\)?[\s\-.]?)(\d{3,4}[\s\-.]?\d{3,4})",
        re.X
    ),
    "ssn": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
}


def redact_pii(text, replacement="[REDACTED]"):
    """Replace PII patterns in text with a placeholder."""
    for label, pattern in _PII_PATTERNS.items():
        text = pattern.sub(replacement, text)
    return text


def redact_pii_from_dict(data, fields_to_redact=None):
    """Redact PII from specific string fields in a nested dict."""
    target_fields = fields_to_redact or cfg.guardrails.pii_fields_to_redact
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = redact_pii_from_dict(value, target_fields)
        elif isinstance(value, str) and key in target_fields:
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


def validate_output_schema(report, required_keys):
    """
    Ensure the screening report contains all required keys.
    Returns (is_valid: bool, errors: list[str])
    """
    errors = validate_required_fields(report, required_keys)
    return len(errors) == 0, errors


def check_score_bounds(report):
    """
    Validate all *_score fields fall within [0, 100].
    Returns list of error messages for out-of-range values.
    """
    errors = []
    for key, value in report.items():
        if key.endswith("_score") and isinstance(value, (int, float)):
            if not (0 <= value <= 100):
                errors.append(
                    f"Score out of bounds: '{key}' = {value}. Expected [0, 100]."
                )
    return errors


def detect_bias_flags(report_text):
    """
    Lightweight scan for potentially biased language in reports.
    Returns list of flagged phrases found.
    """
    bias_patterns = [
        r"\b(too old|too young|young blood|mature candidate)\b",
        r"\b(he |she |his |her )\b",
        r"\b(foreign|native|local|immigrant)\b",
        r"\b(christian|muslim|hindu|jewish|atheist)\b",
        r"\b(married|single|divorced|children|family)\b",
    ]
    flags = []
    text_lower = report_text.lower()
    for pattern in bias_patterns:
        matches = re.findall(pattern, text_lower)
        if matches:
            flags.extend([m.strip() for m in matches])
    return list(set(flags))
