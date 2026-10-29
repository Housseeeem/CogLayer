"""Unit tests for the adaptation mapper.

Tests cover:
- Coach adaptation config across all age groups (child, teen, young_adult, adult, senior).
- Guidance level adaptation for task selection.
- Distinct system prompts for teen, adult, senior.
- Child free chat blocking and predefined responses.
- Minor privacy protection (no conversation storage for child and teen).
- Non-clinical vocabulary verification (forbidden words never present).
"""

from __future__ import annotations

from coglayer.coach.coach import FORBIDDEN_WORDS_PATTERN
from coglayer.core.adaptation import (
    CHILD_ALLOWED_INPUTS,
    CHILD_COACH_RESPONSES,
    CHILD_RESPONSE_MAP,
    get_coach_adaptation,
    get_selector_adaptation,
    get_ui_adaptation,
)
from coglayer.core.models import (
    AgeGroup,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)


def _make_profile(
    age_group: AgeGroup = AgeGroup.ADULT_31_60,
    guidance_level: GuidanceLevel | None = None,
    info_style: InfoStyle = InfoStyle.CONVERSATIONAL,
    theme: ThemeType = ThemeType.STANDARD,
    layout: LayoutType = LayoutType.GUIDED_JOURNEY,
) -> ExperienceProfile:
    return ExperienceProfile(
        user_id="test_user",
        age_group=age_group,
        goals=["improve_focus"],
        tech_comfort=TechComfort.COMFORTABLE,
        info_style=info_style,
        layout=layout,
        theme=theme,
        guidance_level=guidance_level,
    )


def test_coach_adaptation_child() -> None:
    """Child profile blocks free chat, disables storage, and provides predefined responses."""
    profile = _make_profile(age_group=AgeGroup.CHILD_7_12)
    config = get_coach_adaptation(profile)

    assert config.allow_free_chat is False
    assert config.store_conversation is False
    assert len(config.predefined_responses) == 6
    assert "Great effort!" in config.predefined_responses
    assert "Let's try another game" in config.predefined_responses
    assert "Time for a short break" in config.predefined_responses
    assert "Ask a grown-up to help you" in config.predefined_responses
    assert set(CHILD_COACH_RESPONSES).issubset(set(config.allowed_child_messages))

    # Test predefined reply helper
    reply = config.get_predefined_reply("How am I doing?")
    assert "Great effort!" in reply


def test_coach_adaptation_teen() -> None:
    """Teen profile permits free chat, disables storage, and uses strict prompt."""
    profile = _make_profile(age_group=AgeGroup.TEEN_13_17)
    config = get_coach_adaptation(profile)

    assert config.allow_free_chat is True
    assert config.store_conversation is False
    assert len(config.suggested_responses) >= 3

    # Check strict prompt rules
    prompt = config.system_prompt.lower()
    assert "positive" in prompt or "encouraging" in prompt
    assert "short" in prompt
    assert "sensitive" in prompt
    assert "personal information" in prompt or "identifiable" in prompt


def test_coach_adaptation_young_adult_and_adult() -> None:
    """Adult profile permits free chat, enables storage, and uses standard supportive prompt."""
    adult_profile = _make_profile(age_group=AgeGroup.ADULT_31_60)
    config = get_coach_adaptation(adult_profile)

    assert config.allow_free_chat is True
    assert config.store_conversation is True
    assert "supportive cognitive coach" in config.system_prompt.lower()

    young_profile = _make_profile(age_group=AgeGroup.YOUNG_ADULT_18_30)
    young_config = get_coach_adaptation(young_profile)
    assert young_config.allow_free_chat is True
    assert young_config.store_conversation is True


def test_coach_adaptation_senior() -> None:
    """Senior profile uses clear sentences and avoids technical jargon."""
    profile = _make_profile(age_group=AgeGroup.SENIOR_60_PLUS)
    config = get_coach_adaptation(profile)

    assert config.allow_free_chat is True
    assert config.store_conversation is True
    prompt = config.system_prompt.lower()
    assert "clear" in prompt
    assert "short" in prompt
    assert "jargon" in prompt


def test_prompts_are_distinct_between_groups() -> None:
    """Teen, adult, and senior prompts are distinct."""
    teen_config = get_coach_adaptation(_make_profile(age_group=AgeGroup.TEEN_13_17))
    adult_config = get_coach_adaptation(_make_profile(age_group=AgeGroup.ADULT_31_60))
    senior_config = get_coach_adaptation(_make_profile(age_group=AgeGroup.SENIOR_60_PLUS))

    assert teen_config.system_prompt != adult_config.system_prompt
    assert senior_config.system_prompt != adult_config.system_prompt
    assert teen_config.system_prompt != senior_config.system_prompt


def test_info_style_modifies_prompt() -> None:
    """InfoStyle appends specific style guidance to the coach prompt."""
    detailed = get_coach_adaptation(
        _make_profile(age_group=AgeGroup.ADULT_31_60, info_style=InfoStyle.DETAILED)
    )
    short = get_coach_adaptation(
        _make_profile(age_group=AgeGroup.ADULT_31_60, info_style=InfoStyle.SHORT_SIMPLE)
    )
    visual = get_coach_adaptation(
        _make_profile(age_group=AgeGroup.ADULT_31_60, info_style=InfoStyle.VISUAL)
    )

    assert (
        "detailed" in detailed.system_prompt.lower() or "thorough" in detailed.system_prompt.lower()
    )
    assert "brief" in short.system_prompt.lower()
    assert "visual" in visual.system_prompt.lower() or "metaphor" in visual.system_prompt.lower()


def test_no_forbidden_words_in_prompts_and_replies() -> None:
    """No prompt or predefined response contains forbidden clinical words."""
    for age in AgeGroup:
        for style in InfoStyle:
            cfg = get_coach_adaptation(_make_profile(age_group=age, info_style=style))
            assert not FORBIDDEN_WORDS_PATTERN.search(cfg.system_prompt)
            for resp in cfg.predefined_responses:
                assert not FORBIDDEN_WORDS_PATTERN.search(resp)
            for resp in cfg.suggested_responses:
                assert not FORBIDDEN_WORDS_PATTERN.search(resp)

    for msg in CHILD_ALLOWED_INPUTS:
        assert not FORBIDDEN_WORDS_PATTERN.search(msg)
    for reply in CHILD_RESPONSE_MAP.values():
        assert not FORBIDDEN_WORDS_PATTERN.search(reply)


def test_selector_adaptation_guidance_levels() -> None:
    """Selector adaptation config correctly maps each guidance level."""
    more_cfg = get_selector_adaptation(GuidanceLevel.MORE)
    assert more_cfg.guidance_level == GuidanceLevel.MORE
    assert more_cfg.target_game_count <= 2
    assert more_cfg.prefer_introductory_first is True
    assert more_cfg.allow_challenge is False

    some_cfg = get_selector_adaptation(GuidanceLevel.SOME)
    assert some_cfg.guidance_level == GuidanceLevel.SOME
    assert some_cfg.target_game_count == 3
    assert some_cfg.allow_challenge is True

    minimal_cfg = get_selector_adaptation(GuidanceLevel.MINIMAL)
    assert minimal_cfg.guidance_level == GuidanceLevel.MINIMAL
    assert minimal_cfg.target_game_count >= 3
    assert minimal_cfg.allow_challenge is True


def test_ui_adaptation_layout_and_theme() -> None:
    """UI adaptation maps theme CSS and default page."""
    profile_larger = _make_profile(theme=ThemeType.LARGER_TEXT, layout=LayoutType.DASHBOARD)
    cfg_larger = get_ui_adaptation(profile_larger)
    assert "font-size" in cfg_larger.custom_css
    assert cfg_larger.default_page == "profile"

    profile_contrast = _make_profile(
        theme=ThemeType.HIGH_CONTRAST,
        layout=LayoutType.CONVERSATION_FIRST,
    )
    cfg_contrast = get_ui_adaptation(profile_contrast)
    assert "#000000" in cfg_contrast.custom_css
    assert cfg_contrast.default_page == "coach"
