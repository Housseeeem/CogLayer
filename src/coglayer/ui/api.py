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
