"""
Database models.

Table layout mirrors the demo's safety model closely on purpose:
consent, capture binding, and audio-sample lifecycle are each their own
table so every safety check in guards.py can be expressed as a simple,
auditable query instead of inferred from booleans scattered across one
big row.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    retention_ttl_seconds = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    participants = relationship(
        "Participant", back_populates="session", cascade="all, delete-orphan"
    )
    generations = relationship(
        "Generation", back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """False if the session has been ended by the host OR its TTL lapsed."""
        if self.ended_at is not None:
            return False
        if datetime.utcnow() >= self.expires_at:
            return False
        return True


class Participant(Base):
    __tablename__ = "participants"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    display_name = Column(String, nullable=False)
    # Opaque token used only in the participant's private shareable link.
    # Kept separate from `id` so the host dashboard can display participant
    # ids/names without ever exposing the secret link value.
    participant_token = Column(String, unique=True, default=_uuid, nullable=False)

    # consent_status: "none" | "granted" | "revoked"
    consent_status = Column(String, default="none", nullable=False)
    consent_timestamp = Column(DateTime, nullable=True)
    revoke_timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("Session", back_populates="participants")
    capture_sessions = relationship(
        "CaptureSession", back_populates="participant", cascade="all, delete-orphan"
    )
    audio_samples = relationship(
        "AudioSample", back_populates="participant", cascade="all, delete-orphan"
    )
    generations = relationship(
        "Generation", back_populates="participant", cascade="all, delete-orphan"
    )

    @property
    def has_consented(self) -> bool:
        return self.consent_status == "granted"


class CaptureSession(Base):
    """
    Binds one uninterrupted browser recording (consent phrase + reference
    sample) together. Safety requirement #14/#15: an audio-sample upload is
    only accepted if it references a CaptureSession row whose consent
    phrase segment already completed for the SAME participant.
    """

    __tablename__ = "capture_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    participant_id = Column(String, ForeignKey("participants.id"), nullable=False)
    # Client-generated UUID minted once when the participant presses
    # "start continuous recording". The same value tags both segments.
    capture_session_id = Column(String, nullable=False, index=True)
    consent_phrase_completed = Column(Boolean, default=False, nullable=False)
    sample_completed = Column(Boolean, default=False, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    # Set if the binding is rejected (e.g. too much time elapsed between
    # segments, meaning it was very likely not actually continuous).
    invalidated_at = Column(DateTime, nullable=True)

    participant = relationship("Participant", back_populates="capture_sessions")

    @property
    def is_valid_for_sample(self) -> bool:
        return self.consent_phrase_completed and self.invalidated_at is None


class AudioSample(Base):
    __tablename__ = "audio_samples"

    id = Column(String, primary_key=True, default=_uuid)
    participant_id = Column(String, ForeignKey("participants.id"), nullable=False)
    capture_session_id = Column(String, nullable=False)
    # Must always be "live_recording" -- enforced in the router, never
    # trusted from client input. There is no other valid value because
    # there is no upload/import path in this app (safety requirement #13).
    source = Column(String, default="live_recording", nullable=False)
    file_path = Column(String, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    participant = relationship("Participant", back_populates="audio_samples")

    @property
    def is_usable(self) -> bool:
        if self.deleted_at is not None:
            return False
        if datetime.utcnow() >= self.expires_at:
            return False
        return True


class Generation(Base):
    """
    Every generation *attempt* is logged here, whether it succeeded,
    was blocked by the content filter, or was blocked by a consent/audio
    guard. `blocked=True` rows are the audit trail for requirement #17.
    """

    __tablename__ = "generations"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    participant_id = Column(String, ForeignKey("participants.id"), nullable=True)
    input_text = Column(Text, nullable=False)
    output_file_path = Column(String, nullable=True)
    safety_label = Column(String, nullable=False)  # e.g. "ok", "blocked:financial"
    blocked = Column(Boolean, default=False, nullable=False)
    blocked_reason = Column(String, nullable=True)
    provider_used = Column(String, nullable=True)  # "local_clone" | "browser_tts_fallback"
    requested_by = Column(String, default="host", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    session = relationship("Session", back_populates="generations")
    participant = relationship("Participant", back_populates="generations")
