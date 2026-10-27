"""Unit tests for Streamlit IOI API helpers."""

from __future__ import annotations

from typing import Any

from coglayer.ui.api import (
    get_assessment_session,
    get_assessment_sessions,
    get_ioi_score,
    record_ioi_event,
)


class _Response:
    def __init__(self, payload: object, status_code: int = 201) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = "response"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self) -> Any:
        return self._payload


def test_record_ioi_event_uses_expected_api_shape(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> _Response:
        captured.update({"url": url, "json": json, "timeout": timeout})
        return _Response({"status": "recorded"})

    monkeypatch.setattr("coglayer.ui.api.httpx.post", fake_post)

    result = record_ioi_event("http://api", {"event_id": "event-1"})

    assert result == {"status": "recorded"}
    assert captured["url"] == "http://api/v1/assessment/ioi/events"
    assert captured["json"]["event_id"] == "event-1"


def test_get_assessment_session_checks_requested_owner(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> _Response:
        captured.update({"url": url, "params": params, "timeout": timeout})
        return _Response(
            {"session_id": "session-1", "user_id": "user-1", "status": "pending"},
            status_code=200,
        )

    monkeypatch.setattr("coglayer.ui.api.httpx.get", fake_get)

    assert get_assessment_session("http://api", "user-1", "session-1")["session_id"] == "session-1"
    assert captured["url"] == "http://api/v1/assessment/sessions/session-1"
    assert captured["params"] == {"user_id": "user-1"}


def test_get_assessment_sessions_returns_resumable_sessions(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> _Response:
        captured.update({"url": url, "params": params, "timeout": timeout})
        return _Response(
            [{"session_id": "session-1", "user_id": "user-1", "status": "pending"}],
            status_code=200,
        )

    monkeypatch.setattr("coglayer.ui.api.httpx.get", fake_get)

    assert get_assessment_sessions("http://api", "user-1") == [
        {"session_id": "session-1", "user_id": "user-1", "status": "pending"}
    ]
    assert captured["url"] == "http://api/v1/assessment/sessions"
    assert captured["params"] == {"user_id": "user-1"}


def test_get_ioi_score_returns_object(monkeypatch: Any) -> None:
    def fake_get(url: str, *, params: dict[str, str], timeout: float) -> _Response:
        assert url == "http://api/v1/assessment/ioi/user-1/score"
        assert params == {"session_id": "session-1"}
        return _Response({"status": "INSUFFICIENT_EVIDENCE"}, status_code=200)

    monkeypatch.setattr("coglayer.ui.api.httpx.get", fake_get)

    assert get_ioi_score("http://api", "user-1", "session-1") == {"status": "INSUFFICIENT_EVIDENCE"}
