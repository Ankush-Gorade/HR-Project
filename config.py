"""
config.py
─────────
Central configuration for the HR Candidate Screening pipeline.
Loads environment variables, defines model settings, scoring thresholds,
and tool configurations used across all agents.
"""

import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()


# ─── LLM Configuration ───────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    """Settings for the language model used by all agents."""
    provider: str = "openai"                      # "openai" or "anthropic"
    model_name: str = "gpt-4o-mini"               # Model identifier
    temperature: float = 0.1                      # Low temp for consistent extraction
    max_tokens: int = 2048                        # Max output tokens per agent call
    request_timeout: int = 60                     # Seconds before timeout


# ─── Scoring Thresholds ───────────────────────────────────────────────────────

class ScoringConfig(BaseModel):
    """Thresholds that drive conditional routing decisions."""
    min_overall_score: int = 0                    # Minimum possible score
    max_overall_score: int = 100                  # Maximum possible score
    interview_threshold: int = 65                 # Score >= this → recommend interview
    strong_hire_threshold: int = 85               # Score >= this → strong hire
    auto_reject_threshold: int = 30               # Score < this → auto reject

    # Component weights that sum to 1.0
    skill_match_weight: float = 0.40              # JD skill alignment weight
    experience_weight: float = 0.30              # Years & relevance weight
    behavioral_weight: float = 0.20              # Soft skills / culture fit weight
    education_weight: float = 0.10              # Education match weight


# ─── Tool Configuration ───────────────────────────────────────────────────────

class ToolConfig(BaseModel):
    """External tool and MCP server settings."""
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    web_search_max_results: int = 3               # Max search results per query
    enable_gmail_mcp: bool = True                 # Send interview invites via Gmail
    enable_calendar_mcp: bool = True              # Schedule slots via Google Calendar


# ─── Guardrail Configuration ─────────────────────────────────────────────────

class GuardrailConfig(BaseModel):
    """Settings that control input/output guardrail behaviour."""
    max_resume_length_chars: int = 15_000         # Reject resumes exceeding this
    min_resume_length_chars: int = 100            # Reject suspiciously short inputs
    max_jd_length_chars: int = 8_000             # Reject JDs exceeding this
    pii_fields_to_redact: list = [               # Fields scrubbed from output
        "phone", "email", "address", "date_of_birth", "national_id"
    ]
    injection_patterns: list = [                 # Prompt-injection red flags
        "ignore previous instructions",
        "disregard all prior",
        "you are now",
        "act as",
        "forget everything",
        "new instructions:",
    ]


# ─── Observability Configuration ──────────────────────────────────────────────

class ObservabilityConfig(BaseModel):
    """LangSmith tracing and logging settings."""
    tracing_enabled: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    project_name: str = os.getenv("LANGCHAIN_PROJECT", "hr-screening-agent")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_dir: str = "logs"                         # Directory for local log files


# ─── App-level Settings ───────────────────────────────────────────────────────

class AppConfig(BaseModel):
    """Top-level application settings."""
    llm: LLMConfig = LLMConfig()
    scoring: ScoringConfig = ScoringConfig()
    tools: ToolConfig = ToolConfig()
    guardrails: GuardrailConfig = GuardrailConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
    human_review_enabled: bool = (
        os.getenv("HUMAN_REVIEW_ENABLED", "true").lower() == "true"
    )
    prompts_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")  # Absolute path to prompts
    data_dir: str = "data"                        # Path to input data files


# ─── Singleton instance used by all modules ───────────────────────────────────
cfg = AppConfig()
