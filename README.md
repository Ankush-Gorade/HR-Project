# HR Candidate Screening Multi-Agent System

A production-grade, multi-agent HR screening pipeline built with **LangGraph**.  
Automates end-to-end candidate evaluation — from raw resume + job description to a structured screening report with a hire/reject recommendation.

---

## Architecture Overview

```
Candidate Input
      │
      ▼
┌─────────────────────┐       ┌──────────┐
│  Agent 1            │──────▶│  REJECT  │  (invalid input)
│  Input Guard        │       └──────────┘
└─────────────────────┘
      │ (valid)
      ▼
┌─────────────────────┐
│  Agent 2            │
│  Resume Parser      │  ← File processing tool
└─────────────────────┘
      │
      ├─────────────────────────────────────┐
      ▼                                     ▼
┌─────────────────┐               ┌─────────────────────┐
│  Agent 3        │               │  Agent 4            │
│  JD Matcher     │  ← Web Search │  Behavioral Scorer  │
└─────────────────┘               └─────────────────────┘
      │                                     │
      └──────────────┬──────────────────────┘
                     ▼ (fan-in)
          ┌─────────────────────┐
          │  Human-in-the-Loop  │  ← Reviewer approves / requests refinement
          └─────────────────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  Agent 5            │
          │  Output Guard       │  ← PII redact, bias check, schema validate
          └─────────────────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  Screening Report   │  ← JSON + human-readable summary
          └─────────────────────┘
```

### Orchestration Patterns Used
| Pattern | Where |
|---|---|
| Conditional routing | InputGuard → Reject (invalid) or continue (valid) |
| Parallel fan-out/fan-in | JDMatcher + BehavioralScorer run concurrently |
| Iterative refinement loop | Human reviewer triggers re-score (max 3 iterations) |
| Human-in-the-loop | Checkpoint before final output |

---

## Project Structure

```
hr_screening_agent/
├── agents/
│   ├── __init__.py
│   ├── input_guard_agent.py        # Agent 1 – validate & sanitise input
│   ├── resume_parser_agent.py      # Agent 2 – extract structured resume data
│   ├── jd_matcher_agent.py         # Agent 3 – score against job description
│   ├── behavioral_scorer_agent.py  # Agent 4 – soft skills & culture fit
│   └── output_guard_agent.py       # Agent 5 – PII redact, format, bias check
├── pipeline/
│   ├── __init__.py
│   ├── state.py                    # LangGraph ScreeningState TypedDict
│   └── orchestrator.py             # StateGraph construction & routing logic
├── utils/
│   ├── __init__.py
│   ├── helpers.py                  # Prompt loader, score utils, JSON extraction
│   ├── guardrails.py               # Input/output guardrail functions
│   └── tracing.py                  # LangSmith setup & agent trace decorator
├── prompts/
│   ├── input_guard.md
│   ├── resume_parser.md
│   ├── jd_matcher.md
│   ├── behavioral_scorer.md
│   └── output_guard.md
├── evaluation/
│   ├── eval_dataset.json           # 20 labelled test cases
│   └── eval_script.py              # Evaluation runner + metrics
├── tests/
│   └── test_scenarios.py           # 5+ structured test scenarios
├── data/                           # Sample resumes & JDs for testing
├── logs/                           # Auto-created: pipeline.log
├── docs/                           # Design document (HTML/PDF)
├── config.py                       # Central configuration (Pydantic)
├── main_runner.ipynb               # Entry-point notebook
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/HR-Project.git
cd hr-screening-agent
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required keys:
| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (or `ANTHROPIC_API_KEY`) |
| `LANGCHAIN_API_KEY` | LangSmith API key for tracing |
| `TAVILY_API_KEY` | Tavily web search API key |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (Gmail/Calendar) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |

### 5. Run the pipeline

Open and run **`main_runner.ipynb`** in Jupyter:

```bash
jupyter notebook main_runner.ipynb
```

Or run all test scenarios via the CLI:

```bash
python tests/test_scenarios.py
```

---

## Running Evaluations

```bash
python evaluation/eval_script.py
```

Outputs a classification report (Precision / Recall / F1) for the
ResumeParserAgent on 20 labelled test cases.

---

## Tools & Integrations

| Tool | Agent | Purpose |
|---|---|---|
| Tavily Web Search | JDMatcherAgent | Fetch market skill context for a role |
| Gmail MCP | OutputGuardAgent | Send interview invite emails |
| Google Calendar MCP | OutputGuardAgent | Create interview calendar slots |
| LangSmith | All agents | Full pipeline tracing & observability |

---

## Observability

Every agent call, tool invocation, and routing decision is traced in **LangSmith**.  
Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=<your-key>` in `.env`.

View traces at: https://smith.langchain.com

---

## Test Scenarios

Five scenarios covering all pipeline branches:

| # | Scenario | Path |
|---|---|---|
| 1 | Strong candidate – happy path | Full pipeline → Strong Hire |
| 2 | Weak candidate – below threshold | Full pipeline → Reject |
| 3 | Prompt injection in resume | InputGuard → early Reject |
| 4 | Missing required fields | InputGuard → early Reject |
| 5 | Human reviewer requests re-score | Refinement loop → revised recommendation |

---

## License

MIT
