import os
from dotenv import load_dotenv
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "llama3")
VERTEX_PROJECT  = os.getenv("VERTEX_PROJECT",  "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_MODEL    = os.getenv("VERTEX_MODEL",    "gemini-2.5-pro")
LLM_PROVIDER    = os.getenv("LLM_PROVIDER",    "ollama")