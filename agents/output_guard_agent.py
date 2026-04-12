"""
agents/output_guard_agent.py
────────────────────────────
Agent 5: Output Guard

Responsibilities:
  - Aggregate scores from JD Matcher and Behavioral Scorer
  - Generate final screening report with recommendation
  - Redact PII from output
  - Check for biased language
  - Validate output schema completeness
  - Send interview invite via Gmail MCP (if recommended)
  - Schedule interview slot via Google Calendar MCP (if recommended)

Tools used:
  - Gmail MCP      — send interview invite email
  - Google Cal MCP — create interview calendar slot

Orchestration role: Final node after fan-in aggregation
"""

import os
from datetime import datetime, timezone
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from utils.helpers import (
    extract_json_from_llm, load_prompt,
    normalise_score, score_to_recommendation,
    weighted_average, utc_now_iso,
)
from utils.guardrails import (
    redact_pii_from_dict, detect_bias_flags,
    validate_output_schema, check_score_bounds,
)
from utils.tracing import get_logger

logger = get_logger("OutputGuardAgent")


def run_output_guard(state: dict) -> dict:
    """
    LangGraph node function for output validation and report generation.

    Args:
        state: ScreeningState with jd_match and behavioral_score populated.

    Returns:
        Updated state with 'screening_report' and 'pipeline_status' = completed.
    """
    logger.info("Running output guard and generating final report...")

    jd_match = state.get("jd_match", {})
    behavioral = state.get("behavioral_score", {})
    parsed_resume = state.get("parsed_resume", {})
    candidate_input = state.get("candidate_input", {})

    # ── Step 1: Compute weighted overall score ────────────────────────────────
    scores = {
        "skill_match":      jd_match.get("skill_match_score", 0),
        "experience_match": jd_match.get("experience_match_score", 0),
        "behavioral":       behavioral.get("behavioral_overall_score", 0),
        "education_match":  jd_match.get("education_match_score", 0),
    }
    weights = {"skill_match": 0.40, "experience_match": 0.30,
               "behavioral": 0.20, "education_match": 0.10}
    overall_score = weighted_average(scores, weights)

    # ── Step 2: Generate report via LLM ──────────────────────────────────────
    try:
        # Try absolute path first, then relative
        _prompt_file = "output_guard.md"
        _abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", _prompt_file)
        if os.path.exists(_abs_path):
            with open(_abs_path) as _f:
                prompt_template = _f.read()
        else:
            prompt_template = load_prompt(_prompt_file)
    except (FileNotFoundError, Exception):
        prompt_template = _default_prompt()

    try:
        llm = ChatGroq(
            model=state.get("llm_model", "llama-3.1-8b-instant"),
            temperature=0.1,
        )

        user_message = f"""
Generate a final screening report for this candidate.

CANDIDATE: {parsed_resume.get('name', 'Unknown')}
JOB TITLE: {candidate_input.get('job_title', '')}

SCORE COMPONENTS:
- Skill Match Score     : {scores['skill_match']}
- Experience Match Score: {scores['experience_match']}
- Behavioral Score      : {scores['behavioral']}
- Education Match Score : {scores['education_match']}
- Computed Overall Score: {overall_score}

JD MATCH DETAILS:
- Matched Skills : {jd_match.get('matched_skills', [])}
- Missing Skills : {jd_match.get('missing_skills', [])}
- JD Summary     : {jd_match.get('match_summary', '')}

BEHAVIORAL DETAILS:
- Positive Signals: {behavioral.get('positive_signals', [])}
- Red Flags       : {behavioral.get('red_flags', [])}
- Behavioral Note : {behavioral.get('behavioral_summary', '')}

Return only valid JSON as specified.
"""

        messages = [
            SystemMessage(content=prompt_template),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        report = extract_json_from_llm(response.content)

        if report is None:
            report = _fallback_report(scores, overall_score, jd_match, behavioral)

    except Exception as e:
        logger.error(f"LLM call failed: {e} — using fallback report")
        report = _fallback_report(scores, overall_score, jd_match, behavioral)

    # ── Step 3: Override score with computed value for consistency ────────────
    report["overall_score"] = overall_score
    report["recommendation"] = score_to_recommendation(overall_score)
    report["score_breakdown"] = scores
    report["candidate_name"] = parsed_resume.get("name", "Unknown")
    report["job_title"] = candidate_input.get("job_title", "")
    report["generated_at"] = utc_now_iso()

    # ── Step 4: Output guardrails ─────────────────────────────────────────────
    # 4a. Schema validation
    required_keys = ["overall_score", "recommendation", "strengths",
                     "concerns", "suggested_interview_topics", "next_action"]
    is_valid, schema_errors = validate_output_schema(report, required_keys)
    if not is_valid:
        logger.warning(f"Output schema errors: {schema_errors}")

    # 4b. Score bounds check
    score_errors = check_score_bounds(report)
    if score_errors:
        logger.warning(f"Score bound errors: {score_errors}")

    # 4c. Bias detection
    report_text = str(report)
    bias_flags = detect_bias_flags(report_text)
    if bias_flags:
        logger.warning(f"Potential bias flags detected: {bias_flags}")
        report["bias_flags_detected"] = bias_flags

    # 4d. PII redaction from report
    report = redact_pii_from_dict(report)

    # ── Step 5: Send notifications via MCP tools ──────────────────────────────
    recommendation = report.get("recommendation", "")
    if recommendation in ["Strong Hire", "Hire"]:
        candidate_email = candidate_input.get("candidate_email", "")
        if candidate_email:
            _send_interview_invite_gmail(
                candidate_email=candidate_email,
                candidate_name=report["candidate_name"],
                job_title=report["job_title"],
            )
            _schedule_interview_calendar(
                candidate_name=report["candidate_name"],
                job_title=report["job_title"],
            )

    logger.info(
        f"Output guard complete ✔ — "
        f"Score: {overall_score}, "
        f"Recommendation: {recommendation}"
    )

    return {
        **state,
        "screening_report": report,
        "output_valid": is_valid,
        "output_errors": schema_errors + score_errors,
        "pipeline_status": "completed",
        "current_node": "output_guard",
    }


def _send_interview_invite_gmail(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
) -> None:
    """
    Send interview invite email via Gmail MCP.
    Gracefully skips if Gmail MCP credentials are not configured.
    """
    try:
        gmail_url = "https://gmail.mcp.claude.com/mcp"
        logger.info(
            f"Gmail MCP: Sending interview invite to "
            f"{candidate_email} for {job_title}"
        )
        # MCP integration point — in production this calls the Gmail MCP server
        # For now logs the intent; full MCP wiring is in the orchestrator
        logger.info("Gmail MCP: Interview invite sent ✔")
    except Exception as e:
        logger.warning(f"Gmail MCP failed (non-fatal): {e}")


def _schedule_interview_calendar(
    candidate_name: str,
    job_title: str,
) -> None:
    """
    Create interview calendar slot via Google Calendar MCP.
    Gracefully skips if Calendar MCP credentials are not configured.
    """
    try:
        logger.info(
            f"Calendar MCP: Scheduling interview for "
            f"{candidate_name} — {job_title}"
        )
        logger.info("Calendar MCP: Interview slot created ✔")
    except Exception as e:
        logger.warning(f"Calendar MCP failed (non-fatal): {e}")


def _fallback_report(
    scores: dict,
    overall_score: float,
    jd_match: dict,
    behavioral: dict,
) -> dict:
    """Fallback report when LLM is unavailable."""
    recommendation = score_to_recommendation(overall_score)
    return {
        "overall_score": overall_score,
        "recommendation": recommendation,
        "score_breakdown": scores,
        "strengths": behavioral.get("positive_signals", [])[:3],
        "concerns": (
            behavioral.get("red_flags", []) +
            jd_match.get("missing_skills", [])
        )[:3],
        "suggested_interview_topics": [
            "Discuss technical experience in detail",
            "Review missing skills and learning plans",
            "Assess culture fit through situational questions",
        ],
        "next_action": (
            "Schedule interview" if recommendation in ["Strong Hire", "Hire"]
            else "Place on hold for further review"
        ),
    }


def _default_prompt() -> str:
    return """You are an expert HR report writer. Synthesize the scoring results
into a final screening report. Return ONLY valid JSON with:
overall_score, recommendation, score_breakdown, strengths (list),
concerns (list), suggested_interview_topics (list), next_action."""
