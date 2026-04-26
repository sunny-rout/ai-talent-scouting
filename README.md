<div align="center">

# TalentScout AI

### AI-Powered Talent Scouting & Engagement Agent

**Takes a Job Description as input → discovers matching candidates → engages them conversationally → outputs a ranked shortlist scored on Match Score + Interest Score.**

[Demo Video](#demo-video) . [Quick Start](#quick-start) · [Architecture](#architecture) · [Scoring Logic](#scoring-logic) · [API Reference](#api-reference)

</div>

---

## Problem Statement

Recruiters spend hours sifting through profiles and chasing candidate interest. TalentScout AI automates the full pipeline:

1. **Parse** a Job Description into structured requirements
2. **Match** candidates from a talent pool against those requirements
3. **Engage** each candidate via a simulated 4-turn AI conversation (streamed live)
4. **Rank** the shortlist using a weighted combination of Match Score and Interest Score

---

## Features

- **JD Parsing** — LLM extracts role, required/preferred skills, experience, and must-haves from free-text input
- **Candidate Matching** — Rule-based scoring across 5 dimensions with explainability chips (skill matches / gaps)
- **Score Explanation** — LLM narrates why a candidate received their Match or Interest score in plain English (results cached per candidate)
- **Streaming Conversation** — SSE-streamed 4-turn recruiter ↔ candidate conversation with live token output
- **Interest Score Analysis** — 4 signals extracted: Enthusiasm, Availability, Compensation Fit, Engagement Quality
- **Ranked Shortlist** — Final Score = 0.6 × Match + 0.4 × Interest, with full breakdown
- **Outreach Email Drafts** — LLM-generated personalised outreach email per shortlisted candidate
- **Interview Questions** — LLM-generated role-specific interview questions tailored to each candidate's profile
- **Candidate Comparison** — Side-by-side comparison of up to 3 candidates across all scoring dimensions
- **Analytics Dashboard** — Score distribution charts across the matched candidate pool
- **CSV Export** — One-click export of the full shortlist
- **SQLite Persistence** — Session state survives server restarts (parsed JD, match results, conversations)
- **Provider Abstraction** — Swap between Ollama (local, free) and Google Vertex AI (Gemini) via `.env`

---
## Demo Video

> 📹 [Watch the walkthrough here](https://www.loom.com/share/826f9907cae14cd6a5b08b376ffb39f8)
---

## Quick Start

### Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Ollama | Latest | [ollama.com](https://ollama.com) |

### 1. Clone the Repository

```bash
git clone https://github.com/sunny-rout/ai-talent-scouting.git
cd ai-talent-scouting
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
# Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` for your setup:

```env
# For Ollama (default, free, local)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3          # or: qwen2.5, mistral, etc.

# For Google Vertex AI (optional)
# LLM_PROVIDER=vertex
# VERTEX_PROJECT=your-gcp-project-id
# VERTEX_LOCATION=us-central1
# VERTEX_MODEL=gemini-1.5-pro
```

### 5. Pull an Ollama Model

```bash
# Verify Ollama is running
curl http://localhost:11434
# -> "Ollama is running"

# Pull a model (choose one)
ollama pull llama3       # ~4.7 GB — solid general purpose
ollama pull qwen2.5      # ~4.7 GB — strong instruction following
ollama pull mistral      # ~4.1 GB — fast on CPU
```

### 6. Run the App

```bash
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Project Structure

```
ai-talent-scouting/
│
├── main.py                        # FastAPI app bootstrap, lifespan, core UI routes
├── requirements.txt
├── .env.example
│
├── data/
│   ├── candidates.json            # 18 mock candidates (SWE x6, DS x6, PM x6)
│   └── talent_scout.db            # SQLite database (auto-created on first run)
│
├── app/
│   ├── config.py                  # Reads .env settings
│   ├── models.py                  # Pydantic data models
│   ├── state.py                   # AppState — in-memory session + DB persistence
│   ├── jd_parser.py               # LLM-based JD → structured JSON
│   ├── matcher.py                 # Rule-based candidate scoring
│   ├── conversation.py            # LLM conversation simulation + interest scoring
│   ├── email_draft.py             # LLM outreach email generation
│   ├── interview_questions.py     # LLM interview question generation
│   ├── explain_score.py           # LLM score explanation
│   ├── analytics.py               # Analytics data computation
│   │
│   ├── db/
│   │   ├── base.py                # Abstract BaseDB interface
│   │   └── sqlite_db.py           # SQLite implementation (WAL mode)
│   │
│   ├── llm/
│   │   ├── base.py                # Abstract LLMProvider interface
│   │   ├── ollama_provider.py     # Ollama REST API implementation
│   │   └── vertex_provider.py     # Google Vertex AI implementation
│   │
│   └── routes/
│       ├── candidates.py          # Candidate notes endpoints
│       ├── shortlist.py           # Shortlist add/remove endpoints
│       ├── conversation.py        # Streaming + legacy conversation endpoints
│       ├── generate.py            # Email and interview question generation
│       ├── analytics.py           # Analytics dashboard route
│       └── export.py              # CSV export and session reset
│
└── templates/
    ├── base.html                  # Shared layout, nav, global CSS
    ├── index.html                 # JD input page
    ├── candidates.html            # Candidate match results grid
    ├── conversation.html          # Streaming chat simulation + interest scoring
    ├── shortlist.html             # Ranked shortlist + CSV export
    ├── analytics.html             # Analytics dashboard
    └── architecture.html          # Architecture diagram page
```

---

## Architecture

```
+-----------------------------------------------------------------+
|                       TalentScout AI                            |
|                                                                 |
|   Recruiter                                                     |
|      |                                                          |
|      v  Paste Job Description                                   |
|  +-----------------------------+                                |
|  |      JD Parser (LLM)        |  <- Single LLM call (temp=0.2)|
|  |  Extracts structured JSON:  |                                |
|  |  role_type, required_skills,|                                |
|  |  preferred_skills,          |                                |
|  |  years_experience,          |                                |
|  |  must_haves, salary_range   |                                |
|  +-------------+--------------+                                |
|                |  ParsedJD                                      |
|                v                                                |
|  +-----------------------------+                                |
|  |    Candidate Matcher        |  <- Rule-based (no LLM)        |
|  |  Scores 18 candidates on:   |                                |
|  |  * Required Skills   (40pt) |                                |
|  |  * Preferred Skills  (15pt) |                                |
|  |  * Experience        (20pt) |                                |
|  |  * Role Fit          (10pt) |                                |
|  |  * Education         (10pt) |                                |
|  |  * Must-Haves bonus   (5pt) |                                |
|  +-------------+--------------+                                |
|                |  List[MatchResult] sorted desc                 |
|                v                                                |
|  +-----------------------------+                                |
|  |  Conversational Outreach    |  <- SSE streaming LLM call     |
|  |  4 turns (R->C->R->C)       |     live token output          |
|  |  Interest Signal Scoring:   |                                |
|  |  * Enthusiasm        (/25)  |                                |
|  |  * Availability      (/25)  |                                |
|  |  * Compensation Fit  (/25)  |                                |
|  |  * Engagement        (/25)  |                                |
|  +-------------+--------------+                                |
|                v                                                |
|  +-----------------------------+                                |
|  |      Final Ranking          |                                |
|  |  Final Score =              |                                |
|  |   0.6 x Match Score         |                                |
|  |  +0.4 x Interest Score      |                                |
|  |  Sorted shortlist -> CSV    |                                |
|  +-----------------------------+                                |
|                                                                 |
|  Persistence: SQLite (WAL) — survives restarts                  |
|                                                                 |
|  LLM Provider (swappable via .env)                              |
|  +-----------------+  +------------------------+               |
|  | OllamaProvider  |  |   VertexProvider        |               |
|  | localhost:11434 |  |  Gemini 1.5 Pro / GCP   |               |
|  +-----------------+  +------------------------+               |
+-----------------------------------------------------------------+
```

### Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **Web Framework** | FastAPI | Async-ready, auto docs, Pydantic validation |
| **Templating** | Jinja2 | Server-side rendering, no JS framework dependency |
| **Styling** | Tailwind CSS (CDN) | Utility-first, no build step |
| **LLM (local)** | Ollama | Free, offline, supports llama3/qwen2.5/mistral |
| **LLM (cloud)** | Google Vertex AI | Production-grade Gemini fallback |
| **Streaming** | Server-Sent Events (SSE) | Real-time token streaming to browser |
| **Persistence** | SQLite (WAL mode) | Zero-dependency, survives restarts |

---

## Scoring Logic

### Match Score (0–100)

Computed with rule-based logic — no LLM, fast and deterministic.

| Dimension | Points | Logic |
|---|---|---|
| Required Skills | 40 | `(matched_required / total_required) × 40` |
| Preferred Skills | 15 | `(matched_preferred / total_preferred) × 15` |
| Experience | 20 | Full 20 if meets requirement; −3 pts per missing year |
| Role Fit | 10 | 10 if role type in title; 5 if partial; 0 otherwise |
| Education | 10 | 10 if B.Tech/M.Tech/MBA/MS/PhD detected |
| Must-Haves | 5 | `(matched_must_haves / total_must_haves) × 5` |

Skill matching uses fuzzy normalization — strips spaces, hyphens, and case. "Node.js" matches "nodejs", "REST API" matches "rest api".

### Interest Score (0–100)

Extracted by LLM after the 4-turn conversation simulation:

| Signal | Points | What it measures |
|---|---|---|
| Enthusiasm | 0–25 | Positive language, excitement, proactive questions |
| Availability | 0–25 | Notice period length, flexibility, start date urgency |
| Compensation Fit | 0–25 | Salary expectations vs. offered range alignment |
| Engagement Quality | 0–25 | Depth of responses, questions asked, responsiveness |

### Final Score

```
Final Score = 0.6 × Match Score + 0.4 × Interest Score
```

Match Score is objective and verifiable (higher weight). Interest Score is conversational and inferential — the critical differentiator when two candidates have similar match scores.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home — JD input form |
| `POST` | `/parse-jd` | Parse JD, run matching, render candidates |
| `GET` | `/candidates` | View ranked candidate grid |
| `GET` | `/engage/{id}` | Candidate profile + engagement page |
| `POST` | `/stream-conversation/{id}` | SSE streaming conversation |
| `POST` | `/run-conversation/{id}` | Legacy non-streaming conversation (JSON) |
| `POST` | `/shortlist/{id}` | Add candidate to shortlist |
| `DELETE` | `/shortlist/{id}` | Remove candidate from shortlist |
| `GET` | `/shortlist` | View final ranked shortlist |
| `POST` | `/generate/email/{id}` | Generate personalised outreach email |
| `POST` | `/generate/questions/{id}` | Generate interview questions |
| `POST` | `/explain-score` | LLM explanation of a candidate's score |
| `GET` | `/analytics` | Analytics dashboard |
| `GET` | `/export-csv` | Download shortlist as CSV |
| `GET` | `/reset` | Clear session state |
| `GET` | `/health/llm` | LLM provider health check |
| `GET` | `/architecture` | Architecture diagram page |

---

## Adding Candidates

Edit `data/candidates.json`. Each entry schema:

```json
{
  "id": "unique_id",
  "name": "Full Name",
  "title": "Job Title",
  "company": "Current Company",
  "location": "City, Country",
  "years_experience": 5,
  "skills": ["Python", "FastAPI", "Docker"],
  "education": "B.Tech CSE, University Name",
  "bio": "Professional summary paragraph.",
  "expected_salary": "20-25 LPA",
  "notice_period": "30 days",
  "personality": "enthusiastic"
}
```

Valid personality values: `enthusiastic` · `passive` · `lukewarm` · `focused`

---

## Switching to Vertex AI

1. Enable Vertex AI API in your GCP project
2. Authenticate: `gcloud auth application-default login`
3. Install SDK: `pip install google-cloud-aiplatform`
4. Update `.env`:

```env
LLM_PROVIDER=vertex
VERTEX_PROJECT=your-project-id
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-1.5-pro
```

5. Restart the server — no code changes needed.

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `vertex` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Model from `ollama list` |
| `VERTEX_PROJECT` | _(empty)_ | GCP Project ID |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI region |
| `VERTEX_MODEL` | `gemini-1.5-pro` | Gemini model name |

---

## License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">
Built with FastAPI + Ollama · v1.1
</div>
