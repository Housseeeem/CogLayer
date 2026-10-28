"""Unit tests for ExperienceProfile repository.

Tests cover SQLiteExperienceProfileRepository CRUD operations and cascade delete.
"""

from __future__ import annotations

import pathlib

from coglayer.api.db.sqlite import SQLiteExperienceProfileRepository
from coglayer.core.models import (
    AgeGroup,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)


def test_save_and_get_profile(tmp_path: pathlib.Path) -> None:
    """save_profile then get_profile returns the same data."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))
    profile = ExperienceProfile(
        user_id="alice",
        age_group=AgeGroup.ADULT_31_60,
        goals=["improve_focus", "reduce_stress"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=InfoStyle.DETAILED,
        layout=LayoutType.DASHBOARD,
        theme=ThemeType.STANDARD,
        guidance_level=GuidanceLevel.SOME,
    )
    repo.save_profile(profile)
    loaded = repo.get_profile("alice")
    assert loaded is not None
    assert loaded.user_id == "alice"
    assert loaded.age_group == AgeGroup.ADULT_31_60
    assert loaded.goals == ["improve_focus", "reduce_stress"]
    assert loaded.tech_comfort == TechComfort.COMFORTABLE
    assert loaded.guidance_level == GuidanceLevel.SOME


def test_get_profile_not_found(tmp_path: pathlib.Path) -> None:
    """get_profile returns None for a non-existent user."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))
    assert repo.get_profile("ghost") is None


def test_upsert_profile(tmp_path: pathlib.Path) -> None:
    """save_profile replaces existing profile (upsert)."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))

    # First save
    profile1 = ExperienceProfile(
        user_id="bob",
        age_group=AgeGroup.YOUNG_ADULT_18_30,
        goals=["learn_skills"],
        tech_comfort=TechComfort.NEW,
        info_style=InfoStyle.VISUAL,
        layout=LayoutType.GUIDED_JOURNEY,
        theme=ThemeType.LARGER_TEXT,
    )
    repo.save_profile(profile1)

    # Update with different data
    profile2 = ExperienceProfile(
        user_id="bob",
        age_group=AgeGroup.ADULT_31_60,
        goals=["improve_focus", "learn_skills"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=InfoStyle.DETAILED,
        layout=LayoutType.DASHBOARD,
        theme=ThemeType.STANDARD,
        guidance_level=GuidanceLevel.SOME,
    )
    repo.save_profile(profile2)

    # Verify the updated data
    loaded = repo.get_profile("bob")
    assert loaded is not None
    assert loaded.age_group == AgeGroup.ADULT_31_60
    assert len(loaded.goals) == 2
    assert loaded.guidance_level == GuidanceLevel.SOME


def test_delete_user(tmp_path: pathlib.Path) -> None:
    """delete_user removes the profile for the given user."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))
    profile = ExperienceProfile(
        user_id="carol",
        age_group=AgeGroup.TEEN_13_17,
        goals=["better_memory"],
        tech_comfort=TechComfort.SOME_EXPERIENCE,
        info_style=InfoStyle.SHORT_SIMPLE,
        layout=LayoutType.MINIMAL,
        theme=ThemeType.SOFTER_COLORS,
    )
    repo.save_profile(profile)
    repo.delete_user("carol")
    assert repo.get_profile("carol") is None


def test_delete_user_does_not_affect_other_users(tmp_path: pathlib.Path) -> None:
    """delete_user does not affect other users' profiles."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))

    profile1 = ExperienceProfile(
        user_id="user1",
        age_group=AgeGroup.ADULT_31_60,
        goals=["goal1"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=InfoStyle.DETAILED,
        layout=LayoutType.DASHBOARD,
        theme=ThemeType.STANDARD,
    )
    repo.save_profile(profile1)

    profile2 = ExperienceProfile(
        user_id="user2",
        age_group=AgeGroup.SENIOR_60_PLUS,
        goals=["goal2"],
        tech_comfort=TechComfort.NEW,
        info_style=InfoStyle.VISUAL,
        layout=LayoutType.GUIDED_JOURNEY,
        theme=ThemeType.LARGER_TEXT,
    )
    repo.save_profile(profile2)

    repo.delete_user("user1")

    assert repo.get_profile("user1") is None
    user2_profile = repo.get_profile("user2")
    assert user2_profile is not None
    assert user2_profile.user_id == "user2"


def test_profile_with_child_age_group(tmp_path: pathlib.Path) -> None:
    """Profile can be created for child age group."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))
    profile = ExperienceProfile(
        user_id="child_user",
        age_group=AgeGroup.CHILD_7_12,
        goals=["attention_training"],
        tech_comfort=TechComfort.SOME_EXPERIENCE,
        info_style=InfoStyle.SHORT_SIMPLE,
        layout=LayoutType.GUIDED_JOURNEY,
        theme=ThemeType.SOFTER_COLORS,
        guidance_level=GuidanceLevel.MORE,
    )
    repo.save_profile(profile)
    loaded = repo.get_profile("child_user")
    assert loaded is not None
    assert loaded.age_group == AgeGroup.CHILD_7_12
    assert loaded.guidance_level == GuidanceLevel.MORE


def test_profile_without_guidance_level(tmp_path: pathlib.Path) -> None:
    """Profile can be saved and retrieved without guidance_level."""
    repo = SQLiteExperienceProfileRepository(str(tmp_path / "test.db"))
    profile = ExperienceProfile(
        user_id="no_guidance",
        age_group=AgeGroup.YOUNG_ADULT_18_30,
        goals=["explore"],
        tech_comfort=TechComfort.VERY_COMFORTABLE,
        info_style=InfoStyle.CONVERSATIONAL,
        layout=LayoutType.CONVERSATION_FIRST,
        theme=ThemeType.BRIGHTER_COLORS,
    )
    repo.save_profile(profile)
    loaded = repo.get_profile("no_guidance")
    assert loaded is not None
    assert loaded.guidance_level is None
