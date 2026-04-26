"""
B4 — Custom LLM exception hierarchy.

Every error a recruiter can ever trigger maps to one of these classes.
The FastAPI exception handlers in main.py convert them to JSON with a
`friendly_message` and an actionable `hint`.
"""


class LLMError(Exception):
    """Base class — all LLM errors inherit from here."""

    # Default human-readable fields. Subclasses override them.
    friendly_message: str = "The AI model returned an unexpected error."
    hint: str             = "Try again in a moment."
    http_status: int      = 500

    def __init__(self, detail: str = "", **kwargs):
        super().__init__(detail or self.friendly_message)
        self.detail = detail or self.friendly_message
        # Allow callers to override defaults per-instance
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        return {
            "error_type"      : self.__class__.__name__,
            "friendly_message": self.friendly_message,
            "detail"          : self.detail,
            "hint"            : self.hint,
        }


class LLMConnectionError(LLMError):
    """Model server is unreachable (Ollama not running / network down)."""
    friendly_message = "Cannot reach the AI model server."
    hint             = "Make sure Ollama is running: `ollama serve`"
    http_status      = 503


class LLMTimeoutError(LLMError):
    """Model took too long to respond."""
    friendly_message = "The AI model timed out."
    hint             = "The model may be loading. Wait a moment, then try again."
    http_status      = 504


class LLMAuthError(LLMError):
    """Invalid or missing API key (OpenAI)."""
    friendly_message = "Invalid AI provider API key."
    hint             = "Check your OPENAI_API_KEY in .env and restart the server."
    http_status      = 401


class LLMRateLimitError(LLMError):
    """Too many requests — provider quota exceeded."""
    friendly_message = "AI provider rate limit reached."
    hint             = "Wait a minute before sending more requests, or check your usage quota."
    http_status      = 429


class LLMParseError(LLMError):
    """LLM returned a response that could not be parsed as valid JSON/structure."""
    friendly_message = "The AI model returned an unreadable response."
    hint             = "This sometimes happens with smaller models. Try a different model or retry."
    http_status      = 422


class LLMModelNotFoundError(LLMError):
    """Requested model is not installed / not available."""
    friendly_message = "The requested AI model is not installed."
    hint             = "Run `ollama pull <model-name>` to install it, then restart."
    http_status      = 404
