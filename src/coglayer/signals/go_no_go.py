"""Go/No-Go task scorer and runner for CogLayer.

The Go/No-Go task is an active cognitive probe measuring response inhibition -
the ability to suppress a prepotent response when a No-Go stimulus appears.

**Non-clinical statement:** This tool is not a clinical assessment. Results
reflect performance on this specific task under these conditions only and
MUST NOT be used to diagnose any condition or make clinical decisions.

Requirements: R-003.1 to R-003.4
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean, stdev
from typing import Final

from coglayer.core.models import (
    DataQuality,
    RawTaskResult,
    Signal,
    TaskResult,
    Trial,
)

__all__ = [
    "ANTICIPATION_THRESHOLD_MS",
    "IMPLAUSIBLY_FAST_GO_MS",
    "GoNoGoRunner",
    "GoNoGoScorer",
]

# ---------------------------------------------------------------------------
# Exclusion constants  (R-003.4)
# ---------------------------------------------------------------------------

# Anticipation threshold: responses faster than 100 ms cannot be
# intentional Go responses - they precede sensorimotor processing time.
ANTICIPATION_THRESHOLD_MS: Final[float] = 100.0

# Implausibly-fast Go threshold: below 150 ms, the response was likely
# a key held down or a timing artefact rather than a deliberate response.
IMPLAUSIBLY_FAST_GO_MS: Final[float] = 150.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_trial(raw_trial: dict[str, object]) -> Trial:
    """Convert a raw trial dict into a validated Trial model.

    Exclusion rules are applied here (R-003.4), but ONLY when ``response is
    not None``.  A correctly inhibited No-Go (response=None) stays valid
    regardless of rt_ms, because rt_ms in that case reflects the trial
    timeout, not a deliberate keypress.

    For trials where a response was made:

    1. If ``rt_ms < ANTICIPATION_THRESHOLD_MS`` -> ``valid=False``,
       ``invalid_reason="anticipation"`` (applies to all stimuli).
    2. Else if stimulus is "go" and ``rt_ms < IMPLAUSIBLY_FAST_GO_MS`` ->
       ``valid=False``, ``invalid_reason="implausibly_fast"``.

    The anticipation check runs first; a trial with rt_ms < 100 is always
    marked "anticipation", never "implausibly_fast".
    """
    stimulus: str = str(raw_trial["stimulus"])
    expected: str = str(raw_trial["expected"])
    response: str | None = (
        str(raw_trial["response"]) if raw_trial.get("response") is not None else None
    )
    rt_ms: float = float(raw_trial["rt_ms"])  # type: ignore[arg-type]
    timestamp: datetime = datetime.fromisoformat(str(raw_trial["timestamp"]))

    # Start from the validity flags already present in the raw dict (if any).
    valid: bool = bool(raw_trial.get("valid", True))
    invalid_reason: str | None = (
        str(raw_trial["invalid_reason"]) if raw_trial.get("invalid_reason") is not None else None
    )

    # Apply exclusion logic - overrides incoming flags when a rule fires.
    # Exclusions apply ONLY when a response was actually made (response is not None).
    # A correctly inhibited No-Go (response=None) stays valid regardless of rt_ms,
    # because the recorded rt_ms reflects the trial timeout, not a keypress.
    if response is not None:
        if rt_ms < ANTICIPATION_THRESHOLD_MS:
            valid = False
            invalid_reason = "anticipation"
        elif stimulus == "go" and rt_ms < IMPLAUSIBLY_FAST_GO_MS:
            valid = False
            invalid_reason = "implausibly_fast"

    return Trial(
        stimulus=stimulus,
        expected=expected,
        response=response,
        rt_ms=rt_ms,
        timestamp=timestamp,
        valid=valid,
        invalid_reason=invalid_reason,
    )


# ---------------------------------------------------------------------------
# Scorer  (R-003.3, R-003.4, R-003.5)
# ---------------------------------------------------------------------------


class GoNoGoScorer:
    """Score a raw Go/No-Go result into a validated TaskResult.

    Implements ScoringAdapter.

    Raw input format
    ----------------
    The ``raw`` dict MUST contain:

    * ``"session_id"``   - str
    * ``"user_id"``      - str
    * ``"task_version"`` - str (optional, defaults to ``"1.0"``)
    * ``"trials"``       - list of trial dicts, each with:
      - ``stimulus``     - str, ``"go"`` or ``"nogo"``
      - ``expected``     - str, ``"press"`` or ``"inhibit"``
      - ``response``     - str | None
      - ``rt_ms``        - float
      - ``timestamp``    - str (ISO-8601)
      - ``valid``        - bool (optional, default ``True``)
      - ``invalid_reason`` - str | None (optional, default ``None``)

    Metrics computed (valid trials only, R-003.3)
    ----------------------------------------------
    * ``commission_errors``  - valid No-Go trials where response is not None.
    * ``omission_errors``    - valid Go trials where response is None.
    * ``accuracy``           - proportion correct among all valid scored trials.
    * ``nogo_accuracy``      - proportion of valid No-Go trials correctly inhibited
                               (correct_nogo / nogo_valid_count; 0.0 when no valid No-Go).
    * ``go_accuracy``        - proportion of valid Go trials correctly responded
                               (correct_go / go_valid_count; 0.0 when no valid Go).
    * ``nogo_valid_count``   - count of valid No-Go trials (float for metric-dict
                               uniformity).
    * ``go_valid_count``     - count of valid Go trials (float for metric-dict
                               uniformity).
    * ``mean_rt_ms``         - mean RT of correct, valid Go trials.
    * ``rt_std_ms``          - std dev of RT for correct valid Go trials
                               (0.0 when fewer than 2 such trials exist).
    * ``valid_trial_count``  - number of valid trials.
    """

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw Go/No-Go data and return a fully-populated TaskResult."""
        session_id: str = str(raw["session_id"])
        user_id: str = str(raw["user_id"])
        task_version: str = str(raw.get("task_version", "1.0"))

        raw_trials = raw["trials"]
        assert isinstance(raw_trials, list)
        total_trials: int = len(raw_trials)

        # Build validated Trial objects with exclusion applied.
        trials: list[Trial] = [_parse_trial(t) for t in raw_trials]

        valid_trials: list[Trial] = [t for t in trials if t.valid]
        valid_trial_count: int = len(valid_trials)

        # --- Commission errors: valid No-Go where a response WAS given ------
        commission_errors: int = sum(
            1 for t in valid_trials if t.stimulus == "nogo" and t.response is not None
        )

        # --- Omission errors: valid Go where NO response was given ----------
        omission_errors: int = sum(
            1 for t in valid_trials if t.stimulus == "go" and t.response is None
        )

        # --- Accuracy: proportion correct among all valid scored trials ------
        # A trial is "correct" when expected == response (using None-safe compare).
        # For No-Go trials, expected=="inhibit" and response should be None.
        def _is_correct(t: Trial) -> bool:
            if t.expected == "inhibit":
                return t.response is None
            # Go trial: expected=="press"; response must not be None.
            return t.response is not None and t.expected == t.response

        correct_valid_trials: list[Trial] = [t for t in valid_trials if _is_correct(t)]
        accuracy: float = (
            len(correct_valid_trials) / valid_trial_count if valid_trial_count > 0 else 0.0
        )

        # --- RT metrics: correct valid Go trials only -----------------------
        correct_go_rts: list[float] = [
            t.rt_ms
            for t in valid_trials
            if t.stimulus == "go" and t.response is not None and _is_correct(t)
        ]

        mean_rt_ms: float = mean(correct_go_rts) if correct_go_rts else 0.0
        rt_std_ms: float = stdev(correct_go_rts) if len(correct_go_rts) >= 2 else 0.0

        # --- Data quality ---------------------------------------------------
        completeness: float = valid_trial_count / total_trials if total_trials > 0 else 0.0
        data_quality = DataQuality(
            valid_trials=valid_trial_count,
            total_trials=total_trials,
            completeness=completeness,
            anomalies=[],
        )

        # --- Stimulus-specific accuracy metrics ----------------------------
        # No-Go accuracy: proportion of valid No-Go trials correctly inhibited
        valid_nogo_trials = [t for t in valid_trials if t.stimulus == "nogo"]
        correct_nogo_trials = [t for t in valid_nogo_trials if _is_correct(t)]
        nogo_accuracy: float = (
            len(correct_nogo_trials) / len(valid_nogo_trials) if valid_nogo_trials else 0.0
        )

        # Go accuracy: proportion of valid Go trials correctly responded
        valid_go_trials = [t for t in valid_trials if t.stimulus == "go"]
        correct_go_trials = [t for t in valid_go_trials if _is_correct(t)]
        go_accuracy: float = (
            len(correct_go_trials) / len(valid_go_trials) if valid_go_trials else 0.0
        )

        # --- Valid trial counts by stimulus type ----------------------------
        nogo_valid_count: float = float(len(valid_nogo_trials))
        go_valid_count: float = float(len(valid_go_trials))

        # --- Metrics dict ---------------------------------------------------
        metrics: dict[str, float] = {
            "commission_errors": float(commission_errors),
            "omission_errors": float(omission_errors),
            "accuracy": accuracy,
            "nogo_accuracy": nogo_accuracy,
            "go_accuracy": go_accuracy,
            "nogo_valid_count": nogo_valid_count,
            "go_valid_count": go_valid_count,
            "mean_rt_ms": mean_rt_ms,
            "rt_std_ms": rt_std_ms,
            "valid_trial_count": float(valid_trial_count),
        }

        return TaskResult(
            task_id="go_no_go",
            task_version=task_version,
            session_id=session_id,
            user_id=user_id,
            trials=trials,
            metrics=metrics,
            signals=[Signal(name="rt", value=mean_rt_ms)],
            target_dimensions=["response_inhibition"],
            data_quality=data_quality,
            uncertainty=None,
        )


# ---------------------------------------------------------------------------
# Runner stub  (R-002.2)
# ---------------------------------------------------------------------------


class GoNoGoRunner:
    """Task runner stub for the Go/No-Go task.

    Implements TaskRunner.

    The Go/No-Go task requires a JavaScript-instrumented UI for accurate
    sub-10 ms RT capture (R-010.3). Running it headlessly is not meaningful.
    Call GoNoGoScorer.score() directly with a pre-built raw result dict instead.
    """

    def run(
        self,
        session_id: str,
        user_id: str,
        parameters: dict[str, object],
    ) -> RawTaskResult:
        """Raise NotImplementedError - task is UI-driven."""
        raise NotImplementedError("UI-driven; call scorer directly")
