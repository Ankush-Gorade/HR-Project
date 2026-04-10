"""
agents/behavioral_scorer_agent.py
──────────────────────────────────
Agent 4: Behavioral Scorer

Responsibilities:
  - Analyze soft skills, leadership, and culture fit from resume
  - Detect red flags (job hopping, gaps, vague descriptions)
  - Identify positive signals (promotions, impact metrics, mentoring)
  - Score behavioral dimensions: communication, leadership,
    teamwork, problem solving, culture fit

Tools used: None (pure LLM analysis)
Orchestration role: Parallel fan-out node (runs concurrently with Agent 3)
"""

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from utils.helpers import extract_json_from_llm, load_prompt, normalise_score
from utils.tracing import get_logger

logger = get_logger("BehavioralScorerAgent")


def run_behavioral_scorer(state: dict) -> dict:
    """
    LangGraph node function for behavioral scoring.

    Args:
        state: ScreeningState with parsed_resume populated.

    Returns:
        Updated state with 'behavioral_score' populated.
    """
    logger.info("Running behavioral scoring...")

    parsed_resume = state.get("parsed_resume", {})
    candidate_input = state.get("candidate_input", {})
    resume_text = candidate_input.get("resume_text", "")
    job_title = candidate_input.get("job_title", "")

    # ── Load prompt ───────────────────────────────────────────────────────────
    try:
        prompt_template = load_prompt("behavioral_scorer.md")
    except FileNotFoundError:
        prompt_template = _default_prompt()

    # ── Call LLM ─────────────────────────────────────────────────────────────
    try:
        llm = ChatOllama(
            model=state.get("llm_model", "llama3.2"),
            base_url="https://abc123.ngrok-free.app",
            temperature=0.0,
        )

        experience_summary = _summarise_experience(parsed_resume)

        user_message = f"""
Evaluate the behavioral profile of this candidate applying for: {job_title}

RESUME TEXT:
{resume_text[:3000]}

PARSED EXPERIENCE SUMMARY:
{experience_summary}

Analyze soft skills, leadership, red flags, and positive signals.
Return only valid JSON as specified.
"""

        messages = [
            SystemMessage(content=prompt_template),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        result = extract_json_from_llm(response.content)

        if result is None:
            logger.error("Failed to parse behavioral score JSON — using fallback")
            result = _fallback_score(parsed_resume)

    except Exception as e:
        logger.error(f"LLM call failed: {e} — using fallback scoring")
        result = _fallback_score(parsed_resume)

    # ── Validate all scores are in range ─────────────────────────────────────
    score_fields = [
        "communication_score", "leadership_score", "teamwork_score",
        "problem_solving_score", "culture_fit_score", "behavioral_overall_score"
    ]
    for field in score_fields:
        if field in result:
            result[field] = normalise_score(float(result[field]))

    # ── Ensure required fields exist ─────────────────────────────────────────
    result.setdefault("red_flags", [])
    result.setdefault("positive_signals", [])
    result.setdefault("behavioral_summary", "")

    logger.info(
        f"Behavioral scoring complete ✔ — "
        f"Overall: {result.get('behavioral_overall_score', 0)}, "
        f"Red flags: {len(result.get('red_flags', []))}"
    )

    return {
        **state,
        "behavioral_score": result,
        "current_node": "behavioral_scorer",
    }


def _summarise_experience(parsed_resume: dict) -> str:
    """
    Build a concise experience summary string for the LLM prompt.
    """
    lines = []
    experience = parsed_resume.get("experience", [])
    for exp in experience:
        lines.append(
            f"- {exp.get('title','?')} at {exp.get('company','?')} "
            f"({exp.get('duration_years', 0)} years): {exp.get('description','')}"
        )
    total = parsed_resume.get("total_experience_years", 0)
    avg_tenure = total / max(len(experience), 1)
    lines.append(f"\nTotal experience: {total} years")
    lines.append(f"Average tenure per role: {avg_tenure:.1f} years")
    lines.append(f"Number of roles: {len(experience)}")
    return "\n".join(lines)


def _fallback_score(parsed_resume: dict) -> dict:
    """
    Rule-based fallback scoring when LLM is unavailable.
    Uses heuristics: tenure length, number of roles, certifications.
    """
    experience = parsed_resume.get("experience", [])
    total_years = parsed_resume.get("total_experience_years", 0)
    num_roles = len(experience)
    certifications = parsed_resume.get("certifications", [])

    # Red flag: job hopping (avg tenure < 1 year)
    avg_tenure = total_years / max(num_roles, 1)
    red_flags = []
    positive_signals = []

    if avg_tenure < 1.0 and num_roles > 2:
        red_flags.append(f"Frequent job changes: avg tenure {avg_tenure:.1f} years")

    if certifications:
        positive_signals.append(f"Holds {len(certifications)} certification(s)")

    if total_years >= 5:
        positive_signals.append(f"Solid experience: {total_years} years")

    base_score = min(50 + (total_years * 5), 85)
    if red_flags:
        base_score -= 15

    return {
        "communication_score": base_score,
        "leadership_score": base_score - 10,
        "teamwork_score": base_score,
        "problem_solving_score": base_score,
        "culture_fit_score": base_score - 5,
        "red_flags": red_flags,
        "positive_signals": positive_signals,
        "behavioral_overall_score": normalise_score(base_score),
        "behavioral_summary": f"Fallback score based on {total_years} years experience",
    }


def _default_prompt() -> str:
    return """You are an expert HR behavioral analyst.
Evaluate the candidate's soft skills, leadership, teamwork, problem solving,
and culture fit from their resume. Detect red flags and positive signals.
Return ONLY valid JSON with: communication_score, leadership_score,
teamwork_score, problem_solving_score, culture_fit_score, red_flags (list),
positive_signals (list), behavioral_overall_score, behavioral_summary."""
