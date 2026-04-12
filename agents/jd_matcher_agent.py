"""
agents/jd_matcher_agent.py
──────────────────────────
Agent 3: JD Matcher

Responsibilities:
  - Compare candidate skills against job description requirements
  - Compute skill match, experience match, education match scores
  - Use Tavily web search to fetch market context for the role
  - Run in PARALLEL with BehavioralScorerAgent (Agent 4)

Tools used:
  - Tavily Web Search (external tool) — fetches current skill demand context

Orchestration role: Parallel fan-out node (runs concurrently with Agent 4)
"""

import os
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from utils.helpers import extract_json_from_llm, load_prompt, normalise_score
from utils.tracing import get_logger

logger = get_logger("JDMatcherAgent")


def _web_search_skill_context(job_title: str, skills: list) -> str:
    """
    Use Tavily to fetch current market context for the role and skills.
    Falls back gracefully if Tavily key is not set.

    Args:
        job_title: Target job title
        skills:    List of required skills

    Returns:
        A short market context string to inform scoring.
    """
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.warning("TAVILY_API_KEY not set — skipping web search")
        return f"No market context available. Role: {job_title}"

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        skills_str = ", ".join(skills[:5])
        query = f"{job_title} required skills market demand 2024 {skills_str}"
        results = client.search(query=query, max_results=3)
        snippets = [r.get("content", "")[:300] for r in results.get("results", [])]
        context = " | ".join(snippets[:2])
        logger.info(f"Web search completed for: {job_title}")
        return context[:800]
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return f"Market context unavailable for {job_title}"


def run_jd_matcher(state: dict) -> dict:
    """
    LangGraph node function for JD matching.

    Args:
        state: ScreeningState with parsed_resume and candidate_input.

    Returns:
        Updated state with 'jd_match' populated.
    """
    logger.info("Running JD matching...")

    parsed_resume = state.get("parsed_resume", {})
    candidate_input = state.get("candidate_input", {})
    job_description = candidate_input.get("job_description", "")
    job_title = candidate_input.get("job_title", "")
    candidate_skills = parsed_resume.get("skills", [])
    total_exp_years = parsed_resume.get("total_experience_years", 0.0)

    # ── Step 1: Fetch market context via web search ───────────────────────────
    market_context = _web_search_skill_context(job_title, candidate_skills)

    # ── Step 2: Load prompt and call LLM ─────────────────────────────────────
    try:
        prompt_template = load_prompt("jd_matcher.md")
    except FileNotFoundError:
        prompt_template = _default_prompt()

    try:
        llm = ChatGroq(
            model=state.get("llm_model", "llama-3.1-8b-instant"),
            temperature=0.0,
        )

        user_message = f"""
Compare this candidate against the job description and return match scores.

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
- Skills: {', '.join(candidate_skills)}
- Total Experience: {total_exp_years} years
- Education: {parsed_resume.get('education', [])}
- Certifications: {parsed_resume.get('certifications', [])}

MARKET CONTEXT (from web search):
{market_context}

Return only valid JSON as specified.
"""

        messages = [
            SystemMessage(content=prompt_template),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        result = extract_json_from_llm(response.content)

        if result is None:
            logger.error("Failed to parse JD match JSON — using fallback scoring")
            result = _fallback_score(candidate_skills, job_description, total_exp_years)

    except Exception as e:
        logger.error(f"LLM call failed: {e} — using fallback scoring")
        result = _fallback_score(candidate_skills, job_description, total_exp_years)

    # ── Step 3: Validate scores are in range ─────────────────────────────────
    for score_field in ["skill_match_score", "experience_match_score",
                        "education_match_score", "overall_jd_score"]:
        if score_field in result:
            result[score_field] = normalise_score(float(result[score_field]))

    result["web_search_context"] = market_context

    logger.info(
        f"JD matching complete ✔ — "
        f"Overall JD score: {result.get('overall_jd_score', 0)}, "
        f"Matched skills: {len(result.get('matched_skills', []))}"
    )

    return {
        **state,
        "jd_match": result,
        "current_node": "jd_matcher",
    }


def _fallback_score(candidate_skills: list, job_description: str, exp_years: float) -> dict:
    """
    Simple keyword-based fallback scoring if LLM fails.
    Counts skill keyword overlaps between resume and JD.
    """
    jd_lower = job_description.lower()
    matched = [s for s in candidate_skills if s.lower() in jd_lower]
    match_pct = (len(matched) / max(len(candidate_skills), 1)) * 100

    return {
        "required_skills": [],
        "preferred_skills": [],
        "matched_skills": matched,
        "missing_skills": [],
        "skill_match_score": normalise_score(match_pct),
        "experience_match_score": min(exp_years * 12, 100),
        "education_match_score": 70.0,
        "overall_jd_score": normalise_score(match_pct * 0.6 + 30),
        "match_summary": f"Fallback score — {len(matched)} skills matched",
    }


def _default_prompt() -> str:
    return """You are an expert HR technical screener.
Compare the candidate profile against the job description.
Return ONLY valid JSON with: required_skills, preferred_skills, matched_skills,
missing_skills, skill_match_score, experience_match_score, education_match_score,
overall_jd_score, match_summary."""
