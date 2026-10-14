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

from coglayer.core.models import CognitiveProfile, TaskResult
from coglayer.core.protocols import LLMProvider, LLMRequest
from coglayer.core.settings import Settings

__all__ = ["FORBIDDEN_WORDS_PATTERN", "CognitiveCoach"]

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
        provider: LLMProvider,
    ) -> str:
        """Generate coaching feedback from the profile.

        Builds a local summary from the profile dimensions, then asks the
        LLM provider to rewrite it in a friendly tone.  The CognitiveProfile
        object is NEVER sent to the provider.

        On a forbidden-word hit or a provider exception the local text is
        returned as-is and a warning is logged (without the text content).

        Parameters
        ----------
        profile :
            The user's current cognitive profile.
        provider :
            LLM provider (FakeProvider in tests).

        Returns
        -------
        str
            Coaching feedback text including the disclaimer.
        """
        local_text = self._build_local_text(profile)

        # Build the LLM prompt — only the local text, never the profile object
        prompt = f"{_LLM_INSTRUCTION}\n\n{local_text}"

        try:
            llm_response = provider.complete(LLMRequest(prompt=prompt))
            enriched = llm_response.text
        except Exception:
            _log.warning("LLM provider raised an exception; falling back to local text")
            return local_text

        # Check for forbidden words in the LLM output
        if FORBIDDEN_WORDS_PATTERN.search(enriched):
            _log.warning("LLM response contained a forbidden word; falling back to local text")
            return local_text

        # Append disclaimer if the LLM didn't include it
        if _DISCLAIMER not in enriched:
            enriched = f"{enriched}\n\n{_DISCLAIMER}"

        return enriched

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_local_text(profile: CognitiveProfile) -> str:
        """Build a human-readable summary from the profile dimensions.

        Includes per-dimension: credible interval as percent range,
        n_evidence count, data quality completeness, and uncertainty.
        Never ranks dimensions or outputs a global score.
        """
        lines: list[str] = []
        lines.append("Here is your cognitive profile summary:\n")

        if not profile.dimensions:
            lines.append("No assessment data available yet.")
            lines.append(f"\n{_DISCLAIMER}")
            return "\n".join(lines)

        for dim_name, estimate in sorted(profile.dimensions.items()):
            lower_pct = estimate.lower * 100
            upper_pct = estimate.upper * 100
            n = estimate.n_evidence
            dq = profile.data_quality.get(dim_name)
            completeness = dq.completeness if dq else 0.0
            unc = profile.uncertainty.get(dim_name)

            dim_label = dim_name.replace("_", " ").title()
            lines.append(f"  {dim_label}:")
            lines.append(f"    Estimated range: {lower_pct:.0f}% \u2013 {upper_pct:.0f}%")
            lines.append(f"    Observations: {n}")
            lines.append(f"    Data quality: {completeness:.0%}")
            if unc is not None:
                lines.append(f"    Uncertainty: {unc:.2f}")
            lines.append("")

        lines.append(_DISCLAIMER)
        return "\n".join(lines)
