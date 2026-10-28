"""Tests for Groq LLM provider.

Tests use mocked HTTP responses to avoid real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from coglayer.core.protocols import LLMRequest
from coglayer.providers.groq import GroqProvider


@patch("coglayer.providers.groq.httpx.post")
def test_groq_provider_success(mock_post: MagicMock) -> None:
    """Groq provider successfully calls the API and returns response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Test response"}}]}
    mock_post.return_value = mock_response

    provider = GroqProvider(api_key="test_key", model="llama-3.3-70b-versatile")
    request = LLMRequest(prompt="Test prompt")

    response = provider.complete(request)

    assert response.text == "Test response"
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args.kwargs["json"]["model"] == "llama-3.3-70b-versatile"
    assert call_args.kwargs["json"]["messages"][0]["content"] == "Test prompt"
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer test_key"


@patch("coglayer.providers.groq.httpx.post")
def test_groq_provider_http_error(mock_post: MagicMock) -> None:
    """Groq provider raises httpx.HTTPError on HTTP errors."""
    mock_post.side_effect = httpx.HTTPStatusError(
        "HTTP error",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )

    provider = GroqProvider(api_key="test_key")
    request = LLMRequest(prompt="Test prompt")

    with pytest.raises(httpx.HTTPError):
        provider.complete(request)


@patch("coglayer.providers.groq.httpx.post")
def test_groq_provider_timeout(mock_post: MagicMock) -> None:
    """Groq provider raises timeout error on request timeout."""
    mock_post.side_effect = httpx.TimeoutException("Request timed out")

    provider = GroqProvider(api_key="test_key", timeout=5.0)
    request = LLMRequest(prompt="Test prompt")

    with pytest.raises(httpx.TimeoutException):
        provider.complete(request)


def test_groq_provider_default_model() -> None:
    """Groq provider uses default model when not specified."""
    provider = GroqProvider(api_key="test_key")
    assert provider._model == "llama-3.3-70b-versatile"


def test_groq_provider_custom_model() -> None:
    """Groq provider uses custom model when specified."""
    provider = GroqProvider(api_key="test_key", model="llama-3.1-8b")
    assert provider._model == "llama-3.1-8b"


def test_groq_provider_custom_timeout() -> None:
    """Groq provider uses custom timeout when specified."""
    provider = GroqProvider(api_key="test_key", timeout=60.0)
    assert provider._timeout == 60.0


@patch("coglayer.providers.groq.httpx.post")
def test_groq_provider_uses_configured_model(mock_post: MagicMock) -> None:
    """Groq provider uses the configured model (openai/gpt-oss-20b)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Test response"}}]}
    mock_post.return_value = mock_response

    provider = GroqProvider(api_key="test_key", model="openai/gpt-oss-20b")
    request = LLMRequest(prompt="Test prompt")

    response = provider.complete(request)

    assert response.text == "Test response"
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    # Verify the configured model is sent in the request
    assert call_args.kwargs["json"]["model"] == "openai/gpt-oss-20b"
