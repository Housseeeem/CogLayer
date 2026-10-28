"""Pure scoring for the experimental Indice Opérationnel d'Interaction."""

from __future__ import annotations

from typing import Final

from coglayer.core.models import (
    IOIComponent,
    IOIComponentScore,
    IOIObservation,
    IOIScore,
)

IOI_WEIGHTS: Final[dict[IOIComponent, float]] = {
    IOIComponent.CRITICAL_VERIFICATION: 0.25,
    IOIComponent.CLARIFICATION: 0.20,
    IOIComponent.ITERATION: 0.20,
    IOIComponent.AUTONOMY: 0.20,
    IOIComponent.RESPONSIBLE_USAGE: 0.15,
}
IOI_MINIMUM_OBSERVATIONS: Final[int] = 3
IOI_CALCULATION_VERSION: Final[str] = "1.0"

if sum(IOI_WEIGHTS.values()) != 1.0:  # pragma: no cover
    raise RuntimeError("IOI component weights must sum to 1.0")


class IOIScoringService:
    """Calculate component scores and a fixed-weight IOI aggregate."""

    def score(self, observations: list[IOIObservation]) -> IOIScore:
        """Return an IOI score from explicitly recorded observations."""
        user_id = observations[0].user_id if observations else ""
        by_opportunity: dict[tuple[IOIComponent, str], IOIObservation] = {}
        for observation in observations:
            key = (observation.component, observation.opportunity_id)
            by_opportunity.setdefault(key, observation)

        components: dict[IOIComponent, IOIComponentScore] = {}
        for component, weight in IOI_WEIGHTS.items():
            valid = [
                observation
                for (candidate, _), observation in by_opportunity.items()
                if candidate is component and observation.valid
            ]
            evidence_count = len(valid)
            score = (
                sum(observation.behavior_observed for observation in valid) / evidence_count
                if evidence_count
                else 0.0
            )
            components[component] = IOIComponentScore(
                score=score,
                evidence_count=evidence_count,
                weight=weight,
                sufficient=evidence_count >= IOI_MINIMUM_OBSERVATIONS,
            )

        sufficient = all(component.sufficient for component in components.values())
        aggregate = (
            sum(component.score * component.weight for component in components.values())
            if sufficient
            else None
        )
        return IOIScore(
            user_id=user_id,
            components=components,
            aggregate_score=aggregate,
            status="AVAILABLE" if sufficient else "INSUFFICIENT_EVIDENCE",
            calculation_version=IOI_CALCULATION_VERSION,
        )
