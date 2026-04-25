<div align="center">

# 🎯 TalentScout AI

### AI-Powered Talent Scouting & Engagement Agent

[
[
[
[
[

**Takes a Job Description as input → discovers matching candidates → engages them conversationally → outputs a ranked shortlist scored on Match Score + Interest Score.**

[Demo Video](#demo-video) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Scoring Logic](#scoring-logic)

</div>

***

## 📌 Problem Statement

Recruiters spend hours sifting through profiles and chasing candidate interest. TalentScout AI automates the full pipeline:

1. **Parse** a Job Description into structured requirements
2. **Match** candidates from a talent pool against those requirements
3. **Engage** each candidate via a simulated 4-turn AI conversation
4. **Rank** the shortlist using a weighted combination of Match Score and Interest Score

***

## ✨ Features

- **JD Parsing** — LLM extracts role, required/preferred skills, experience, must-haves from free-text JD
- **Candidate Matching** — Rule-based scoring across 5 dimensions with explainability chips (skill matches ✓ / gaps ✗)
- **Conversational Outreach** — LLM simulates a 4-turn recruiter ↔ candidate conversation; candidate personality varies (enthusiastic / passive / lukewarm / focused)
- **Interest Score Analysis** — 4 signals extracted: Enthusiasm, Availability, Compensation Fit, Engagement Quality
- **Ranked Shortlist** — Final Score = 0.6 × Match + 0.4 × Interest, with full breakdown
- **CSV Export** — One-click export of the entire shortlist
- **Multi-role support** — Software Engineer, Data Scientist, Product Manager
- **Provider abstraction** — Swap between Ollama (local, free) and Google Vertex AI (Gemini) via `.env`

***

## 🎬 Demo Video

> 📹 [Watch the 5-minute walkthrough here](#) ← _add Loom link_

**What the demo covers:**
1. Loading the Software Engineer sample JD
2. Watching the JD parser extract structured requirements
3. Browsing the ranked candidate grid with explainability chips
4. Running a 4-turn simulated conversation for the top candidate
5. Adding candidates to the shortlist and exporting CSV

***

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Ollama | Latest | [ollama.com](https://ollama.com) |
| Git | Any | [git-scm.com](https://git-scm.com) |

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

# List installed models
ollama list
```

### 6. Run the App

```bash
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

***

## 📁 Project Structure

```
ai-talent-scouting/
│
├── main.py                        # FastAPI app — all routes
├── requirements.txt
├── .env.example                   # Environment variable template
│
├── data/
│   └── candidates.json            # 18 mock candidates (SWE x6, DS x6, PM x6)
│
├── app/
│   ├── config.py                  # Reads .env settings
│   ├── models.py                  # Pydantic data models
│   ├── jd_parser.py               # LLM-based JD -> structured JSON
│   ├── matcher.py                 # Rule-based candidate scoring
│   ├── conversation.py            # LLM conversation simulation
│   └── llm/
│       ├── base.py                # Abstract LLMProvider interface
│       ├── ollama_provider.py     # Ollama REST API implementation
│       └── vertex_provider.py     # Google Vertex AI implementation
│
├── templates/
│   ├── base.html                  # Shared layout, nav, global CSS
│   ├── index.html                 # JD input page
│   ├── candidates.html            # Candidate match results grid
│   ├── conversation.html          # Chat simulation + interest scoring
│   └── shortlist.html             # Ranked shortlist + CSV export
│
└── static/
    └── js/app.js
```

***

## 🏗️ Architecture

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
|  |  Match Score = total / 100  |                                |
|  +-------------+--------------+                                |
|                |  List[MatchResult] sorted desc                 |
|                v                                                |
|  +-----------------------------+                                |
|  |  Conversational Outreach    |  <- LLM call per candidate     |
|  |  LLM role-plays both sides: |     (temp=0.75, JSON output)   |
|  |  4 turns (R->C->R->C)       |                                |
|  |  Personalities: enthusiastic|                                |
|  |  / passive / lukewarm       |                                |
|  |                             |                                |
|  |  Interest Signal Scoring:   |                                |
|  |  * Enthusiasm        (/25)  |                                |
|  |  * Availability      (/25)  |                                |
|  |  * Compensation Fit  (/25)  |                                |
|  |  * Engagement        (/25)  |                                |
|  |  Interest Score = sum / 100 |                                |
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
| **Templating** | Jinja2 | Server-side rendering, zero JS framework dependency |
| **Styling** | Tailwind CSS (CDN) | Utility-first, no build step needed |
| **LLM (local)** | Ollama | Free, offline, supports llama3/qwen2.5 |
| **LLM (cloud)** | Google Vertex AI | Production-grade Gemini fallback |
| **Data** | JSON file | Zero database setup for prototype |
| **State** | In-memory dict | Simple, fast, demo-safe |

***

## 📊 Scoring Logic

### Match Score (0–100)

Computed with rule-based logic — no LLM needed. Fast and deterministic.

| Dimension | Points | Logic |
|---|---|---|
| Required Skills | 40 | `(matched_required / total_required) x 40` |
| Preferred Skills | 15 | `(matched_preferred / total_preferred) x 15` |
| Experience | 20 | Full 20 if meets requirement; -3pts per missing year |
| Role Fit | 10 | 10 if role type in title; 5 if partial; 0 otherwise |
| Education | 10 | 10 if B.Tech/M.Tech/MBA/MS/PhD detected |
| Must-Haves | 5 | `(matched_must_haves / total_must_haves) x 5` |

**Skill matching uses fuzzy normalization** — strips spaces, hyphens, and case.
So "Node.js" matches "nodejs", "REST API" matches "rest api".

**Experience scoring:**

```python
def experience_score(candidate_years, required_years):
    diff = candidate_years - required_years
    if diff >= 0:
        return min(20.0, 20.0 - diff * 0.5)   # slight over-qualification penalty
    else:
        return max(0.0, 20.0 + diff * 3.0)    # -3pts per missing year
```

### Interest Score (0–100)

Extracted by the LLM after a 4-turn conversation simulation:

| Signal | Points | What it measures |
|---|---|---|
| Enthusiasm | 0–25 | Positive language, excitement, proactive questions |
| Availability | 0–25 | Notice period length, flexibility, start date urgency |
| Compensation Fit | 0–25 | Salary expectations vs. offered range alignment |
| Engagement Quality | 0–25 | Depth of responses, questions asked, responsiveness |

### Final Score

```
Final Score = 0.6 x Match Score + 0.4 x Interest Score
```

**Why 60/40?**
Match Score is objective and verifiable (higher weight).
Interest Score is conversational and inferential — critical differentiator
when two candidates have similar match scores (lower weight but essential).

***

## 🗂️ Sample Input / Output

### Sample Input — Job Description

```
Senior Backend Software Engineer – Bangalore

We are a fast-growing fintech startup looking for a Senior Backend Engineer.

Requirements:
- 4+ years of backend software engineering experience
- Proficiency in Python (FastAPI or Django preferred)
- Strong knowledge of PostgreSQL and Redis
- Experience with Docker and Kubernetes

Preferred:
- Experience with Kafka or RabbitMQ
- Knowledge of GraphQL

Compensation: 25–40 LPA.
```

### Sample Output — Parsed JD (JSON)

```json
{
  "role": "Senior Backend Software Engineer",
  "role_type": "Software Engineer",
  "required_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
  "preferred_skills": ["Kafka", "RabbitMQ", "GraphQL"],
  "years_experience": 4,
  "must_haves": ["Python", "PostgreSQL", "Docker"],
  "salary_range": "25-40 LPA"
}
```

### Sample Output — Top Match Result

```json
{
  "candidate": { "name": "Arjun Sharma", "title": "Senior Software Engineer" },
  "match_score": 84.5,
  "skill_matches": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
  "skill_gaps": ["Kubernetes"],
  "score_breakdown": {
    "required_skills": 34.3,
    "preferred_skills": 0.0,
    "experience": 18.5,
    "role_fit": 10.0,
    "education": 10.0,
    "must_haves": 5.0
  }
}
```

### Sample Output — Conversation Simulation

```
Recruiter Agent:
Hi Arjun! I came across your profile and noticed your strong background
in Python and FastAPI. We're hiring a Senior Backend Engineer at a
fast-growing fintech — would you be open to a chat?

Arjun Sharma:
Thanks for reaching out! I'm definitely open to hearing about exciting
opportunities. What does the tech stack look like and what's the team size?

Recruiter Agent:
The stack is Python/FastAPI, PostgreSQL, Redis, Docker, and Kubernetes on
AWS. Team is about 12 engineers. Your experience looks like a strong fit.
What's your current notice period and expected CTC?

Arjun Sharma:
I'm on a 30-day notice and targeting around 30-34 LPA. The stack sounds
exciting. I'd love to know more about the product domain and growth path.
```

### Sample Output — Interest Score

```json
{
  "enthusiasm": 22, "availability": 20,
  "compensation_fit": 18, "engagement": 21,
  "total": 81.0,
  "summary": "Strong enthusiasm with proactive questions; salary expectations within range."
}
```

### Sample Output — Final Shortlist CSV

```
Rank,Name,Title,Company,Match Score,Interest Score,Final Score,Skill Matches,Skill Gaps,Notice Period,Expected CTC
1,Arjun Sharma,Senior Software Engineer,Infosys,84.5,81.0,83.1,"Python,FastAPI,PostgreSQL",Kubernetes,30 days,28-32 LPA
2,Sneha Iyer,Software Dev Engineer II,Wipro,76.2,74.0,75.3,"Python,Docker,Redis",Kubernetes,60 days,22-26 LPA
3,Priya Nair,Software Engineer II,TCS,71.8,68.5,70.5,"Python,PostgreSQL",FastAPI,45 days,20-25 LPA
```

***

## 🔌 API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home — JD input form |
| `POST` | `/parse-jd` | Parse JD, run matching, redirect to candidates |
| `GET` | `/candidates` | View ranked candidate grid |
| `GET` | `/engage/{id}` | Candidate profile + engagement page |
| `POST` | `/run-conversation/{id}` | Run LLM conversation (returns JSON) |
| `POST` | `/shortlist/{id}` | Add candidate to shortlist |
| `DELETE` | `/shortlist/{id}` | Remove from shortlist |
| `GET` | `/shortlist` | View final ranked shortlist |
| `GET` | `/export-csv` | Download shortlist as CSV |
| `GET` | `/reset` | Clear session state |

***

## 🧩 Adding Candidates

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

***

## 🔄 Switching to Vertex AI

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

***

## ⚙️ Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `vertex` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Model from `ollama list` |
| `VERTEX_PROJECT` | _(empty)_ | GCP Project ID |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI region |
| `VERTEX_MODEL` | `gemini-1.5-pro` | Gemini model name |

***

## 🛣️ Roadmap

- [ ] SQLite persistence (survive server restarts)
- [ ] Streaming LLM output (real-time typing effect)
- [ ] Auto-generated interview questions per candidate
- [ ] Personalized outreach email drafts
- [ ] Candidate comparison modal (side-by-side scores)
- [ ] Analytics dashboard (score distribution charts)

***

## 📄 License

MIT License — see [LICENSE](LICENSE)

***

<div align="center">
Built with FastAPI + Ollama · Prototype v1.0
</div>