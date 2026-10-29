"""Unit tests for UI theme and presentation adaptation.

Tests verify:
- Theme CSS generation for all ThemeType options.
- CSS injection into Streamlit with st.markdown(..., unsafe_allow_html=True).
- Presentation adaptation for info_style (concise vs detailed captions).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from coglayer.core.adaptation import get_theme_css
from coglayer.core.models import ThemeType
from coglayer.ui.app import _apply_user_theme
from coglayer.ui.page_views.coach import render_coach_page


def test_theme_css_rules_all_variants() -> None:
    """CSS rules are properly generated for each theme type."""
    larger_css = get_theme_css(ThemeType.LARGER_TEXT)
    assert "font-size" in larger_css
    assert "1.15rem" in larger_css

    contrast_css = get_theme_css(ThemeType.HIGH_CONTRAST)
    assert "#000000" in contrast_css
    assert "#ffffff" in contrast_css

    softer_css = get_theme_css(ThemeType.SOFTER_COLORS)
    assert "#f7f9f8" in softer_css

    brighter_css = get_theme_css(ThemeType.BRIGHTER_COLORS)
    assert "#ffffff" in brighter_css

    standard_css = get_theme_css(ThemeType.STANDARD)
    assert standard_css == ""

    # String input support
    assert "font-size" in get_theme_css("larger_text")
    assert get_theme_css(None) == ""


@patch("coglayer.ui.app.httpx.get")
@patch("coglayer.ui.app.st")
def test_apply_user_theme_injects_css(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """_apply_user_theme queries the profile and injects CSS with unsafe_allow_html=True."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"theme": "high_contrast"},
    )

    _apply_user_theme("http://testserver", "user_contrast")

    assert mock_st.markdown.called
    call_args = mock_st.markdown.call_args
    assert "<style>" in call_args[0][0]
    assert "#000000" in call_args[0][0]
    assert call_args[1].get("unsafe_allow_html") is True


@patch("coglayer.ui.app.httpx.get")
@patch("coglayer.ui.app.st")
def test_apply_user_theme_standard_no_injection(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Standard theme does not inject extra CSS styles."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"theme": "standard"},
    )

    _apply_user_theme("http://testserver", "user_standard")

    assert not mock_st.markdown.called


@patch("coglayer.ui.page_views.coach._fetch_experience_profile")
@patch("coglayer.ui.page_views.coach.st")
def test_coach_page_adapts_to_info_style(mock_st: MagicMock, mock_fetch_profile: MagicMock) -> None:
    """Coach page displays concise vs detailed indicators based on info_style."""
    mock_st.session_state = {
        "conversation_id": "test_conv",
        "chat_messages": [],
    }
    mock_st.chat_input.return_value = None
    mock_st.columns.return_value = (MagicMock(), MagicMock())

    # Test short_simple
    mock_fetch_profile.return_value = {
        "age_group": "adult_31_60",
        "info_style": "short_simple",
    }
    render_coach_page("http://testserver", "user_short")
    assert any("Concise coaching mode" in str(call) for call in mock_st.caption.call_args_list)

    # Test detailed
    mock_fetch_profile.return_value = {
        "age_group": "adult_31_60",
        "info_style": "detailed",
    }
    render_coach_page("http://testserver", "user_detailed")
    assert any(
        "Comprehensive cognitive coaching" in str(call) for call in mock_st.caption.call_args_list
    )
