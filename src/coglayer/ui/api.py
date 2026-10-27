"""Small HTTP helpers used by the Streamlit UI."""

from __future__ import annotations

from typing import Any

import httpx


def get_decision(api_url: str, session_id: str) -> dict[str, Any]:
    """Fetch the decision for an assessment session."""
    response = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}/decision", timeout=5.0)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Assessment decision response must be an object.")
    return data


def get_assessment_session(
    api_url: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Fetch one assessment session after checking its requested owner."""
    response = httpx.get(
        f"{api_url}/v1/assessment/sessions/{session_id}",
        params={"user_id": user_id},
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Assessment session response must be an object.")
    return data


def get_assessment_sessions(api_url: str, user_id: str) -> list[dict[str, Any]]:
    """Fetch resumable assessment sessions owned by the requested user."""
    response = httpx.get(
        f"{api_url}/v1/assessment/sessions",
        params={"user_id": user_id},
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("Assessment sessions response must be a list of objects.")
    return data


def record_ioi_event(api_url: str, event: dict[str, Any]) -> dict[str, Any]:
    """Record one structured IOI event through the assessment API."""
    response = httpx.post(
        f"{api_url}/v1/assessment/ioi/events",
        json=event,
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("IOI event response must be an object.")
    return data


def get_ioi_score(api_url: str, user_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Fetch the current IOI score snapshot."""
    params = {} if session_id is None else {"session_id": session_id}
    response = httpx.get(
        f"{api_url}/v1/assessment/ioi/{user_id}/score",
        params=params,
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("IOI score response must be an object.")
    return data


def get_daily_plan(
    api_url: str,
    user_id: str,
    plan_date: str | None = None,
    target_game_count: int = 3,
    force_regenerate: bool = False,
    subjective_feedback: str | None = None,
) -> dict[str, Any]:
    """Fetch or generate the daily cognitive game plan for a user."""
    params: dict[str, Any] = {
        "user_id": user_id,
        "target_game_count": target_game_count,
        "force_regenerate": force_regenerate,
    }
    if plan_date is not None:
        params["plan_date"] = plan_date
    if subjective_feedback is not None:
        params["subjective_feedback"] = subjective_feedback

    response = httpx.get(
        f"{api_url}/v1/assessment/daily-plan/{user_id}",
        params=params,
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Daily plan response must be an object.")
    return data


def update_daily_plan_status(
    api_url: str,
    user_id: str,
    plan_date: str,
    status: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Update lifecycle status of a daily plan."""
    payload = {
        "plan_date": plan_date,
        "status": status,
        "session_id": session_id,
    }
    response = httpx.patch(
        f"{api_url}/v1/assessment/daily-plan/{user_id}/status",
        params={"user_id": user_id},
        json=payload,
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Daily plan status response must be an object.")
    return data
