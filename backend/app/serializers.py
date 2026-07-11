"""Shared DB-row -> API-response conversion helpers."""
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from app import models, schemas


def _participant_active_sample(participant: models.Participant):
    now = datetime.utcnow()
    valid = [
        s
        for s in participant.audio_samples
        if s.deleted_at is None and s.expires_at > now
    ]
    if not valid:
        return None
    return max(valid, key=lambda s: s.created_at)


def participant_to_out(participant: models.Participant) -> schemas.ParticipantOut:
    sample = _participant_active_sample(participant)
    return schemas.ParticipantOut(
        id=participant.id,
        display_name=participant.display_name,
        participant_token=participant.participant_token,
        consent_status=participant.consent_status,
        consent_timestamp=participant.consent_timestamp,
        revoke_timestamp=participant.revoke_timestamp,
        has_audio_sample=sample is not None,
        audio_sample_expires_at=sample.expires_at if sample else None,
    )


def session_to_out(db: DBSession, session: models.Session) -> schemas.SessionOut:
    blocked_count = (
        db.query(models.Generation)
        .filter(models.Generation.session_id == session.id, models.Generation.blocked.is_(True))
        .count()
    )
    return schemas.SessionOut(
        id=session.id,
        retention_ttl_seconds=session.retention_ttl_seconds,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
        created_at=session.created_at,
        is_active=session.is_active,
        blocked_generation_count=blocked_count,
        participants=[participant_to_out(p) for p in session.participants],
    )
