"""Groq LLM provider for CogLayer.

Implements the LLMProvider protocol using Groq's OpenAI-compatible API.
Uses the existing httpx dependency for HTTP requests.

Requirements: Provider abstraction (R-008.4)
"""

from __future__ import annotations

import logging

import httpx

from coglayer.core.protocols import LLMProvider, LLMRequest, LLMResponse

__all__ = ["GroqProvider"]

_log = logging.getLogger(__name__)

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_TIMEOUT = 30.0


class GroqProvider:
    """Groq LLM provider using OpenAI-compatible API.

    Parameters
    ----------
    api_key :
        Groq API key. Must be configured via environment variable.
    model :
        Model identifier for Groq API. Defaults to llama-3.3-70b-versatile.
    timeout :
        Request timeout in seconds. Defaults to 30.0.
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Groq.

        Args:
            request: The prompt to send.

        Returns:
            The model's text response.

        Raises:
            httpx.HTTPError: On network or API errors.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        response = httpx.post(
            _GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(text=content)


# Verify structural compatibility with LLMProvider at import time
assert isinstance(GroqProvider(api_key="test"), LLMProvider), (
    "GroqProvider does not satisfy the LLMProvider Protocol"
)
