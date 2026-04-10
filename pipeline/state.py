"""
pipeline/state.py
─────────────────
Shared LangGraph state that flows through every node in the pipeline.
"""

from typing import Any, Literal, Optional
from typing_extensions import TypedDict


class ScreeningState(TypedDict, total=False):

    # ── Raw Inputs ───────────────────────────────────────────────────────────
    candidate_input: dict

    # ── Guardrail Results ────────────────────────────────────────────────────
    input_valid: bool
    input_errors: list
    output_valid: bool
    output_errors: list

    # ── Agent Outputs ────────────────────────────────────────────────────────
    parsed_resume: dict
    jd_match: dict
    behavioral_score: dict

    # ── Human-in-the-Loop ────────────────────────────────────────────────────
    human_review_requested: bool
    human_approved: Optional[bool]
    human_notes: str

    # ── Final Output ─────────────────────────────────────────────────────────
    screening_report: dict

    # ── Pipeline Metadata ────────────────────────────────────────────────────
    current_node: str
    error_message: str
    iteration_count: int
    max_iterations: int
    pipeline_status: str
    trace_id: str
    llm_model: str
