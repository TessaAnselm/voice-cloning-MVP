"""
Centralized abuse-prevention guards.

Every check here is enforced SERVER-SIDE regardless of what the frontend
already checked (safety requirement #5: "Enforce consent checks in both
the frontend and backend"). The frontend checks exist only for UX; this
module is the actual security boundary. /generate-voice and the
audio-sample endpoints must call these before doing anything else.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app import models


class GuardError(Exception):
    """Raised when a request fails an abuse-prevention guard."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ValidatedGenerationContext:
    session: models.Session
    participant: models.Participant
    audio_sample: models.AudioSample


def require_active_session(session: Optional[models.Session]) -> models.Session:
    if session is None:
        raise GuardError("session_not_found", "Session not found.")
    if session.ended_at is not None:
        raise GuardError("session_ended", "This session has been ended by the host.")
    if datetime.utcnow() >= session.expires_at:
        raise GuardError("session_expired", "This session's data retention window has expired.")
    return session


def require_consenting_participant(participant: Optional[models.Participant]) -> models.Participant:
    """
    Core consent gate (safety requirements #1, #4, #5). Generation and new
    recordings must both refuse to proceed unless this passes.
    """
    if participant is None:
        raise GuardError("participant_not_found", "Participant not found.")
    if participant.consent_status == "revoked":
        raise GuardError(
            "consent_revoked",
            f"{participant.display_name} has revoked consent. Voice generation is not permitted.",
        )
    if participant.consent_status != "granted":
        raise GuardError(
            "consent_missing",
            f"{participant.display_name} has not granted consent yet.",
        )
    return participant


def require_usable_audio_sample(participant: models.Participant) -> models.AudioSample:
    """
    Participant must have a live-recorded, non-deleted, non-expired sample
    bound to a validly-completed capture session (requirements #13-#15).
    """
    sample = (
        None
        if not participant.audio_samples
        else max(participant.audio_samples, key=lambda s: s.created_at)
    )
    if sample is None:
        raise GuardError(
            "no_audio_sample",
            f"{participant.display_name} has no recorded voice sample.",
        )
    if sample.deleted_at is not None:
        raise GuardError(
            "audio_sample_deleted",
            f"{participant.display_name}'s voice sample has been deleted.",
        )
    if datetime.utcnow() >= sample.expires_at:
        raise GuardError(
            "audio_sample_expired",
            f"{participant.display_name}'s voice sample has expired.",
        )
    if sample.source != "live_recording":
        # Defense in depth: this should be structurally impossible given
        # there is no upload/import path, but never trust it implicitly.
        raise GuardError(
            "invalid_audio_source",
            "Audio sample source is invalid.",
        )
    return sample


def validate_can_generate(
    db: DBSession, session_id: str, participant_id: str
) -> ValidatedGenerationContext:
    """
    The single entry point /generate-voice uses before EVER touching the
    content filter or a provider. Raises GuardError with a user-facing
    reason on any failure; callers must log the blocked attempt.
    """
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    session = require_active_session(session)

    participant = (
        db.query(models.Participant)
        .filter(
            models.Participant.id == participant_id,
            models.Participant.session_id == session_id,
        )
        .first()
    )
    participant = require_consenting_participant(participant)
    sample = require_usable_audio_sample(participant)

    return ValidatedGenerationContext(session=session, participant=participant, audio_sample=sample)
