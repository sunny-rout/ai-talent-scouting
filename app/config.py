import os
from dotenv import load_dotenv
load_dotenv()

# ── Active provider ───────────────────────────────────────────────────────────
# Accepted values: ollama | gemini | vertex | openai | auto
# "auto" tries providers in order: ollama → gemini → openai → vertex
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "llama3")

# ── Google AI Studio (Gemini API key) ─────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY",  "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL",    "gemini-2.0-flash")

# ── Google Vertex AI ──────────────────────────────────────────────────────────
VERTEX_PROJECT  = os.getenv("VERTEX_PROJECT",  "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_MODEL    = os.getenv("VERTEX_MODEL",    "gemini-2.0-flash")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY",  "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL",    "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")  # optional: override for proxies

# ── Default model per provider (used when model not specified explicitly) ─────
_DEFAULT_MODELS: dict[str, str] = {
    "ollama":  OLLAMA_MODEL,
    "gemini":  GEMINI_MODEL,
    "vertex":  VERTEX_MODEL,
    "openai":  OPENAI_MODEL,
}

def default_model_for(provider: str) -> str:
    return _DEFAULT_MODELS.get(provider.lower(), OLLAMA_MODEL)
