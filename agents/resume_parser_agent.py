"""
agents/resume_parser_agent.py
─────────────────────────────
Agent 2: Resume Parser

Responsibilities:
  - Extract structured data from raw resume text using LLM
  - Uses few-shot prompting for consistent JSON output
  - Validates extracted data completeness
  - Feeds parsed data to Agent 3 (JD Matcher) and Agent 4 (Behavioral Scorer)
    which run in PARALLEL after this agent completes

Tools used: None (pure LLM extraction)
Orchestration role: Sequential step before parallel fan-out
"""

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from utils.helpers import extract_json_from_llm, load_prompt, utc_now_iso
from utils.tracing import get_logger

logger = get_logger("ResumeParserAgent")


def run_resume_parser(state: dict) -> dict:
    """
    LangGraph node function for resume parsing.

    Args:
        state: ScreeningState with validated candidate_input.

    Returns:
        Updated state with 'parsed_resume' populated.
    """
    logger.info("Parsing resume...")

    candidate_input = state.get("candidate_input", {})
    resume_text = candidate_input.get("resume_text", "")

    # ── Load prompt template ──────────────────────────────────────────────────
    try:
        prompt_template = load_prompt("resume_parser.md")
    except FileNotFoundError:
        logger.warning("Prompt file not found — using default prompt")
        prompt_template = _default_prompt()

    # ── Call LLM ──────────────────────────────────────────────────────────────
    try:
        llm = ChatGroq(
            model=state.get("llm_model", "llama-3.1-8b-instant"),
            temperature=0.0,
        )

        user_message = f"""
Parse the following resume and extract all information.
Return only valid JSON matching the required format.

RESUME:
{resume_text}
"""

        messages = [
            SystemMessage(content=prompt_template),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        parsed = extract_json_from_llm(response.content)

        if parsed is None:
            logger.error("Failed to parse LLM response as JSON")
            parsed = _fallback_parse(resume_text)

    except Exception as e:
        logger.error(f"LLM call failed: {e} — using fallback parser")
        parsed = _fallback_parse(resume_text)

    # ── Validate and clean extracted data ────────────────────────────────────
    parsed = _validate_and_clean(parsed)

    logger.info(
        f"Resume parsed ✔ — "
        f"Skills: {len(parsed.get('skills', []))}, "
        f"Experience: {parsed.get('total_experience_years', 0)} years"
    )

    return {
        **state,
        "parsed_resume": parsed,
        "current_node": "resume_parser",
    }


def _validate_and_clean(parsed: dict) -> dict:
    """Ensure all required fields exist with sensible defaults."""
    defaults = {
        "name": "Unknown",
        "email": "",
        "phone": "",
        "location": "",
        "summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "total_experience_years": 0.0,
    }
    for key, default in defaults.items():
        if key not in parsed or parsed[key] is None:
            parsed[key] = default

    # Ensure total_experience_years is a float
    try:
        parsed["total_experience_years"] = float(parsed["total_experience_years"])
    except (ValueError, TypeError):
        parsed["total_experience_years"] = 0.0

    # Ensure skills is a list of strings
    if not isinstance(parsed["skills"], list):
        parsed["skills"] = []

    return parsed


def _fallback_parse(resume_text: str) -> dict:
    """
    Simple keyword-based fallback if LLM fails.
    Extracts skills from common technology keywords.
    """
    import re
    common_skills = [
        "Python", "Java", "JavaScript", "SQL", "R", "Scala",
        "Docker", "Kubernetes", "AWS", "GCP", "Azure",
        "TensorFlow", "PyTorch", "Spark", "Hadoop",
        "Django", "FastAPI", "Spring", "React", "Node.js",
        "PostgreSQL", "MySQL", "MongoDB", "Redis",
        "Git", "CI/CD", "Terraform", "Linux",
    ]
    found_skills = [s for s in common_skills if s.lower() in resume_text.lower()]

    return {
        "name": "Unknown",
        "email": "",
        "phone": "",
        "location": "",
        "summary": resume_text[:200],
        "skills": found_skills,
        "experience": [],
        "education": [],
        "certifications": [],
        "total_experience_years": 0.0,
    }


def _default_prompt() -> str:
    """Fallback prompt if .md file is not found."""
    return """You are an expert resume parser.
Extract structured information from the resume and return ONLY valid JSON with these fields:
name, email, phone, location, summary, skills (list), experience (list of objects with title/company/duration_years/description),
education (list of objects with degree/institution/year), certifications (list), total_experience_years (float).
No extra text, just JSON."""
