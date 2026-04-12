HR Candidate Screening — Multi-Agent System
> **Assignment 1 | Multi-Agent Systems | LangGraph | Domain: Human Resources**
An end-to-end HR candidate screening pipeline that automates resume evaluation, job description matching, behavioral analysis, and screening report generation using 5 specialised sub-agents orchestrated with LangGraph.
---
Demo

Run the interactive Streamlit UI from Google Colab — paste a resume, paste a job description, get a full screening report in ~30 seconds.
---
Architecture
```
Candidate Input (resume + JD)
          │
          ▼
┌─────────────────────┐
│  Agent 1            │──(invalid)──▶ REJECT ──▶ END
│  Input Guard        │
└─────────────────────┘
          │ (valid)
          ▼
┌─────────────────────┐
│  Agent 2            │
│  Resume Parser      │
└─────────────────────┘
          │
    ┌─────┴─────┐   ← Parallel fan-out
    ▼           ▼
┌────────┐ ┌──────────┐
│Agent 3 │ │ Agent 4  │
│JD Match│ │Behavioral│
│Tavily  │ │DuckDuckGo│
└────────┘ └──────────┘
    └─────┬─────┘   ← Fan-in / aggregate
          ▼
┌─────────────────────┐
│  Human-in-the-Loop  │◀── (refine) ──┐
│  Checkpoint         │               │
└─────────────────────┘               │
          │ (approved)                 │
          ▼                           │
┌─────────────────────┐               │
│  Agent 5            │───────────────┘
│  Output Guard       │
└─────────────────────┘
          │
          ▼
   Screening Report
```
Orchestration Patterns
Pattern	Where	Justification
Conditional routing	After Agent 1	Reject invalid inputs early — no wasted LLM calls
Parallel fan-out/in	Agents 3 & 4	Independent tasks — run concurrently to halve latency
Human-in-the-loop	After scoring	High-stakes decisions need human oversight
Iterative refinement	On rejection	Reviewer triggers re-score up to 3 iterations
---
Project Structure
```
HR-Project/
├── agents/
│   ├── __init__.py
│   ├── input_guard_agent.py        # Agent 1 — validate & sanitise
│   ├── resume_parser_agent.py      # Agent 2 — extract structured data
│   ├── jd_matcher_agent.py         # Agent 3 — score vs job description
│   ├── behavioral_scorer_agent.py  # Agent 4 — soft skills & culture fit
│   └── output_guard_agent.py       # Agent 5 — report, PII redact, MCP
├── pipeline/
│   ├── __init__.py
│   ├── state.py                    # LangGraph ScreeningState TypedDict
│   └── orchestrator.py             # StateGraph with all edges & routing
├── utils/
│   ├── __init__.py
│   ├── helpers.py                  # Score utils, JSON extraction, prompts
│   ├── guardrails.py               # Input/output guardrail functions
│   └── tracing.py                  # LangSmith + structured logger
├── prompts/
│   ├── input_guard.md
│   ├── resume_parser.md
│   ├── jd_matcher.md
│   ├── behavioral_scorer.md
│   └── output_guard.md
├── evaluation/
│   ├── eval_dataset.json           # 20 labelled test cases
│   └── eval_script.py              # Evaluation runner + F1 metrics
├── tests/
│   └── test_scenarios.py           # 5 structured test scenarios
├── docs/
│   └── design_document.html        # Full design document
├── streamlit_app.py                # Interactive UI
├── config.py                       # Central Pydantic configuration
├── requirements.txt
├── main_runner.ipynb               # Submission entry-point notebook
└── README.md
```
---
Quick Start
Option A — Google Colab (Recommended)
Open `main_runner.ipynb` in Google Colab and run cells in order:
Step 1 — Install dependencies
Step 2 — Clone private repo (requires GitHub token)
Step 3 — Patch agents + configure API keys
Step 4 — Verify imports
Step 5 — Full pipeline run
Step 6 — Run all 5 test scenarios
Step 7 — Sub-agent evaluation
Step 8 — Launch Streamlit UI
Step 9 — Download design document
Option B — Run Locally
```bash
# Clone the repo
git clone https://github.com/Ankush-Gorade/HR-Project.git
cd HR-Project

# Install dependencies
pip install -r requirements.txt

# Set API keys
cp .env.example .env
# Edit .env with your keys

# Run Streamlit UI
streamlit run streamlit_app.py
```
---
Setup — API Keys Required
Key	Required	Where to get	Cost
`GROQ_API_KEY`	✅ Yes	console.groq.com	Free
`TAVILY_API_KEY`	Optional	app.tavily.com	Free tier
`NGROK_AUTHTOKEN`	For Colab UI	dashboard.ngrok.com	Free
Create a `.env` file:
```
GROQ_API_KEY=your_groq_key_here
TAVILY_API_KEY=your_tavily_key_here
LANGCHAIN_TRACING_V2=false
HUMAN_REVIEW_ENABLED=true
```
---
Sub-Agents
Agent 1 — Input Guard
Rule-based checks: required fields, length bounds, injection patterns
LLM-based semantic validation: is this actually a resume?
Routes to `reject` (invalid) or `resume_parser` (valid)
Prompt strategy: Few-shot with 3 examples (valid, gibberish, injection)
Agent 2 — Resume Parser
Extracts: name, email, skills, experience, education, certifications
Computes `total_experience_years` from role durations
Keyword-based fallback if LLM fails
Prompt strategy: Chain-of-thought with explicit reasoning steps
Agent 3 — JD Matcher (Tool: Tavily Web Search)
Scores skill match, experience match, education match against JD
Uses Tavily to fetch live market context for the role
Identifies matched and missing required skills
Prompt strategy: Structured rubric with two few-shot examples
Agent 4 — Behavioral Scorer (Tool: DuckDuckGo Search)
Detects red flags: job hopping, vague descriptions, gaps
Identifies positive signals: quantified impact, leadership, mentoring
Verifies previous employers via DuckDuckGo web search
Prompt strategy: Rubric-based with scoring criteria per dimension
Agent 5 — Output Guard (Tools: Gmail MCP, Google Calendar MCP)
Computes weighted overall score: skill(40%) + exp(30%) + behavioral(20%) + edu(10%)
Redacts PII from output report
Detects biased language
Sends interview invite via Gmail MCP for Hire/Strong Hire
Creates calendar slot via Google Calendar MCP
---
Guardrail Strategy
Input Guardrails (Agent 1)
Guardrail	Type	Catches
Required field check	Rule-based	Missing resume, JD, or job title
Length validation	Rule-based	Resume < 100 chars or > 15,000 chars
Prompt injection scan	Rule-based	"ignore previous instructions", "act as", etc.
Semantic validation	LLM-based	Gibberish, non-resume content
Output Guardrails (Agent 5)
Guardrail	Type	Catches
PII redaction	Regex	Email, phone, SSN in output
Schema validation	Rule-based	Missing required report fields
Score bounds check	Rule-based	Scores outside [0, 100]
Bias detection	Regex	Age, gender, religion references
---
Test Scenarios
#	Scenario	Input	Expected	Actual
1	Happy path	Strong 7-year engineer	Strong Hire	✅ Strong Hire (89.2)
2	Weak candidate	B.Com graduate, basic skills	Reject/Hold	✅ Rejected at input
3	Prompt injection	"ignore previous instructions"	Rejected	✅ Rejected (rule-based)
4	Missing fields	Empty resume, JD, title	Rejected	✅ Rejected (5 errors)
5	Human refinement	Strong candidate, human rejects	Re-score	✅ Iteration 1 triggered
Result: 5/5 scenarios passed
---
Evaluation Results
Agent evaluated: ResumeParserAgent  
Dataset: 20 manually curated resumes across 15 job roles  
Metric: Field-level Precision / Recall / F1
Field	Correct	Accuracy	F1
Name extraction	20/20	100%	1.000
Skills extraction	20/20	100%	1.000
Email extraction	20/20	100%	1.000
Experience detection	20/20	100%	1.000
Experience count	20/20	100%	1.000
Experience years	20/20	100%	1.000
Education detection	20/20	100%	1.000
OVERALL	140/140	100%	1.000
---
Observability
Every agent call, tool invocation, and routing decision is logged:
Console logs — coloured output with timestamps
File logs — `logs/pipeline.log`
LangSmith — full pipeline trace (set `LANGCHAIN_TRACING_V2=true`)
Trace ID — unique ID per pipeline run for correlation
---
Prompt Engineering
All prompts are stored as `.md` files in `prompts/` and loaded at runtime.
Technique	Used In
Few-shot examples (2–3 per agent)	All 5 agents
Chain-of-thought reasoning steps	Resume Parser, JD Matcher
Role assignment	All 5 agents
Explicit output schema	All 5 agents
Rubric-based scoring criteria	Behavioral Scorer
---
Streamlit UI
Interactive web interface with 4 tabs:
Screen Candidate — paste resume + JD, get full report
Test Scenarios — run any of the 5 predefined scenarios
Evaluation — view F1 results, run live evaluation
About — architecture overview, setup instructions
Run locally:
```bash
streamlit run streamlit_app.py
```
Run in Colab: See Step 8 in `main_runner.ipynb`
---
Requirements
```
langgraph>=0.2.0
langchain>=0.3.0
langchain-groq>=0.2.0
langchain-community>=0.3.0
pydantic>=2.0.0
python-dotenv>=1.0.0
duckduckgo-search>=6.0.0
tavily-python>=0.3.0
streamlit>=1.35.0
pyngrok>=7.0.0
pandas>=2.0.0
```
---
Limitations & Future Work
No true parallelism — Agents 3 & 4 run sequentially in current implementation; production would use LangGraph's Send API
English-only — prompts and guardrails optimised for English resumes
MCP tools — Gmail/Calendar MCP log intent but require OAuth for full activation
Future: Multi-candidate ranking, LinkedIn profile verification, feedback loop for score improvement
---
License
MIT
