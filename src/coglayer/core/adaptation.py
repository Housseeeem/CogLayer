"""Personalized experience adaptation pure functions and data models.

Transforms an ExperienceProfile into concrete adaptation configurations
for the coach, task selector, and presentation layers.

Non-clinical: contains no clinical terminology or diagnostic concepts.
Forbidden words: diagnosis, disorder, deficit, impairment, IQ, patient.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from coglayer.core.models import (
    AgeGroup,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    ThemeType,
)

__all__ = [
    "ADULT_SUGGESTED_RESPONSES",
    "ADULT_SYSTEM_PROMPT",
    "CHILD_ALLOWED_INPUTS",
    "CHILD_COACH_RESPONSES",
    "CHILD_RESPONSE_MAP",
    "SENIOR_SYSTEM_PROMPT",
    "TEEN_SUGGESTED_RESPONSES",
    "TEEN_SYSTEM_PROMPT",
    "CoachAdaptationConfig",
    "SelectorAdaptationConfig",
    "UIAdaptationConfig",
    "get_coach_adaptation",
    "get_selector_adaptation",
    "get_ui_adaptation",
]

# ---------------------------------------------------------------------------
# Predefined child coach messages (hardcoded, encouraging, non-clinical)
# ---------------------------------------------------------------------------

CHILD_COACH_RESPONSES: Final[tuple[str, ...]] = (
    "Great effort!",
    "Let's try another game",
    "Time for a short break",
    "Ask a grown-up to help you",
    "Keep up the great work!",
    "You are doing wonderfully!",
)

CHILD_ALLOWED_INPUTS: Final[tuple[str, ...]] = (
    "How am I doing?",
    "Let's try another game",
    "Time for a short break",
    "Ask a grown-up to help you",
    "Keep up the great work!",
    "You are doing wonderfully!",
    "What should I play next?",
    "I need a pause",
    "Can you give me a tip?",
    *CHILD_COACH_RESPONSES,
)

CHILD_RESPONSE_MAP: Final[dict[str, str]] = {
    "Great effort!": "Great effort! You are making wonderful progress on your activities.",
    "Let's try another game": "Let's try another game! Pick one that looks fun to you.",
    "Time for a short break": (
        "Time for a short break. Rest your eyes and come back whenever you are ready!"
    ),
    "Ask a grown-up to help you": (
        "Ask a grown-up to help you if you are feeling stuck or need guidance."
    ),
    "Keep up the great work!": "Keep up the great work! You are doing amazingly well today.",
    "You are doing wonderfully!": "You are doing wonderfully! Have fun with your next activity.",
    "How am I doing?": "Great effort! You did a fantastic job focusing today.",
    "What should I play next?": (
        "Let's try another game, or take a short break if you need to rest."
    ),
    "I need a pause": "Time for a short break. Relax for a few minutes and drink some water!",
    "Can you give me a tip?": (
        "Ask a grown-up to help you if you need a hand, or try another fun activity!"
    ),
}

# ---------------------------------------------------------------------------
# Suggested responses for teen, adult, senior
# ---------------------------------------------------------------------------

TEEN_SUGGESTED_RESPONSES: Final[tuple[str, ...]] = (
    "How did I do on today's tasks?",
    "What game should I try next?",
    "Tips for maintaining daily focus",
)

ADULT_SUGGESTED_RESPONSES: Final[tuple[str, ...]] = (
    "Review my session summary",
    "What cognitive skill can I exercise next?",
    "Tips for sustaining daily focus",
)

# ---------------------------------------------------------------------------
# System prompts by age group
# ---------------------------------------------------------------------------

TEEN_SYSTEM_PROMPT: Final[str] = (
    "You are a supportive cognitive coach for a teenager. "
    "Maintain an encouraging, positive tone with short and clear sentences. "
    "Do not discuss sensitive topics. "
    "Never ask for personal information or identifiable details. "
    "Do not rank dimensions against each other and do not produce a global score. "
    "Keep responses concise, clear, and empowering."
)

ADULT_SYSTEM_PROMPT: Final[str] = (
    "You are a supportive cognitive coach. Use the following notes to write "
    "friendly, encouraging feedback for the user. Do not rank dimensions "
    "against each other and do not produce a global score. Keep it concise."
)

SENIOR_SYSTEM_PROMPT: Final[str] = (
    "You are a supportive cognitive coach for an older adult. "
    "Use clear, short, and respectful sentences with no technical jargon. "
    "Focus on practical cognitive strengths and gentle encouragement. "
    "Do not rank dimensions against each other and do not produce a global score. "
    "Keep responses concise, clear, and reassuring."
)

# ---------------------------------------------------------------------------
# Information style modifiers (only style guidance, never cognitive estimates)
# ---------------------------------------------------------------------------

INFO_STYLE_PROMPT_MODIFIERS: Final[dict[InfoStyle, str]] = {
    InfoStyle.VISUAL: "Use descriptive visual metaphors and vivid language to illustrate ideas.",
    InfoStyle.STEP_BY_STEP: "Organize suggestions into clear, structured, step-by-step points.",
    InfoStyle.SHORT_SIMPLE: "Keep answers very brief, direct, and straightforward.",
    InfoStyle.DETAILED: (
        "Provide thorough, in-depth explanations with additional contextual detail."
    ),
    InfoStyle.CONVERSATIONAL: "Adopt an approachable, warm, and conversational tone.",
}


class CoachAdaptationConfig(BaseModel):
    """Configuration for adapting coach interactions to a user's experience profile."""

    age_group: AgeGroup
    allow_free_chat: bool
    store_conversation: bool
    system_prompt: str
    predefined_responses: list[str] = Field(default_factory=list)
    allowed_child_messages: list[str] = Field(default_factory=list)
    suggested_responses: list[str] = Field(default_factory=list)

    def get_predefined_reply(self, message: str) -> str:
        """Return a predefined encouraging response matching the message or a default."""
        return CHILD_RESPONSE_MAP.get(
            message.strip(),
            "Great effort! You are doing wonderfully, keep it up!",
        )


class SelectorAdaptationConfig(BaseModel):
    """Configuration for adapting task selection to guidance level."""

    guidance_level: GuidanceLevel
    target_game_count: int
    prefer_introductory_first: bool
    allow_challenge: bool
    factors_used: list[str] = Field(default_factory=list)


class UIAdaptationConfig(BaseModel):
    """Configuration for adapting UI theme and layout."""

    theme_type: ThemeType
    layout_type: LayoutType
    info_style: InfoStyle
    custom_css: str
    default_page: str
    is_compact_coach: bool


def get_coach_adaptation(profile: ExperienceProfile | None) -> CoachAdaptationConfig:
    """Map an ExperienceProfile to coach adaptation settings.

    Parameters
    ----------
    profile : ExperienceProfile | None
        User's profile, or None for default adult behavior.

    Returns
    -------
    CoachAdaptationConfig
        Settings controlling free chat allowance, storage persistence, system prompt,
        predefined options, and suggested responses.
    """
    if profile is None:
        return CoachAdaptationConfig(
            age_group=AgeGroup.ADULT_31_60,
            allow_free_chat=True,
            store_conversation=True,
            system_prompt=ADULT_SYSTEM_PROMPT,
            predefined_responses=[],
            allowed_child_messages=[],
            suggested_responses=list(ADULT_SUGGESTED_RESPONSES),
        )

    # Style modifier from info_style
    style_modifier = INFO_STYLE_PROMPT_MODIFIERS.get(profile.info_style, "")
    style_suffix = f"\nStyle preference: {style_modifier}" if style_modifier else ""

    if profile.age_group == AgeGroup.CHILD_7_12:
        return CoachAdaptationConfig(
            age_group=AgeGroup.CHILD_7_12,
            allow_free_chat=False,
            store_conversation=False,
            system_prompt="Child mode: predefined responses only; LLM calls disabled.",
            predefined_responses=list(CHILD_COACH_RESPONSES),
            allowed_child_messages=list(CHILD_ALLOWED_INPUTS),
            suggested_responses=list(CHILD_COACH_RESPONSES),
        )

    if profile.age_group == AgeGroup.TEEN_13_17:
        return CoachAdaptationConfig(
            age_group=AgeGroup.TEEN_13_17,
            allow_free_chat=True,
            store_conversation=False,
            system_prompt=f"{TEEN_SYSTEM_PROMPT}{style_suffix}",
            predefined_responses=[],
            allowed_child_messages=[],
            suggested_responses=list(TEEN_SUGGESTED_RESPONSES),
        )

    if profile.age_group == AgeGroup.SENIOR_60_PLUS:
        return CoachAdaptationConfig(
            age_group=AgeGroup.SENIOR_60_PLUS,
            allow_free_chat=True,
            store_conversation=True,
            system_prompt=f"{SENIOR_SYSTEM_PROMPT}{style_suffix}",
            predefined_responses=[],
            allowed_child_messages=[],
            suggested_responses=list(ADULT_SUGGESTED_RESPONSES),
        )

    # Young adult and adult
    return CoachAdaptationConfig(
        age_group=profile.age_group,
        allow_free_chat=True,
        store_conversation=True,
        system_prompt=f"{ADULT_SYSTEM_PROMPT}{style_suffix}",
        predefined_responses=[],
        allowed_child_messages=[],
        suggested_responses=list(ADULT_SUGGESTED_RESPONSES),
    )


def get_selector_adaptation(
    guidance_level: GuidanceLevel | None,
    default_game_count: int = 3,
) -> SelectorAdaptationConfig:
    """Map guidance level to selector adaptation configuration."""
    level = guidance_level or GuidanceLevel.SOME
    if level == GuidanceLevel.MORE:
        return SelectorAdaptationConfig(
            guidance_level=GuidanceLevel.MORE,
            target_game_count=min(default_game_count, 2),
            prefer_introductory_first=True,
            allow_challenge=False,
            factors_used=["guidance_scaffolding_more"],
        )
    if level == GuidanceLevel.MINIMAL:
        return SelectorAdaptationConfig(
            guidance_level=GuidanceLevel.MINIMAL,
            target_game_count=max(default_game_count, 3),
            prefer_introductory_first=False,
            allow_challenge=True,
            factors_used=["guidance_autonomy_minimal"],
        )
    return SelectorAdaptationConfig(
        guidance_level=GuidanceLevel.SOME,
        target_game_count=default_game_count,
        prefer_introductory_first=False,
        allow_challenge=True,
        factors_used=["guidance_balanced_some"],
    )


def get_ui_adaptation(profile: ExperienceProfile | None) -> UIAdaptationConfig:
    """Map ExperienceProfile to UI presentation settings and CSS injection."""
    theme = profile.theme if profile is not None else ThemeType.STANDARD
    layout = profile.layout if profile is not None else LayoutType.GUIDED_JOURNEY
    info = profile.info_style if profile is not None else InfoStyle.CONVERSATIONAL

    css_rules: list[str] = []
    if theme == ThemeType.LARGER_TEXT:
        css_rules.append(
            """
            html, body, [class*="css"], p, span, div, button {
                font-size: 1.15rem !important;
                line-height: 1.6 !important;
            }
            h1 { font-size: 2.2rem !important; }
            h2 { font-size: 1.8rem !important; }
            h3 { font-size: 1.4rem !important; }
            """
        )
    elif theme == ThemeType.HIGH_CONTRAST:
        css_rules.append(
            """
            body, .stApp {
                background-color: #000000 !important;
                color: #ffffff !important;
            }
            p, span, div, label {
                color: #ffffff !important;
            }
            button, .stButton>button {
                border: 2px solid #ffffff !important;
                background-color: #1a1a1a !important;
                color: #ffffff !important;
                font-weight: bold !important;
            }
            """
        )
    elif theme == ThemeType.SOFTER_COLORS:
        css_rules.append(
            """
            .stApp {
                background-color: #f7f9f8 !important;
                color: #2d3748 !important;
            }
            """
        )
    elif theme == ThemeType.BRIGHTER_COLORS:
        css_rules.append(
            """
            .stApp {
                background-color: #ffffff !important;
            }
            button, .stButton>button {
                border-radius: 8px !important;
                font-weight: 600 !important;
            }
            """
        )

    default_page_map = {
        LayoutType.GUIDED_JOURNEY: "lab",
        LayoutType.DASHBOARD: "profile",
        LayoutType.CONVERSATION_FIRST: "coach",
        LayoutType.MINIMAL: "lab",
    }
    default_page = default_page_map.get(layout, "lab")
    is_compact = info in (InfoStyle.SHORT_SIMPLE, InfoStyle.STEP_BY_STEP)

    return UIAdaptationConfig(
        theme_type=theme,
        layout_type=layout,
        info_style=info,
        custom_css="".join(css_rules).strip(),
        default_page=default_page,
        is_compact_coach=is_compact,
    )
