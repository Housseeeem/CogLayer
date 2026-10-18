"""Dependency injection providers for CogLayer FastAPI app.

Provides injectable factories for repositories, services, registries,
and coaches using FastAPI Depends.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteConsentRepository,
    SQLiteProfileRepository,
)
from coglayer.coach.coach import CognitiveCoach
from coglayer.coach.decision import AdaptiveDecisionEngine
from coglayer.core.protocols import (
    AssessmentRepository,
    ConsentRepository,
    LLMProvider,
    ProfileRepository,
    ScoringAdapter,
    TaskRegistry,
)
from coglayer.core.settings import Settings, get_settings
from coglayer.privacy.consent import ConsentService
from coglayer.profile.service import ProfileService
from coglayer.providers.fake import FakeProvider
from coglayer.signals.go_no_go import GoNoGoScorer
from coglayer.signals.registry import build_default_registry
from coglayer.signals.sequence_span import SequenceSpanScorer

__all__ = [
    "get_assessment_repo",
    "get_coach",
    "get_consent_repo",
    "get_consent_service",
    "get_db_settings",
    "get_decision_engine",
    "get_llm_provider",
    "get_profile_repo",
    "get_profile_service",
    "get_scoring_adapters",
    "get_task_registry",
]


def get_db_settings() -> Settings:
    """Return runtime application settings."""
    return get_settings()


def get_assessment_repo(
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> AssessmentRepository:
    """Return an AssessmentRepository backed by SQLite."""
    return SQLiteAssessmentRepository(settings.db_path)


def get_profile_repo(
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> ProfileRepository:
    """Return a ProfileRepository backed by SQLite."""
    return SQLiteProfileRepository(settings.db_path)


def get_consent_repo(
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> ConsentRepository:
    """Return a ConsentRepository backed by SQLite."""
    return SQLiteConsentRepository(settings.db_path)


def get_consent_service(
    repo: Annotated[ConsentRepository, Depends(get_consent_repo)],
) -> ConsentService:
    """Return a ConsentService wired to the consent repository."""
    return ConsentService(repo)


def get_task_registry() -> TaskRegistry:
    """Return the default pre-populated TaskRegistry."""
    return build_default_registry()


def get_decision_engine(
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
) -> AdaptiveDecisionEngine:
    """Return the AdaptiveDecisionEngine wired to task registry and interval function."""
    from coglayer.profile.model import BetaProfileModel

    model = BetaProfileModel()
    return AdaptiveDecisionEngine(registry=registry, interval_fn=model.credible_interval)


def get_coach() -> CognitiveCoach:
    """Return the CognitiveCoach."""
    return CognitiveCoach()


def get_llm_provider(
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> LLMProvider | None:
    """Return the configured LLMProvider or None when coach_use_llm is False."""
    if not settings.coach_use_llm:
        return None
    # For MVP / tests, returns FakeProvider(seed=42)
    return FakeProvider(seed=42)


def get_profile_service(
    settings: Annotated[Settings, Depends(get_db_settings)],
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
) -> ProfileService:
    """Return the ProfileService configured with forgetting factor and task registry."""
    return ProfileService(
        lambda_=settings.forgetting_factor,
        registry=registry,
    )


def get_scoring_adapters(
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
) -> dict[str, ScoringAdapter]:
    """Return task scoring adapters built from the task registry."""
    if hasattr(registry, "get_scorers"):
        return registry.get_scorers()  # type: ignore[no-any-return]
    adapters: dict[str, ScoringAdapter] = {}
    for task_id in registry.list_ids():
        try:
            desc = registry.get(task_id, "1.0")
            if task_id == "go_no_go":
                adapters[task_id] = GoNoGoScorer(descriptor=desc)
            elif task_id == "sequence_span":
                adapters[task_id] = SequenceSpanScorer(descriptor=desc)
        except KeyError:
            continue
    return adapters
