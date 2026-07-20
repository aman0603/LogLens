"""Provider-agnostic LLM client.

Default backend: Google Gemini accessed through its OpenAI-compatible REST API.
Everything (base URL, model, API key) is supplied via environment variables so
no provider is hardcoded and the backend can be swapped without code changes.
"""

import os
from typing import List, Dict, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - imported lazily so tests can mock
    OpenAI = None


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or ""
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.model = model or os.getenv("LLM_MODEL", "gemini-3.1-flash-lite")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(temperature)))
        self._client = None

    def _get_client(self):
        if OpenAI is None:
            raise RuntimeError(
                "openai package is required for the LLM client. Install it via requirements.txt."
            )
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        """Send chat messages and return the assistant's text content."""
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature if temperature is None else temperature,
        )
        return resp.choices[0].message.content or ""
