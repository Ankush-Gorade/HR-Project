"""
pipeline/orchestrator.py
────────────────────────
Builds and runs the full HR Screening LangGraph pipeline.

Orchestration patterns used:
  1. Conditional routing  — InputGuard → Reject or continue
  2. Parallel fan-out/in  — JDMatcher + BehavioralScorer run concurrently
  3. Human-in-the-loop    — Checkpoint before final output
  4. Iterative refinement — Human can trigger re-scoring (max 3 iterations)
"""

from langgraph.graph import StateGraph, END
from pipeline.state import ScreeningState
from agents.input_guard_agent import run_input_guard, route_after_input_guard
from agents.resume_parser_agent import run_resume_parser
from agents.jd_matcher_agent import run_jd_matcher
from agents.behavioral_scorer_agent import run_behavioral_scorer
from agents.output_guard_agent import run_output_guard
from utils.helpers import generate_trace_id, utc_now_iso
from utils.tracing import get_logger

logger = get_logger("Orchestrator")


# ─── Rejection Node ───────────────────────────────────────────────────────────

def reject_node(state: dict) -> dict:
    """Terminal node for invalid/rejected inputs."""
    logger.warning(f"Pipeline rejected: {state.get('error_message', 'Unknown reason')}")
    return {
        **state,
        "pipeline_status": "rejected",
        "current_node": "reject",
        "screening_report": {
            "recommendation": "Reject",
            "overall_score": 0,
            "candidate_name": state.get("candidate_input", {}).get("candidate_name", "Unknown"),
            "job_title": state.get("candidate_input", {}).get("job_title", ""),
            "strengths": [],
            "concerns": state.get("input_errors", ["Input validation failed"]),
            "suggested_interview_topics": [],
            "next_action": "Application rejected at input validation stage",
            "generated_at": utc_now_iso(),
        },
    }


# ─── Parallel Fan-out Node ────────────────────────────────────────────────────

def run_parallel_scoring(state: dict) -> dict:
    """
    Fan-out node: runs JDMatcher and BehavioralScorer concurrently
    then merges both results back into state.

    LangGraph supports true parallel execution via Send API.
    Here we run sequentially and merge — functionally identical output.
    """
    logger.info("Running parallel scoring (JD Matcher + Behavioral Scorer)...")

    # Run both agents
    state_after_jd = run_jd_matcher(state)
    state_after_behavioral = run_behavioral_scorer(state)

    # Merge results from both agents into a single state
    merged_state = {
        **state,
        "jd_match": state_after_jd.get("jd_match", {}),
        "behavioral_score": state_after_behavioral.get("behavioral_score", {}),
        "current_node": "parallel_scoring",
    }

    logger.info("Parallel scoring complete ✔")
    return merged_state


# ─── Human-in-the-Loop Node ───────────────────────────────────────────────────

def human_review_node(state: dict) -> dict:
    """
    Human-in-the-loop checkpoint.

    In production this pauses the pipeline and waits for
    a recruiter to approve/reject/request refinement via UI.
    In this implementation it auto-approves unless
    human_approved is explicitly set to False in state.
    """
    logger.info("Human review checkpoint reached...")

    # Check if human has already made a decision
    human_approved = state.get("human_approved", None)

    if human_approved is None:
        # Auto-approve for automated runs
        # In production: pause here and wait for human input
        logger.info("No human decision found — auto-approving for automated run")
        human_approved = True

    if human_approved:
        logger.info("Human review: APPROVED ✔")
    else:
        logger.info("Human review: REJECTED — requesting refinement")

    return {
        **state,
        "human_approved": human_approved,
        "current_node": "human_review",
    }


def route_after_human_review(state: dict) -> str:
    """
    Conditional edge after human review checkpoint.

    Returns:
        'output_guard'     if approved
        'parallel_scoring' if refinement requested (within iteration limit)
        'reject'           if max iterations exceeded
    """
    human_approved  = state.get("human_approved", True)
    iteration_count = state.get("iteration_count", 0)
    max_iterations  = state.get("max_iterations", 3)

    if human_approved:
        return "output_guard"

    if iteration_count < max_iterations:
        logger.info(f"Refinement requested — iteration {iteration_count + 1}/{max_iterations}")
        return "parallel_scoring"

    logger.warning("Max iterations reached — terminating pipeline")
    return "reject"


def increment_iteration(state: dict) -> dict:
    """Increment the refinement loop counter."""
    return {
        **state,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "human_approved": None,  # Reset for next review
    }


# ─── Pipeline Builder ─────────────────────────────────────────────────────────

def build_pipeline() -> StateGraph:
    """
    Construct and compile the full LangGraph StateGraph.

    Graph structure:
        START
          │
          ▼
        input_guard ──(invalid)──▶ reject ──▶ END
          │ (valid)
          ▼
        resume_parser
          │
          ▼
        parallel_scoring  (JDMatcher + BehavioralScorer)
          │
          ▼
        human_review ──(reject/refine)──▶ increment ──▶ parallel_scoring
          │ (approved)
          ▼
        output_guard
          │
          ▼
         END

    Returns:
        Compiled LangGraph StateGraph ready to invoke.
    """
    logger.info("Building LangGraph pipeline...")

    graph = StateGraph(ScreeningState)

    # ── Add all nodes ─────────────────────────────────────────────────────────
    graph.add_node("input_guard",       run_input_guard)
    graph.add_node("resume_parser",     run_resume_parser)
    graph.add_node("parallel_scoring",  run_parallel_scoring)
    graph.add_node("human_review",      human_review_node)
    graph.add_node("increment",         increment_iteration)
    graph.add_node("output_guard",      run_output_guard)
    graph.add_node("reject",            reject_node)

    # ── Set entry point ───────────────────────────────────────────────────────
    graph.set_entry_point("input_guard")

    # ── Add edges ─────────────────────────────────────────────────────────────

    # Conditional routing after input guard
    graph.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {
            "resume_parser": "resume_parser",
            "reject":        "reject",
        }
    )

    # Sequential: resume_parser → parallel_scoring
    graph.add_edge("resume_parser", "parallel_scoring")

    # Sequential: parallel_scoring → human_review
    graph.add_edge("parallel_scoring", "human_review")

    # Conditional routing after human review
    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "output_guard":      "output_guard",
            "parallel_scoring":  "increment",
            "reject":            "reject",
        }
    )

    # Refinement loop: increment → parallel_scoring
    graph.add_edge("increment", "parallel_scoring")

    # Final edges to END
    graph.add_edge("output_guard", END)
    graph.add_edge("reject",       END)

    compiled = graph.compile()
    logger.info("Pipeline compiled successfully ✔")
    return compiled


# ─── Convenience Runner ───────────────────────────────────────────────────────

def run_pipeline(
    resume_text: str,
    job_description: str,
    job_title: str,
    department: str = "",
    candidate_name: str = "",
    candidate_email: str = "",
    human_approved: bool = True,
    human_notes: str = "",
    llm_model: str = "llama-3.1-8b-instant",
) -> dict:
    """
    Convenience function to run the full pipeline from raw inputs.

    Args:
        resume_text:      Full resume as plain text
        job_description:  Full job description text
        job_title:        Target role title
        department:       Hiring department
        candidate_name:   Candidate name (optional)
        candidate_email:  Candidate email for invite (optional)
        human_approved:   Pre-set human decision (True=auto-approve)
        human_notes:      Reviewer notes
        llm_model:        LLM model to use

    Returns:
        Final ScreeningState dict with screening_report populated.
    """
    pipeline = build_pipeline()

    initial_state = {
        "candidate_input": {
            "resume_text":    resume_text,
            "job_description": job_description,
            "job_title":      job_title,
            "department":     department,
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
        },
        "human_approved":   human_approved,
        "human_notes":      human_notes,
        "iteration_count":  0,
        "max_iterations":   3,
        "pipeline_status":  "running",
        "trace_id":         generate_trace_id(),
        "llm_model":        llm_model,
    }

    logger.info(f"Starting pipeline run | trace_id: {initial_state['trace_id']}")
    result = pipeline.invoke(initial_state)
    logger.info(f"Pipeline complete | status: {result.get('pipeline_status')}")

    return result
