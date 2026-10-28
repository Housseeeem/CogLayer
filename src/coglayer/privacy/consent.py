"""Consent service for CogLayer.

Handles recording, revoking, and querying user consent to data collection.
All data processing requires active consent. A user who revokes consent
must not be treated as having consented.

Non-clinical statement: this module does not store any clinical data. It
records only whether the user has agreed to local cognitive task data
collection for personalised coaching purposes.

Requirements: R-001.1, R-001.4
"""

from __future__ import annotations

from datetime import UTC, datetime

from coglayer.core.models import ConsentRecord
from coglayer.core.protocols import ConsentRepository

__all__ = ["ConsentService"]


class ConsentService:
    """Records, revokes, and queries user consent.

    Constructor takes a ``ConsentRepository`` so the service remains
    independent of any storage backend.

    Requirements: R-001.1, R-001.4
    """

    def __init__(self, repo: ConsentRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_consent(
        self,
        user_id: str,
        guardian_consent: bool = False,
        guardian_id: str | None = None,
    ) -> ConsentRecord:
        """Persist a new consent record for the user.

        If a record already exists (e.g. a previously revoked consent) it
        is replaced with a fresh one so ``consented_at`` reflects the most
        recent agreement.

        Args:
            user_id: The identifier of the user giving consent.
            guardian_consent: Whether a parent/guardian has consented (for minors).
            guardian_id: Identifier of the consenting guardian.

        Returns:
            The newly created ``ConsentRecord``.
        """
        record = ConsentRecord(
            user_id=user_id,
            consented_at=datetime.now(UTC),
            revoked_at=None,
            guardian_consent=guardian_consent,
            guardian_id=guardian_id,
        )
        self._repo.save_consent(record)
        return record

    def revoke_consent(self, user_id: str) -> None:
        """Mark consent as revoked for the user.

        Sets ``revoked_at`` on the existing record.  If no record exists
        this is a no-op (idempotent).

        Args:
            user_id: The identifier of the user revoking consent.
        """
        existing = self._repo.get_consent(user_id)
        if existing is None:
            return
        revoked = ConsentRecord(
            user_id=existing.user_id,
            consented_at=existing.consented_at,
            revoked_at=datetime.now(UTC),
            guardian_consent=existing.guardian_consent,
            guardian_id=existing.guardian_id,
        )
        self._repo.save_consent(revoked)

    def has_consented(self, user_id: str) -> bool:
        """Return True only if the user has an active (non-revoked) consent record.

        Args:
            user_id: The identifier of the user to check.

        Returns:
            ``True`` if a consent record exists and ``revoked_at`` is ``None``.
            ``False`` in all other cases (no record, or record has been revoked).
        """
        record = self._repo.get_consent(user_id)
        if record is None:
            return False
        return record.revoked_at is None
