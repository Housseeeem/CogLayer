"""Unit tests for ConsentService.

Tests: record_consent, revoke_consent, has_consented lifecycle.
Also covers test_ac_new_session_after_consent (permission-check simulation).

Requirements: R-001.1, R-001.4, REQ-011 test_ac_new_session_after_consent
"""

from __future__ import annotations

from coglayer.core.models import ConsentRecord
from coglayer.privacy.consent import ConsentService

# ---------------------------------------------------------------------------
# In-memory stub for ConsentRepository
# ---------------------------------------------------------------------------


class _InMemoryConsentRepo:
    """Dict-backed consent store for unit tests.  Not thread-safe."""

    def __init__(self) -> None:
        self._store: dict[str, ConsentRecord] = {}

    def save_consent(self, record: ConsentRecord) -> None:
        self._store[record.user_id] = record

    def get_consent(self, user_id: str) -> ConsentRecord | None:
        return self._store.get(user_id)

    def delete_consent(self, user_id: str) -> None:
        self._store.pop(user_id, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> ConsentService:
    return ConsentService(_InMemoryConsentRepo())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_new_user_has_not_consented() -> None:
    """A fresh user has_consented returns False."""
    svc = _make_service()
    assert svc.has_consented("alice") is False


def test_has_consented_after_record() -> None:
    """After record_consent, has_consented returns True."""
    svc = _make_service()
    record = svc.record_consent("alice")
    assert svc.has_consented("alice") is True
    assert record.user_id == "alice"
    assert record.revoked_at is None


def test_has_not_consented_after_revoke() -> None:
    """After revoke_consent, has_consented returns False."""
    svc = _make_service()
    svc.record_consent("alice")
    svc.revoke_consent("alice")
    assert svc.has_consented("alice") is False


def test_record_consent_returns_timezone_aware_datetime() -> None:
    """consented_at is a timezone-aware datetime (UTC)."""
    import datetime

    svc = _make_service()
    record = svc.record_consent("bob")
    assert record.consented_at.tzinfo is not None
    assert record.consented_at.utcoffset() == datetime.timedelta(0)


def test_revoke_idempotent_when_no_record() -> None:
    """revoke_consent on a user with no record is a no-op."""
    svc = _make_service()
    svc.revoke_consent("nobody")  # should not raise
    assert svc.has_consented("nobody") is False


def test_revoke_sets_revoked_at() -> None:
    """After revoke_consent, the record has revoked_at set."""
    repo = _InMemoryConsentRepo()
    svc2 = ConsentService(repo)
    svc2.record_consent("carol")
    svc2.revoke_consent("carol")
    record = repo.get_consent("carol")
    assert record is not None
    assert record.revoked_at is not None
    assert record.revoked_at.tzinfo is not None


def test_re_record_consent_clears_revocation() -> None:
    """Calling record_consent again after revoke restores consented state."""
    svc = _make_service()
    svc.record_consent("dave")
    svc.revoke_consent("dave")
    assert svc.has_consented("dave") is False
    svc.record_consent("dave")
    assert svc.has_consented("dave") is True


def test_ac_new_session_after_consent() -> None:
    """REQ-011: session creation is only permitted when consent is active.

    This test simulates the permission check that the sessions router performs.
    """
    svc = _make_service()

    def _may_create_session(user_id: str) -> bool:
        """Simulate the sessions router consent gate."""
        return svc.has_consented(user_id)

    # Before consent: no access
    assert _may_create_session("eve") is False

    # After consent: access granted
    svc.record_consent("eve")
    assert _may_create_session("eve") is True

    # After revocation: access denied again
    svc.revoke_consent("eve")
    assert _may_create_session("eve") is False
