"""Shared presentation for the CogLayer learning workspace."""

from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path


@lru_cache(maxsize=1)
def design_css() -> str:
    """Return the bundled workspace stylesheet without external resources."""
    return Path(__file__).with_name("assets").joinpath("design.css").read_text(encoding="utf-8")


def _icon(kind: str) -> str:
    paths = {
        "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
        "memory": '<path d="M12 6C9 4 6 4 3 5v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Zm0 0v14"/>',
        "spark": '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
    }
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{paths[kind]}</svg>'
    )


def brand_html() -> str:
    """Return the workspace wordmark and its decorative mark."""
    return (
        '<div class="cog-brand"><span class="cog-brand-mark" aria-hidden="true">'
        "<i></i><i></i><i></i></span>coglayer<span>.</span></div>"
        '<p class="cog-sidebar-eyebrow">YOUR LEARNING SPACE</p>'
    )


def workspace_header_html(page_label: str) -> str:
    """Return an escaped breadcrumb and the workspace context."""
    return (
        '<div class="cog-topbar"><div class="cog-breadcrumb">My workspace'
        f'<span aria-hidden="true">/</span><strong>{escape(page_label)}</strong></div>'
        '<span class="cog-workspace-badge"><i aria-hidden="true"></i>'
        "Learning workspace</span></div>"
    )


def sidebar_note_html() -> str:
    """Return a supportive sidebar note without claims about user performance."""
    return (
        '<div class="cog-sidebar-note"><span aria-hidden="true">✧</span>'
        "<strong>A little practice.<br>A little more possibility.</strong>"
        "<p>Your pace. Your journey.</p></div>"
    )


def footer_html() -> str:
    """Return the visible educational context for every screen."""
    return (
        '<div class="cog-footer"><span>Educational coaching · Non-clinical</span>'
        "<span>Your pace. Your journey.</span></div>"
    )


def lab_hero_html(*, completed: int, total: int) -> str:
    """Return daily-plan progress from actual activity counts (nonnegative integers)."""
    total = max(0, total)
    completed = max(0, min(completed, total))
    if total:
        progress = (
            f'<div class="cog-plan-progress" role="progressbar" '
            f'aria-label="Daily activities complete" aria-valuemin="0" '
            f'aria-valuemax="{total}" aria-valuenow="{completed}">'
            f'<span style="width:{completed / total * 100:.1f}%"></span></div>'
            f'<p class="cog-plan-count">{completed} of {total} activities complete</p>'
        )
    else:
        progress = '<p class="cog-plan-count">No activities recommended yet</p>'
    return (
        '<section class="cog-hero" aria-label="Your daily learning session">'
        '<div class="cog-hero-copy"><span class="cog-eyebrow">YOUR NEXT SMALL STEP</span>'
        "<h2>Get curious.<br>Find your focus.</h2>"
        "<p>A few thoughtful moments to explore how you learn, think, and respond.</p>"
        f'{progress}</div><div class="cog-orbits" aria-hidden="true">'
        '<span class="cog-orbit"></span><span class="cog-orbit"></span>'
        '<span class="cog-orbit"></span><span class="cog-orb">'
        f'{_icon("spark")}</span><span class="cog-orbit-bead cog-bead-one">'
        f'{_icon("memory")}</span><span class="cog-orbit-bead cog-bead-two">'
        f"{_icon('target')}</span></div></section>"
    )


def activity_card_html(
    *, task_id: str, label: str, dimension: str, level: str, description: str
) -> str:
    """Return an activity card heading with escaped display text."""
    kind, color = {
        "go_no_go": ("target", "mint"),
        "stroop": ("spark", "peach"),
        "perception_lab": ("spark", "peach"),
    }.get(task_id, ("memory", "lavender"))
    return (
        '<div class="cog-activity-heading">'
        f'<span class="cog-activity-icon cog-{color}">{_icon(kind)}</span>'
        f'<span class="cog-activity-level">{escape(level)}</span>'
        f'<h3>{escape(label)}</h3><p class="cog-activity-domain">{escape(dimension)}</p>'
        f'<p class="cog-activity-description">{escape(description)}</p></div>'
    )


def interval_bar_html(*, lower: float, upper: float, mean: float) -> str:
    """Visualize existing [0, 1] interval values; accessible labels remain native widgets."""
    return (
        '<div class="cog-interval" aria-hidden="true" '
        f'style="--lower:{lower * 100:.1f}%;--range:{(upper - lower) * 100:.1f}%;'
        f'--mean:{mean * 100:.1f}%"><span></span><i></i></div>'
    )


def theme_overrides(theme: str | None) -> str:
    """Keep the workspace palette compatible with existing display preferences."""
    if theme == "high_contrast":
        return (
            ":root { --cog-bg:#000000; --cog-surface:#141414; --cog-ink:#ffffff;"
            " --cog-muted:#e3e3e3; --cog-line:#ffffff; --cog-soft:#242424; }"
            ".cog-hero,.cog-activity-icon,.cog-workspace-badge,.cog-coach-intro {"
            " background:#242424 !important; color:#ffffff !important; }"
            ".cog-hero h2,.cog-hero p,.cog-eyebrow { color:#ffffff !important; }"
            "[data-testid='stSidebar'] { background:#000000 !important; }"
            "[data-testid='stSidebar'] [role='radiogroup'] > label:has(input:checked) {"
            " background:#242424 !important; outline:1px solid #ffffff; }"
        )
    if theme == "softer_colors":
        return ":root { --cog-bg:#f7f9f8; --cog-ink:#2d3748; }"
    if theme == "brighter_colors":
        return ":root { --cog-bg:#ffffff; }"
    return ""


def activity_frame_html(source: str) -> str:
    """Style activity surroundings while preserving original stimuli and scripts."""
    if 'id="coglayer-activity-style"' in source:
        return source
    style = (
        '<style id="coglayer-activity-style">'
        "body { background:#ffffff; color:#272639; font-family:'Segoe UI',Arial,sans-serif; }"
        "#status-msg,#progress { color:#77788c; }"
        "#action-btn { background:#302d48; border-radius:10px; box-shadow:none; }"
        "#action-btn:hover { background:#49415f; }"
        "button:focus-visible,input:focus-visible { outline:3px solid #9b7fe5;"
        " outline-offset:4px; }"
        "</style>"
    )
    if "</head>" in source:
        return source.replace("</head>", f"{style}</head>", 1)
    return style + source
