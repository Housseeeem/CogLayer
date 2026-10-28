"""Unit tests for onboarding data models.

Tests validate Pydantic models for ExperienceProfile and related enums.
Ensures that all enum values are valid and model constraints are enforced.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coglayer.core.models import (
    AgeGroup,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)


def test_age_group_enum_values() -> None:
    """AgeGroup enum has all expected values."""
    assert AgeGroup.CHILD_7_12.value == "child_7_12"
    assert AgeGroup.TEEN_13_17.value == "teen_13_17"
    assert AgeGroup.YOUNG_ADULT_18_30.value == "young_adult_18_30"
    assert AgeGroup.ADULT_31_60.value == "adult_31_60"
    assert AgeGroup.SENIOR_60_PLUS.value == "senior_60_plus"


def test_tech_comfort_enum_values() -> None:
    """TechComfort enum has all expected values."""
    assert TechComfort.NEW.value == "new"
    assert TechComfort.SOME_EXPERIENCE.value == "some_experience"
    assert TechComfort.COMFORTABLE.value == "comfortable"
    assert TechComfort.VERY_COMFORTABLE.value == "very_comfortable"


def test_info_style_enum_values() -> None:
    """InfoStyle enum has all expected values."""
    assert InfoStyle.VISUAL.value == "visual"
    assert InfoStyle.STEP_BY_STEP.value == "step_by_step"
    assert InfoStyle.SHORT_SIMPLE.value == "short_simple"
    assert InfoStyle.DETAILED.value == "detailed"
    assert InfoStyle.CONVERSATIONAL.value == "conversational"


def test_layout_type_enum_values() -> None:
    """LayoutType enum has all expected values."""
    assert LayoutType.GUIDED_JOURNEY.value == "guided_journey"
    assert LayoutType.DASHBOARD.value == "dashboard"
    assert LayoutType.CONVERSATION_FIRST.value == "conversation_first"
    assert LayoutType.MINIMAL.value == "minimal"


def test_theme_type_enum_values() -> None:
    """ThemeType enum has all expected values."""
    assert ThemeType.LARGER_TEXT.value == "larger_text"
    assert ThemeType.STANDARD.value == "standard"
    assert ThemeType.HIGH_CONTRAST.value == "high_contrast"
    assert ThemeType.SOFTER_COLORS.value == "softer_colors"
    assert ThemeType.BRIGHTER_COLORS.value == "brighter_colors"


def test_guidance_level_enum_values() -> None:
    """GuidanceLevel enum has all expected values."""
    assert GuidanceLevel.MORE.value == "more"
    assert GuidanceLevel.SOME.value == "some"
    assert GuidanceLevel.MINIMAL.value == "minimal"


def test_experience_profile_valid() -> None:
    """ExperienceProfile validates with all required fields."""
    profile = ExperienceProfile(
        user_id="user123",
        age_group=AgeGroup.ADULT_31_60,
        goals=["improve_focus", "reduce_stress"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=InfoStyle.DETAILED,
        layout=LayoutType.DASHBOARD,
        theme=ThemeType.STANDARD,
        guidance_level=GuidanceLevel.SOME,
    )
    assert profile.user_id == "user123"
    assert profile.age_group == AgeGroup.ADULT_31_60
    assert len(profile.goals) == 2
    assert profile.tech_comfort == TechComfort.COMFORTABLE
    assert profile.guidance_level == GuidanceLevel.SOME


def test_experience_profile_guidance_level_optional() -> None:
    """guidance_level is optional and can be None."""
    profile = ExperienceProfile(
        user_id="user123",
        age_group=AgeGroup.YOUNG_ADULT_18_30,
        goals=["learn_new_skills"],
        tech_comfort=TechComfort.NEW,
        info_style=InfoStyle.VISUAL,
        layout=LayoutType.GUIDED_JOURNEY,
        theme=ThemeType.LARGER_TEXT,
    )
    assert profile.guidance_level is None


def test_experience_profile_goals_minimum_one() -> None:
    """goals must have at least one element."""
    with pytest.raises(ValueError):  # Pydantic validation error
        ExperienceProfile(
            user_id="user123",
            age_group=AgeGroup.ADULT_31_60,
            goals=[],
            tech_comfort=TechComfort.COMFORTABLE,
            info_style=InfoStyle.DETAILED,
            layout=LayoutType.DASHBOARD,
            theme=ThemeType.STANDARD,
        )


def test_experience_profile_timestamps_default() -> None:
    """created_at and updated_at default to UTC now."""
    before = datetime.now(UTC)
    profile = ExperienceProfile(
        user_id="user123",
        age_group=AgeGroup.ADULT_31_60,
        goals=["goal1"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=InfoStyle.DETAILED,
        layout=LayoutType.DASHBOARD,
        theme=ThemeType.STANDARD,
    )
    after = datetime.now(UTC)
    assert before <= profile.created_at <= after
    assert before <= profile.updated_at <= after


def test_experience_profile_model_dump() -> None:
    """ExperienceProfile serializes correctly."""
    profile = ExperienceProfile(
        user_id="user123",
        age_group=AgeGroup.CHILD_7_12,
        goals=["improve_attention"],
        tech_comfort=TechComfort.SOME_EXPERIENCE,
        info_style=InfoStyle.SHORT_SIMPLE,
        layout=LayoutType.MINIMAL,
        theme=ThemeType.SOFTER_COLORS,
        guidance_level=GuidanceLevel.MORE,
    )
    data = profile.model_dump()
    assert data["user_id"] == "user123"
    assert data["age_group"] == "child_7_12"
    assert data["goals"] == ["improve_attention"]
    assert data["guidance_level"] == "more"
