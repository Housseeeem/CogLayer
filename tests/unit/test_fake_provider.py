"""Unit tests for ``FakeProvider``.

Validates the determinism and canned-response behaviour required by R-008.4.
"""

from __future__ import annotations

import hashlib

import pytest

from coglayer.core.protocols import LLMRequest
from coglayer.providers.fake import FakeProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_prefix(prompt: str) -> str:
    """Return the 8-char SHA-256 hex prefix used by FakeProvider."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:8]


def _make_request(prompt: str) -> LLMRequest:
    return LLMRequest(prompt=prompt)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same prompt + same seed must always produce the same response (R-008.4)."""

    def test_same_prompt_returns_same_text(self) -> None:
        provider = FakeProvider(seed=42)
        prompt = "Explain working memory."

        first = provider.complete(_make_request(prompt))
        second = provider.complete(_make_request(prompt))

        assert first.text == second.text

    def test_same_prompt_same_seed_across_instances_returns_same_text(self) -> None:
        """Two independent FakeProvider instances with the same seed are equivalent."""
        prompt = "Tell me about cognitive load."
        a = FakeProvider(seed=99).complete(_make_request(prompt))
        b = FakeProvider(seed=99).complete(_make_request(prompt))

        assert a.text == b.text


class TestDifferentPrompts:
    """Different prompts must return different text (no collision on distinct inputs)."""

    def test_different_prompts_return_different_text(self) -> None:
        provider = FakeProvider(seed=42)

        response_a = provider.complete(_make_request("Hello world"))
        response_b = provider.complete(_make_request("Goodbye world"))

        assert response_a.text != response_b.text


class TestCannedOverride:
    """When a canned mapping matches the prompt hash prefix, it must be returned."""

    def test_canned_response_returned_for_matching_hash(self) -> None:
        prompt = "What is attention span?"
        prefix = _hash_prefix(prompt)
        canned_text = "Attention span is how long you can focus."

        provider = FakeProvider(canned={prefix: canned_text})
        response = provider.complete(_make_request(prompt))

        assert response.text == canned_text

    def test_canned_response_not_returned_for_non_matching_hash(self) -> None:
        """A canned entry for a different prompt must not affect an unrelated prompt."""
        other_prompt = "What is memory?"
        target_prompt = "What is attention span?"
        canned_text = "Memory is the ability to recall information."

        provider = FakeProvider(canned={_hash_prefix(other_prompt): canned_text})
        response = provider.complete(_make_request(target_prompt))

        # Should fall through to fallback, not return the canned text
        assert response.text != canned_text

    def test_canned_takes_priority_over_fallback(self) -> None:
        """Canned response must override the seed-based fallback."""
        prompt = "Describe inhibitory control."
        prefix = _hash_prefix(prompt)
        canned_text = "Inhibitory control is the ability to suppress impulses."

        provider = FakeProvider(seed=42, canned={prefix: canned_text})
        response = provider.complete(_make_request(prompt))

        assert response.text == canned_text
        # Confirm the fallback format is not present
        assert not response.text.startswith("[FakeProvider")


class TestDifferentSeeds:
    """Different seeds must produce different fallback text for the same prompt."""

    def test_different_seeds_produce_different_fallback_text(self) -> None:
        prompt = "Evaluate executive function."

        response_seed_1 = FakeProvider(seed=1).complete(_make_request(prompt))
        response_seed_2 = FakeProvider(seed=2).complete(_make_request(prompt))

        assert response_seed_1.text != response_seed_2.text

    def test_seed_zero_and_seed_42_differ(self) -> None:
        prompt = "Describe working memory capacity."

        r0 = FakeProvider(seed=0).complete(_make_request(prompt))
        r42 = FakeProvider(seed=42).complete(_make_request(prompt))

        assert r0.text != r42.text


class TestFallbackFormat:
    """Fallback responses must follow the '[FakeProvider seed=N] ...' format."""

    def test_fallback_starts_with_expected_format(self) -> None:
        seed = 7
        provider = FakeProvider(seed=seed)
        # Use a prompt with no canned entry
        response = provider.complete(_make_request("Some uncanned prompt"))

        assert response.text.startswith(f"[FakeProvider seed={seed}]")

    def test_fallback_includes_prompt_prefix(self) -> None:
        """The fallback text must embed the first 40 chars of the prompt."""
        prompt = "A" * 60  # longer than the 40-char truncation
        provider = FakeProvider(seed=42)
        response = provider.complete(_make_request(prompt))

        expected_fragment = prompt[:40]
        assert expected_fragment in response.text

    def test_fallback_truncates_long_prompt_to_40_chars(self) -> None:
        """Only the first 40 characters of the prompt appear in the fallback."""
        prompt = "X" * 80
        provider = FakeProvider(seed=42)
        response = provider.complete(_make_request(prompt))

        # The 41st character must not appear after the seed prefix
        assert prompt[41] * 10 not in response.text or response.text.count("X") <= 40

    @pytest.mark.parametrize("seed", [0, 1, 42, 100, 999])
    def test_fallback_format_for_various_seeds(self, seed: int) -> None:
        provider = FakeProvider(seed=seed)
        response = provider.complete(_make_request("Parametrized test prompt"))

        assert response.text.startswith(f"[FakeProvider seed={seed}]")
