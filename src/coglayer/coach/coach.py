"""Cognitive coach for CogLayer.

Builds personalized, encouraging feedback from a user's cognitive profile.
The coach is available only when the user has at least one session where
the decision engine returned ``complete``.  A new empty session must not
lock the coach again.

Feedback flow
-------------
1. Build a local summary string from the profile dimensions: credible
   interval as a percent range, n_evidence, data quality completeness,
   and uncertainty.  Append the fixed disclaimer.
2. Send ONLY that local summary to the LLM provider as a neutral coaching
   instruction.  The CognitiveProfile object and raw trial data are NEVER
   included in the prompt.
3. If the LLM response contains a forbidden word (case-insensitive,
   whole-word match) or the provider raises an exception, fall back to
   the local text and log a warning (without including the text).
4. Never rank dimensions against each other or output a global score.

Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
"""

from __future__ import annotations

import logging
import re
from typing import Final

from coglayer.core.brain_twin import BrainTwinSignal, BrainTwinState
from coglayer.core.models import CognitiveProfile, TaskResult
from coglayer.core.protocols import LLMProvider, LLMRequest
from coglayer.core.settings import Settings

__all__ = ["FORBIDDEN_WORDS_PATTERN", "CognitiveCoach", "validate_llm_reply"]

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Forbidden words — case-insensitive whole-word regex
# Never use these in code, comments, UI text, or generated feedback.
# ---------------------------------------------------------------------------

_FORBIDDEN_WORDS: Final[tuple[str, ...]] = (
    "diagnosis",
    "disorder",
    "deficit",
    "impairment",
    "IQ",
    "patient",
    "patients",
)

FORBIDDEN_WORDS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _FORBIDDEN_WORDS) + r")\b",
    re.IGNORECASE,
)
"""Compiled regex matching any forbidden word as a whole word."""

_DISCLAIMER: Final[str] = "Based on these two tasks only \u2014 not a clinical assessment."

_LLM_INSTRUCTION: Final[str] = (
    "You are a supportive cognitive coach. Use the following notes to write "
    "friendly, encouraging feedback for the user. Do not rank dimensions "
    "against each other and do not produce a global score. Keep it concise."
)

_BRAIN_TWIN_CONTEXT: Final[str] = (
    "A recent comparable measurement differs from the user's usual reference. "
    "This indicates a variation to review, but does not determine its cause. "
    "The user can continue, take a pause, or repeat the activity."
)


def _echoes_instruction(reply: str, instruction: str) -> bool:
    """Return True if reply echoes the instruction or its opening directive."""
    if not instruction:
        return False
    r_lower = reply.lower()
    inst_lower = instruction.strip().lower()
    if inst_lower in r_lower:
        return True
    first_sentence = inst_lower.split(".")[0].strip()
    if len(first_sentence) >= 15 and first_sentence in r_lower:
        return True
    return False


def validate_llm_reply(
    reply: str,
    instruction: str = _LLM_INSTRUCTION,
) -> str | None:
    """Validate an LLM reply against safety and quality rules.

    Accepts an LLM reply only if ALL hold:
      a) none of these whole words appear, case-insensitive:
         diagnosis, disorder, deficit, impairment, IQ, patient, patients;
      b) length >= 20 characters after stripping;
      c) it does not echo the instruction/system prompt text.

    Otherwise returns None so the caller falls back to the local text.
    """
    if not reply:
        return None
    stripped = reply.strip()
    if len(stripped) < 20:
        return None
    if FORBIDDEN_WORDS_PATTERN.search(stripped):
        return None
    if _echoes_instruction(stripped, instruction):
        return None
    return stripped


class CognitiveCoach:
    """Generates personalized cognitive feedback from a profile.

    Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
    """

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(
        self,
        user_id: str,
        all_session_results: list[list[TaskResult]],
        settings: Settings,
    ) -> bool:
        """Return True if the coach is available for the given user.

        The coach is available when the user has at least one session
        whose results would yield a ``complete`` decision from the engine.
        A new empty session does not lock the coach again.

        Parameters
        ----------
        user_id :
            User identifier (unused directly; kept for API symmetry).
        all_session_results :
            A list of result-lists, one per session for this user.
        settings :
            Application settings (completeness threshold).

        Returns
        -------
        bool
            True if the user may receive coaching feedback.
        """
        from coglayer.coach.decision import AdaptiveDecisionEngine

        engine = AdaptiveDecisionEngine()
        for session_results in all_session_results:
            decision = engine.decide(results=session_results, settings=settings)
            if decision.status == "complete":
                return True
        return False

    # ------------------------------------------------------------------
    # Feedback generation
    # ------------------------------------------------------------------

    def generate_feedback(
        self,
        profile: CognitiveProfile,
        provider: LLMProvider | None = None,
        settings: Settings | None = None,
        *,
        brain_twin_signal: BrainTwinSignal | None = None,
    ) -> str:
        """Generate coaching feedback from the profile.

        Builds a local summary from the profile dimensions, then asks the
        LLM provider to rewrite it in a friendly tone if enabled.  The CognitiveProfile
        object is NEVER sent to the provider.

        When coach_use_llm is False or no provider is given, the local text is
        returned directly without calling any provider.

        On a forbidden-word hit or a provider exception the local text is
        returned as-is and a warning is logged (without the text content).

        Parameters
        ----------
        profile :
            The user's current cognitive profile.
        provider :
            Optional LLM provider (FakeProvider in tests).
        settings :
            Optional application settings (coach_use_llm flag).

        Returns
        -------
        str
            Coaching feedback text including the disclaimer.
        """
        local_text = self._build_local_text(profile, brain_twin_signal)

        if settings is not None and not settings.coach_use_llm:
            return local_text

        if provider is None:
            return local_text

        # Build the LLM prompt — only the local text, never the profile object
        prompt = f"{_LLM_INSTRUCTION}\n\n{local_text}"

        try:
            llm_response = provider.complete(LLMRequest(prompt=prompt))
            raw_text = llm_response.text
        except Exception:
            _log.warning("LLM provider raised an exception; falling back to local text")
            return local_text

        # Validate LLM output against clinical words, length, and instruction echo
        validated = validate_llm_reply(raw_text, instruction=_LLM_INSTRUCTION)
        if validated is None:
            _log.warning("LLM response failed validation; falling back to local text")
            return local_text

        # Append disclaimer if the LLM didn't include it
        if _DISCLAIMER not in validated:
            validated = f"{validated}\n\n{_DISCLAIMER}"

        return validated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_local_text(
        profile: CognitiveProfile,
        brain_twin_signal: BrainTwinSignal | None = None,
    ) -> str:
        """Build a human-readable summary from the profile dimensions.

        Includes per-dimension: percentage, two-sided credible interval,
        session count, cautious wording ('suggests', never 'is').
        Never ranks dimensions or outputs a global score.
        """
        lines: list[str] = []
        lines.append("Cognitive profile summary:\n")

        if not profile.dimensions:
            lines.append("No assessment data available yet.")
            if (
                brain_twin_signal is not None
                and brain_twin_signal.state is BrainTwinState.VARIATION_FLAGGED
            ):
                lines.append(f"\n{_BRAIN_TWIN_CONTEXT}")
            lines.append(f"\n{_DISCLAIMER}")
            return "\n".join(lines)

        for dim_name, estimate in sorted(profile.dimensions.items()):
            pct = round(estimate.mean * 100)
            lower_pct = round(estimate.lower * 100)
            upper_pct = round(estimate.upper * 100)
            n = estimate.n_evidence
            session_str = f"{n} session" if n == 1 else f"{n} sessions"

            dim_label = dim_name.replace("_", " ").title()
            lines.append(f"  {dim_label}:")
            lines.append(
                f"    Performance suggests an estimate of {pct}% "
                f"(two-sided credible interval: {lower_pct}% \u2013 {upper_pct}%, "
                f"based on {session_str})."
            )
            lines.append(f"    Observations: {n}")
            lines.append("")

        if (
            brain_twin_signal is not None
            and brain_twin_signal.state is BrainTwinState.VARIATION_FLAGGED
        ):
            lines.append(_BRAIN_TWIN_CONTEXT)
            lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)
