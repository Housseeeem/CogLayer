"""Tests for CognitiveCoach.

Task 13 acceptance criteria:
  test_ac_coach_lock_per_user          — per-user availability
  test_ac_coach_new_empty_session      — new empty session does not lock
  test_ac_llm_request_no_profile       — LLMRequest has no profile object/trials
  test_ac_forbidden_word_fallback      — forbidden word -> fall back to local text
  test_ac_no_false_positive_technique  — "technique" does not match any forbidden word
  test_ac_no_false_positive_unique     — "unique" does not match any forbidden word
  test_ac_provider_exception_fallback  — provider exception -> fall back to local text
  test_ac_no_ranking_no_global_score   — no ranking or global score in output
  test_ac_disclaimer_present           — disclaimer always present

All expected values are hand-derived.
Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coglayer.coach.coach import (
    FORBIDDEN_WORDS_PATTERN,
    CognitiveCoach,
    validate_llm_reply,
)
from coglayer.core.brain_twin import BrainTwinSignal, BrainTwinState
from coglayer.core.models import (
    CognitiveProfile,
    DataQuality,
    DimensionEstimate,
    TaskResult,
)
from coglayer.core.protocols import LLMRequest, LLMResponse
from coglayer.core.settings import Settings
from coglayer.providers.fake import FakeProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
_COACH = CognitiveCoach()

_DISCLAIMER = "Based on these two tasks only \u2014 not a clinical assessment."


def _settings(threshold: float = 0.8) -> Settings:
    return Settings(completeness_threshold=threshold)


def _result(task_id: str, completeness: float = 1.0) -> TaskResult:
    """Minimal TaskResult with hand-derived valid_trials."""
    valid = round(10 * completeness)
    return TaskResult(
        task_id=task_id,
        task_version="1.0",
        session_id="sess-test",
        user_id="user-test",
        trials=[],
        metrics={},
        signals=[],
        target_dimensions=[],
        data_quality=DataQuality(
            valid_trials=valid,
            total_trials=10,
            completeness=float(valid) / 10.0,
            anomalies=[],
        ),
        uncertainty=None,
    )


def _make_profile(
    user_id: str = "user-test",
    dimensions: dict[str, DimensionEstimate] | None = None,
) -> CognitiveProfile:
    """Build a profile with known dimension estimates for testing."""
    if dimensions is None:
        # Hand-derived: after one update with outcome=0.8, weight=1.0,
        # count=10 on prior Beta(1,1) with lambda=0.98:
        # forgetting: alpha=1+0.98*(1-1)=1, beta=1+0.98*(1-1)=1
        # n_eff = 1.0 * min(10, 20) = 10
        # alpha = 1 + 10*0.8 = 9.0
        # beta = 1 + 10*0.2 = 3.0
        # mean = 9/(9+3) = 0.75
        dimensions = {
            "response_inhibition": DimensionEstimate(
                dimension="response_inhibition",
                mean=0.75,
                lower=0.51,
                upper=0.91,
                n_evidence=1,
                last_update=_TS,
                alpha=9.0,
                beta_param=3.0,
            ),
            "sequential_visual_memory": DimensionEstimate(
                dimension="sequential_visual_memory",
                mean=0.60,
                lower=0.38,
                upper=0.80,
                n_evidence=1,
                last_update=_TS,
                alpha=6.0,
                beta_param=4.0,
            ),
        }
    return CognitiveProfile(
        user_id=user_id,
        dimensions=dimensions,
        evidence_history=[],
        data_quality={
            "response_inhibition": DataQuality(
                valid_trials=10, total_trials=10, completeness=1.0, anomalies=[]
            ),
            "sequential_visual_memory": DataQuality(
                valid_trials=8, total_trials=10, completeness=0.8, anomalies=[]
            ),
        },
        uncertainty={
            "response_inhibition": 0.16,
            "sequential_visual_memory": 0.20,
        },
    )


# ---------------------------------------------------------------------------
# Per-user availability
# ---------------------------------------------------------------------------


def test_ac_coach_lock_per_user() -> None:
    """Coach is locked when no session is complete, available when one is.

    Hand-derived:
      No sessions -> not available (empty list)
      One session with only go_no_go -> engine returns next_task -> not available
      One session with both tasks complete -> engine returns complete -> available
    """
    settings = _settings()

    # No sessions at all
    assert _COACH.is_available("user-test", [], settings) is False

    # One session with only go_no_go done
    incomplete_session = [_result("go_no_go", completeness=1.0)]
    assert _COACH.is_available("user-test", [incomplete_session], settings) is False

    # One session with both tasks done and sufficient
    complete_session = [
        _result("go_no_go", completeness=1.0),
        _result("sequence_span", completeness=1.0),
    ]
    assert _COACH.is_available("user-test", [complete_session], settings) is True


def test_ac_coach_lock() -> None:
    """AC test: coach locked before completion, available after."""
    test_ac_coach_lock_per_user()


def test_ac_coach_new_empty_session() -> None:
    """A new empty session does not lock the coach again.

    Hand-derived:
      Session 1: complete (both tasks, full quality)
      Session 2: empty (no results)
      Engine on session 1 -> complete -> coach available.
      Engine on session 2 -> next_task (go_no_go).
      But availability checks ALL sessions: at least one complete -> True.
    """
    settings = _settings()

    complete_session = [
        _result("go_no_go", completeness=1.0),
        _result("sequence_span", completeness=1.0),
    ]
    empty_session: list[TaskResult] = []

    # Both sessions provided; the coach should still be available
    assert _COACH.is_available("user-test", [complete_session, empty_session], settings) is True


# ---------------------------------------------------------------------------
# LLMRequest must not contain profile or trial data
# ---------------------------------------------------------------------------


def test_ac_llm_request_no_profile() -> None:
    """The LLMRequest sent to the provider must NOT contain the profile object
    or any raw trial data.

    We capture the LLMRequest via a mock provider and verify:
      - No "CognitiveProfile" string
      - No "alpha" or "beta_param" fields
      - No "trials" key
      - No "evidence_history" key
      - The prompt DOES contain the local text (percent range, n_evidence)
    """
    profile = _make_profile()

    captured_requests: list[LLMRequest] = []

    class CapturingProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            captured_requests.append(request)
            return LLMResponse(text="Great job! Keep up the practice.")

    provider = CapturingProvider()
    _COACH.generate_feedback(profile, provider)

    assert len(captured_requests) == 1
    prompt = captured_requests[0].prompt

    # Must NOT contain profile internals
    assert "CognitiveProfile" not in prompt
    assert "beta_param" not in prompt
    assert "evidence_history" not in prompt
    # "alpha" as a model parameter must not appear — check for "alpha="
    assert "alpha=" not in prompt
    # raw trials must never leak
    assert '"trials"' not in prompt

    # Must contain the local summary content
    assert "%" in prompt  # percent range
    assert "Observations:" in prompt
    assert _DISCLAIMER in prompt


# ---------------------------------------------------------------------------
# Forbidden word fallback
# ---------------------------------------------------------------------------


def test_ac_forbidden_word_fallback() -> None:
    """If LLM response contains a forbidden word, fall back to local text.

    Hand-derived: the forbidden word "disorder" appears in the LLM response.
    The coach must return the local text (without the LLM enrichment).
    """
    profile = _make_profile()

    class BadProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(text="You may have a learning disorder. Keep trying!")

    result = _COACH.generate_feedback(profile, BadProvider())

    # Should be the local text, not the LLM response
    assert "disorder" not in result.lower()
    assert _DISCLAIMER in result
    assert "Observations:" in result


def test_ac_no_false_positive_technique() -> None:
    """The word 'technique' must NOT trigger the forbidden word filter.

    Hand-derived: none of the forbidden words (whole-word match) overlap
    with 'technique'. The regex uses \\b word boundaries.
    """
    assert FORBIDDEN_WORDS_PATTERN.search("technique") is None
    assert FORBIDDEN_WORDS_PATTERN.search("Try this technique for improvement.") is None


def test_ac_no_false_positive_unique() -> None:
    """The word 'unique' must NOT trigger the forbidden word filter.

    Hand-derived: 'unique' contains 'iq' as a substring, but the whole-word
    regex (\\b) must not match it.
    """
    assert FORBIDDEN_WORDS_PATTERN.search("unique") is None
    assert FORBIDDEN_WORDS_PATTERN.search("Your unique approach is great.") is None


# ---------------------------------------------------------------------------
# Provider exception fallback
# ---------------------------------------------------------------------------


def test_ac_provider_exception_fallback() -> None:
    """If the provider raises an exception, fall back to local text.

    Hand-derived: provider raises RuntimeError. The coach must catch it,
    log a warning, and return the local text.
    """
    profile = _make_profile()

    class FailingProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            raise RuntimeError("Connection timed out")

    result = _COACH.generate_feedback(profile, FailingProvider())

    # Should be the local text
    assert _DISCLAIMER in result
    assert "Observations:" in result


def test_coach_adds_neutral_context_only_for_flagged_variation() -> None:
    profile = _make_profile()
    flagged = BrainTwinSignal(
        state=BrainTwinState.VARIATION_FLAGGED,
        comparable_observation_count=5,
        flagged_observation_id="session-4|go_no_go|response_inhibition|stable",
    )
    normal = BrainTwinSignal(
        state=BrainTwinState.NO_VARIATION,
        comparable_observation_count=4,
    )
    insufficient = BrainTwinSignal(
        state=BrainTwinState.INSUFFICIENT_DATA,
        comparable_observation_count=2,
    )

    flagged_text = _COACH.generate_feedback(profile, brain_twin_signal=flagged)
    normal_text = _COACH.generate_feedback(profile, brain_twin_signal=normal)
    insufficient_text = _COACH.generate_feedback(profile, brain_twin_signal=insufficient)

    assert "differs from the user's usual reference" in flagged_text
    assert "does not determine its cause" in flagged_text
    assert "differs from the user's usual reference" not in normal_text
    assert "differs from the user's usual reference" not in insufficient_text
    assert "stress" not in flagged_text.lower()
    assert "fatigue" not in flagged_text.lower()
    assert "disorder" not in flagged_text.lower()


def test_coach_keeps_normal_feedback_without_signal() -> None:
    profile = _make_profile()

    result = _COACH.generate_feedback(profile)

    assert "differs from the user's usual reference" not in result
    assert _DISCLAIMER in result


def test_provider_receives_only_neutral_derived_context() -> None:
    profile = _make_profile()
    signal = BrainTwinSignal(
        state=BrainTwinState.VARIATION_FLAGGED,
        comparable_observation_count=5,
        flagged_observation_id="session-4|go_no_go|response_inhibition|stable",
    )
    captured: list[LLMRequest] = []

    class CapturingProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return LLMResponse(text="Keep going and choose what feels useful.")

    _COACH.generate_feedback(profile, CapturingProvider(), brain_twin_signal=signal)

    prompt = captured[0].prompt
    assert "session-4" not in prompt
    assert "VARIATION_FLAGGED" not in prompt
    assert "differs from the user's usual reference" in prompt
    assert "evidence_history" not in prompt


# ---------------------------------------------------------------------------
# No ranking or global score
# ---------------------------------------------------------------------------


def test_ac_no_ranking_no_global_score() -> None:
    """The local text must not rank dimensions or output a global score.

    Hand-derived: patterns like "rank", "ranked", "overall score",
    "global score", "#1", "#2" must not appear in the local text.
    """
    profile = _make_profile()
    local_text = CognitiveCoach._build_local_text(profile)

    ranking_patterns = [
        r"\brank\b",
        r"\branked\b",
        r"\branking\b",
        r"\bglobal score\b",
        r"\boverall score\b",
        r"#\d+",  # "#1", "#2", etc.
        r"\bbetter than\b",
        r"\bworse than\b",
    ]
    for pattern in ranking_patterns:
        assert re.search(pattern, local_text, re.IGNORECASE) is None, (
            f"Found ranking pattern '{pattern}' in local text"
        )


# ---------------------------------------------------------------------------
# Disclaimer always present
# ---------------------------------------------------------------------------


def test_ac_disclaimer_present() -> None:
    """The disclaimer must always be present in the output.

    Test with FakeProvider (deterministic).
    """
    profile = _make_profile()
    provider = FakeProvider(seed=42)
    result = _COACH.generate_feedback(profile, provider)
    assert _DISCLAIMER in result


# ---------------------------------------------------------------------------
# Test with FakeProvider end-to-end
# ---------------------------------------------------------------------------


def test_coach_feedback_with_fake_provider() -> None:
    """End-to-end test: generate_feedback with FakeProvider returns text
    that contains the disclaimer and dimension info.
    """
    profile = _make_profile()
    provider = FakeProvider(seed=42)
    result = _COACH.generate_feedback(profile, provider)

    assert _DISCLAIMER in result
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Empty profile
# ---------------------------------------------------------------------------


def test_coach_feedback_empty_profile() -> None:
    """Feedback for a profile with no dimensions should mention no data."""
    profile = CognitiveProfile(
        user_id="user-empty",
        dimensions={},
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )
    provider = FakeProvider(seed=42)
    result = _COACH.generate_feedback(profile, provider)
    assert _DISCLAIMER in result


# ---------------------------------------------------------------------------
# Step 1: Settings and provider selection
# ---------------------------------------------------------------------------


def test_get_llm_provider_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_llm_provider returns None when coach_use_llm is False, and a provider when True.

    Hand-derived:
      Settings(coach_use_llm=False) -> None
      Settings(coach_use_llm=True)  -> FakeProvider instance
    """
    from coglayer.api.deps import get_llm_provider
    from coglayer.core.settings import get_settings

    # Clear environment to avoid interference from .env file
    monkeypatch.delenv("COGLAYER_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("COGLAYER_LLM_PROVIDER", raising=False)
    get_settings.cache_clear()

    provider_disabled = get_llm_provider(Settings(coach_use_llm=False))
    assert provider_disabled is None

    # Explicitly set llm_provider to "fake" to ensure FakeProvider is returned
    provider_enabled = get_llm_provider(Settings(coach_use_llm=True, llm_provider="fake"))
    assert provider_enabled is not None
    assert isinstance(provider_enabled, FakeProvider)


def test_coach_no_provider_called_when_coach_use_llm_false() -> None:
    """When coach_use_llm is False, no LLM provider is called at all.

    Tested with a provider that raises if complete() is called.
    Hand-derived: provider raises AssertionError if invoked; call succeeds and returns local text.
    """
    profile = _make_profile()

    class RaisingProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            raise AssertionError("LLM provider must not be called when coach_use_llm is False")

    # When coach_use_llm is False, generate_feedback must not call the provider
    feedback = _COACH.generate_feedback(
        profile,
        provider=RaisingProvider(),
        settings=Settings(coach_use_llm=False),
    )
    assert _DISCLAIMER in feedback
    assert "Observations:" in feedback


# ---------------------------------------------------------------------------
# Step 2: Validation of an LLM reply (pure function)
# ---------------------------------------------------------------------------


def test_validate_llm_reply_passing_case() -> None:
    """Accept an LLM reply when all three rules hold.

    Hand-derived: clean string of 61 characters, no forbidden words, does not
    echo instruction prompt. Returns stripped reply string.
    """
    valid_text = "Great focus and steady progress throughout the session today."
    assert len(valid_text) >= 20
    result = validate_llm_reply(valid_text)
    assert result == valid_text


def test_validate_llm_reply_rule_a_forbidden_words() -> None:
    """Rule a: reject reply containing any forbidden word (case-insensitive whole word).

    Hand-derived: each forbidden word in a sentence >= 20 characters must return None.
    Forbidden words: diagnosis, disorder, deficit, impairment, IQ, patient.
    """
    cases = [
        "A formal diagnosis cannot be made from these tasks.",
        "Your responses show no disorder in working memory.",
        "There is no deficit detected in today's performance.",
        "No impairment was observed in your reaction speed.",
        "This assessment does not measure your IQ score.",
        "You were a very patient user throughout the session.",
    ]
    for text in cases:
        assert len(text) >= 20
        assert validate_llm_reply(text) is None, f"Expected None for forbidden word in: {text}"


def test_validate_llm_reply_rule_a_patients_plural_decision() -> None:
    """Rule a: 'patients' plural is a separate case.

    Decision: 'patients' is also forbidden because plural clinical language
    violates non-clinical coaching principles.
    Hand-derived: text containing 'patients' must return None.
    """
    text = "Most patients show similar patterns on sequence span."
    assert len(text) >= 20
    assert validate_llm_reply(text) is None


def test_validate_llm_reply_rule_a_no_false_positives_iq_substring() -> None:
    """Rule a: 'iq' inside another word must NOT match.

    Hand-derived: words like 'technique' and 'unique' contain 'iq' as substring,
    not whole word. The reply must be accepted.
    """
    clean_text = "Your technique on the visual span task was unique."
    assert len(clean_text) >= 20
    result = validate_llm_reply(clean_text)
    assert result == clean_text


def test_validate_llm_reply_rule_b_length_boundary_19_vs_20() -> None:
    """Rule b: length >= 20 characters after stripping.

    Hand-derived:
      - 19 characters after strip -> returns None
      - 20 characters after strip -> accepted
      - padded string with 19 non-whitespace chars -> returns None
    """
    # 19 characters
    text_19 = "1234567890123456789"
    assert len(text_19) == 19
    assert validate_llm_reply(text_19) is None

    # Padded with spaces, 19 chars when stripped
    padded_19 = "   1234567890123456789   "
    assert len(padded_19.strip()) == 19
    assert validate_llm_reply(padded_19) is None

    # 20 characters
    text_20 = "12345678901234567890"
    assert len(text_20) == 20
    assert validate_llm_reply(text_20) == text_20

    # Padded with spaces, 20 chars when stripped
    padded_20 = "   12345678901234567890   "
    assert len(padded_20.strip()) == 20
    assert validate_llm_reply(padded_20) == text_20


def test_validate_llm_reply_rule_c_echoes_instruction() -> None:
    """Rule c: reject reply if it echoes the instruction / system prompt text.

    Hand-derived:
      - Full instruction prompt text -> returns None
      - Prompt prefix / opening sentence (as produced by FakeProvider fallback) -> returns None
      - Reply embedding 'You are a supportive cognitive coach' -> returns None
    """
    from coglayer.coach.coach import _LLM_INSTRUCTION

    # Exact instruction echo
    assert validate_llm_reply(_LLM_INSTRUCTION) is None

    # FakeProvider fallback echo: '[FakeProvider seed=42] You are a supportive cognitive coach. Us'
    fake_provider_echo = f"[FakeProvider seed=42] {_LLM_INSTRUCTION[:40]}"
    assert validate_llm_reply(fake_provider_echo) is None

    # Opening directive embedded in response
    embedded_echo = "You are a supportive cognitive coach. Great work on the tasks!"
    assert validate_llm_reply(embedded_echo) is None


# ---------------------------------------------------------------------------
# Step 3: Readable local text
# ---------------------------------------------------------------------------


def test_step3_readable_local_text_hand_derived_and_scipy() -> None:
    """Validate readable local text format, cautious wording, and statistical bounds.

    Hand-derived:
      Beta(alpha=9, beta=3) has mean 9 / (9 + 3) = 9/12 = 0.75 = 75%.
      n_evidence = 1 session.
    TESTED:
      Independent scipy computation of 90% credible interval for Beta(9, 3):
      lower = beta.ppf(0.05, 9, 3) =~ 0.5299 -> 53%
      upper = beta.ppf(0.95, 9, 3) =~ 0.9212 -> 92%
    """
    from scipy.stats import beta as scipy_beta

    # TESTED: independent computation of interval bounds with scipy
    scipy_lo = float(scipy_beta.ppf(0.05, 9.0, 3.0))
    scipy_hi = float(scipy_beta.ppf(0.95, 9.0, 3.0))
    expected_lo_pct = round(scipy_lo * 100)  # 53%
    expected_hi_pct = round(scipy_hi * 100)  # 92%

    dim_estimate = DimensionEstimate(
        dimension="response_inhibition",
        mean=9.0 / 12.0,  # hand-derived: 0.75
        lower=scipy_lo,
        upper=scipy_hi,
        n_evidence=1,
        last_update=_TS,
        alpha=9.0,
        beta_param=3.0,
    )
    profile = _make_profile(dimensions={"response_inhibition": dim_estimate})

    local_text = CognitiveCoach._build_local_text(profile)

    # Percentage: 75%
    assert "75%" in local_text

    # Two-sided interval: 53% - 92% (or 53% \u2013 92%)
    assert (
        f"{expected_lo_pct}% \u2013 {expected_hi_pct}%" in local_text
        or f"{expected_lo_pct}% - {expected_hi_pct}%" in local_text
    )

    # Number of sessions: 1 session
    assert "1 session" in local_text

    # Cautious wording: MUST contain "suggests", NEVER "is"
    assert "suggests" in local_text.lower()
    assert re.search(r"\bis\b", local_text, re.IGNORECASE) is None, (
        f"Found forbidden word 'is' in local text:\n{local_text}"
    )

    # Fixed warning kept exactly
    exact_warning = "Based on these two tasks only \u2014 not a clinical assessment."
    assert exact_warning in local_text

    # No clinical terms from Step 2 forbidden words
    assert FORBIDDEN_WORDS_PATTERN.search(local_text) is None

    # No ranking or comparison of dimensions, no global score
    ranking_patterns = [
        r"\brank\b",
        r"\branked\b",
        r"\branking\b",
        r"\bglobal score\b",
        r"\boverall score\b",
        r"#\d+",
        r"\bbetter than\b",
        r"\bworse than\b",
    ]
    for pat in ranking_patterns:
        assert re.search(pat, local_text, re.IGNORECASE) is None


def test_step3_no_fake_provider_leak_in_feedback() -> None:
    """The coach must never leak '[FakeProvider seed=42] ...' into user-facing output."""
    profile = _make_profile()
    provider = FakeProvider(seed=42)

    feedback = _COACH.generate_feedback(profile, provider)

    assert "[FakeProvider" not in feedback
    assert "You are a supportive cognitive coach" not in feedback
    assert _DISCLAIMER in feedback
    assert "suggests" in feedback.lower()
    assert re.search(r"\bis\b", feedback, re.IGNORECASE) is None


# ---------------------------------------------------------------------------
# Step 4: End to end
# ---------------------------------------------------------------------------


def test_e2e_coach_endpoint_coach_use_llm_false(tmp_path: Path) -> None:
    """Through the real coach endpoint with coach_use_llm=False:
    the response contains the local text and the fixed warning, and no provider call happened.
    """
    from fastapi.testclient import TestClient

    from coglayer.api.app import create_app
    from coglayer.api.deps import get_llm_provider

    settings = Settings(
        db_path=str(tmp_path / "test_coach_e2e.db"),
        coach_use_llm=False,
    )
    app = create_app(settings)

    class RaisingProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            raise AssertionError("LLM provider must not be called when coach_use_llm is False")

    app.dependency_overrides[get_llm_provider] = lambda: RaisingProvider()
    client = TestClient(app)

    user_id = "user_e2e_local"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Complete both tasks to unlock the coach
    gng = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 200.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        }
    ]
    span = [
        {
            "stimulus": "0,1",
            "expected": "0,1",
            "response": "0,1",
            "rt_ms": 1000.0,
            "timestamp": "2024-01-15T10:00:10+00:00",
            "length": 2,
        }
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng}},
    )
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"sequences": span}},
    )

    resp = client.post(f"/v1/assessment/coach/{user_id}")
    assert resp.status_code == 200
    text = resp.text

    # Contains local text and fixed warning
    assert _DISCLAIMER in text
    assert "suggests" in text.lower()
    assert re.search(r"\bis\b", text, re.IGNORECASE) is None
    assert "[FakeProvider" not in text


def test_e2e_coach_endpoint_fallback_on_forbidden_word(tmp_path: Path) -> None:
    """Through the real coach endpoint with a provider returning a forbidden word:
    the response falls back to the local text.
    """
    from fastapi.testclient import TestClient

    from coglayer.api.app import create_app
    from coglayer.api.deps import get_llm_provider

    settings = Settings(
        db_path=str(tmp_path / "test_coach_e2e_bad.db"),
        coach_use_llm=True,
    )
    app = create_app(settings)

    class ForbiddenWordProvider:
        def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                text="Your profile shows no sign of a cognitive disorder at all. Keep it up!"
            )

    app.dependency_overrides[get_llm_provider] = lambda: ForbiddenWordProvider()
    client = TestClient(app)

    user_id = "user_e2e_forbidden"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Complete both tasks to unlock the coach
    gng = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 200.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        }
    ]
    span = [
        {
            "stimulus": "0,1",
            "expected": "0,1",
            "response": "0,1",
            "rt_ms": 1000.0,
            "timestamp": "2024-01-15T10:00:10+00:00",
            "length": 2,
        }
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng}},
    )
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"sequences": span}},
    )

    resp = client.post(f"/v1/assessment/coach/{user_id}")
    assert resp.status_code == 200
    text = resp.text

    # Must fall back to local text (no forbidden word, contains disclaimer and local wording)
    assert "disorder" not in text.lower()
    assert _DISCLAIMER in text
    assert "suggests" in text.lower()
    assert re.search(r"\bis\b", text, re.IGNORECASE) is None
