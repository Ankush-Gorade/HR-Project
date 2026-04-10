import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

class LLMConfig(BaseModel):
    provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 2048
    request_timeout: int = 60

class ScoringConfig(BaseModel):
    min_overall_score: int = 0
    max_overall_score: int = 100
    interview_threshold: int = 65
    strong_hire_threshold: int = 85
    auto_reject_threshold: int = 30
    skill_match_weight: float = 0.40
    experience_weight: float = 0.30
    behavioral_weight: float = 0.20
    education_weight: float = 0.10

class ToolConfig(BaseModel):
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    web_search_max_results: int = 3
    enable_gmail_mcp: bool = True
    enable_calendar_mcp: bool = True

class GuardrailConfig(BaseModel):
    max_resume_length_chars: int = 15000
    min_resume_length_chars: int = 100
    max_jd_length_chars: int = 8000
    pii_fields_to_redact: list = ["phone","email","address","date_of_birth","national_id"]
    injection_patterns: list = [
        "ignore previous instructions",
        "disregard all prior",
        "you are now",
        "act as",
        "forget everything",
        "new instructions:",
    ]

class ObservabilityConfig(BaseModel):
    tracing_enabled: bool = os.getenv("LANGCHAIN_TRACING_V2","false").lower() == "true"
    project_name: str = os.getenv("LANGCHAIN_PROJECT","hr-screening-agent")
    log_level: str = os.getenv("LOG_LEVEL","INFO")
    log_dir: str = "logs"

class AppConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    scoring: ScoringConfig = ScoringConfig()
    tools: ToolConfig = ToolConfig()
    guardrails: GuardrailConfig = GuardrailConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
    human_review_enabled: bool = os.getenv("HUMAN_REVIEW_ENABLED","true").lower() == "true"
    prompts_dir: str = "prompts"
    data_dir: str = "data"

cfg = AppConfig()
