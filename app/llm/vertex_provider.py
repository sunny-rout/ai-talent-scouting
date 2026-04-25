from typing import List, Dict
from .base import LLMProvider

class VertexProvider(LLMProvider):
    def __init__(self, project: str, location="us-central1", model="gemini-1.5-pro"):
        self.project = project
        self.location = location
        self.model_name = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=self.project, location=self.location)
            self._client = GenerativeModel(self.model_name)
        return self._client

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        from vertexai.generative_models import GenerationConfig
        model = self._get_client()
        prompt = "\n\n".join(
            f"[{m['role'].capitalize()}]: {m['content']}" for m in messages
        )
        cfg = GenerationConfig(temperature=temperature, max_output_tokens=2048)
        return model.generate_content(prompt, generation_config=cfg).text