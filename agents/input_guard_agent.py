"""
agents/input_guard_agent.py
───────────────────────────
Agent 1: Input Guard

Responsibilities:
  - Run rule-based guardrails (length, required fields, injection patterns)
  - Run LLM-based semantic validation (is this actually a resume?)
  - Set state['input_valid'] = True/False
  - If invalid → pipeline routes to early rejection

Orchestration role: CONDITIONAL ROUTING gate.
  Valid   → continue to ResumeParserAgent
  Invalid → terminate with rejection message
"""

import os
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from utils.guardrails import validate_candidate_input
from utils.helpers import extract_json_from_llm, utc_now_iso, load_prompt
from utils.tracing import get_logger

logger = get_logger("InputGuardAgent")


def run_input_guard(state: dict) -> dict:
    """
    LangGraph node function for input validation.

    Args:
        state: ScreeningState dict with 'candidate_input' populated.

    Returns:
        Updated state with 'input_valid', 'input_errors', 'pipeline_status'.
    """
    logger.info("Running input validation...")
    candidate_input = state.get("candidate_input", {})

    # ── Step 1: Rule-based guardrails (fast, no LLM needed) ──────────────────
    is_valid, errors = validate_candidate_input(candidate_input)

    if not is_valid:
        logger.warning(f"Rule-based validation failed: {errors}")
        return {
            **state,
            "input_valid": False,
            "input_errors": errors,
            "pipeline_status": "rejected",
            "error_message": "Input validation failed: " + "; ".join(errors),
            "current_node": "input_guard",
        }

    # ── Step 2: LLM-based semantic validation ────────────────────────────────
    try:
        prompt_template = load_prompt("input_guard.md")
        llm = ChatGroq(
            model=state.get("llm_model", "llama-3.1-8b-instant"),
            temperature=0.0,
        )

        resume = candidate_input.get("resume_text", "")
        jd = candidate_input.get("job_description", "")
        job_title = candidate_input.get("job_title", "")

        user_message = f"""
Please validate the following inputs for an HR screening pipeline.

JOB TITLE: {job_title}

RESUME:
{resume[:3000]}

JOB DESCRIPTION:
{jd[:2000]}

Return only JSON as specified in your instructions.
"""

        messages = [
            SystemMessage(content=prompt_template),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        result = extract_json_from_llm(response.content)

        if result is None:
            logger.warning("LLM returned unparseable response — defaulting to valid")
            result = {"is_valid": True, "issues": [], "recommendation": "proceed"}

        llm_valid = result.get("is_valid", True)
        llm_issues = result.get("issues", [])

        if not llm_valid:
            logger.warning(f"LLM semantic validation failed: {llm_issues}")
            return {
                **state,
                "input_valid": False,
                "input_errors": llm_issues,
                "pipeline_status": "rejected",
                "error_message": "Semantic validation failed: " + "; ".join(llm_issues),
                "current_node": "input_guard",
            }

    except Exception as e:
        # LLM failure is non-fatal — log and continue if rule-based passed
        logger.warning(f"LLM validation error (non-fatal): {e}")

    # ── Step 3: All checks passed ─────────────────────────────────────────────
    logger.info("Input validation passed ✔")
    return {
        **state,
        "input_valid": True,
        "input_errors": [],
        "pipeline_status": "running",
        "current_node": "input_guard",
    }


def route_after_input_guard(state: dict) -> str:
    """
    LangGraph conditional edge function.
    Decides next node based on input validation result.

    Returns:
        'resume_parser' if valid, 'reject' if invalid.
    """
    if state.get("input_valid", False):
        return "resume_parser"
    return "reject"
