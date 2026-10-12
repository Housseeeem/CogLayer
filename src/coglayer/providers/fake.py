"""Deterministic fake LLM provider for testing and development.

``FakeProvider`` satisfies the ``LLMProvider`` Protocol without making any
network calls. Responses are fully deterministic: the same prompt and seed
always produce the same output, making tests reproducible across runs.

Requirements: R-008.4
"""

from __future__ import annotations

import hashlib

from coglayer.core.protocols import LLMProvider, LLMRequest, LLMResponse

__all__ = ["FakeProvider"]


class FakeProvider:
    """Deterministic LLM provider for tests and offline development.

    Responses are keyed on the first 8 hex characters of the SHA-256 hash of
    the prompt, combined with a configurable integer seed.  Callers can
    optionally pre-register canned responses by their 8-char hash prefix.

    Requirements: R-008.4

    Args:
        seed: Integer seed that is embedded in the fallback response text.
            Changing the seed changes the fallback text for every prompt,
            making it easy to verify which provider instance produced a
            response.
        canned: Mapping of 8-char prompt-hash prefixes to response strings.
            When the hash prefix of the incoming prompt matches a key, that
            canned string is returned verbatim.  Pass ``None`` (the default)
            to start with an empty mapping.

    Example::

        provider = FakeProvider(seed=7)
        response = provider.complete(LLMRequest(prompt="Hello"))
        assert response.text.startswith("[FakeProvider seed=7]")

        # With canned response:
        prefix = hashlib.sha256(b"Hello").hexdigest()[:8]
        provider = FakeProvider(canned={prefix: "Hi there!"})
        response = provider.complete(LLMRequest(prompt="Hello"))
        assert response.text == "Hi there!"
    """

    def __init__(
        self,
        seed: int = 42,
        canned: dict[str, str] | None = None,
    ) -> None:
        self._seed = seed
        # Use None default to avoid mutable default argument pitfall; initialise
        # an empty dict when no canned responses are provided.
        self._canned: dict[str, str] = {} if canned is None else canned

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic response for the given prompt.

        Lookup order:
        1. If the 8-char SHA-256 hex prefix of the prompt matches a key in
           ``self._canned``, return the canned string.
        2. Otherwise, return a fallback string embedding the seed and the
           first 40 characters of the prompt.

        Args:
            request: The LLM request.  Only ``request.prompt`` is used.

        Returns:
            A deterministic ``LLMResponse``.
        """
        prompt_hash_prefix = hashlib.sha256(request.prompt.encode()).hexdigest()[:8]

        if prompt_hash_prefix in self._canned:
            return LLMResponse(text=self._canned[prompt_hash_prefix])

        fallback = f"[FakeProvider seed={self._seed}] {request.prompt[:40]}"
        return LLMResponse(text=fallback)


# Verify structural compatibility with LLMProvider at import time (no runtime
# overhead — isinstance with a runtime_checkable Protocol is a static duck-type
# check only).
assert isinstance(
    FakeProvider(), LLMProvider
), "FakeProvider does not satisfy the LLMProvider Protocol"
