"""Pydantic request/response models for the API."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.config import DEFAULT_TTL_SECONDS, MAX_TTL_SECONDS, MIN_TTL_SECONDS


class SessionCreateRequest(BaseModel):
    retention_ttl_seconds: int = Field(
        default=DEFAULT_TTL_SECONDS, ge=MIN_TTL_SECONDS, le=MAX_TTL_SECONDS
    )


class ParticipantOut(BaseModel):
    id: str
    display_name: str
    participant_token: str
    consent_status: str
    consent_timestamp: Optional[datetime]
    revoke_timestamp: Optional[datetime]
    has_audio_sample: bool
    audio_sample_expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: str
    retention_ttl_seconds: int
    expires_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    is_active: bool
    blocked_generation_count: int
    participants: List[ParticipantOut]

    class Config:
        from_attributes = True


class ParticipantCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class ParticipantPublicOut(BaseModel):
    """What a participant themself is allowed to see about their own record."""

    id: str
    session_id: str
    display_name: str
    consent_status: str
    has_audio_sample: bool
    session_is_active: bool

    class Config:
        from_attributes = True


class ConsentGrantRequest(BaseModel):
    """
    Explicit consent-button click. No audio is attached here -- this is the
    plain "I consent" action required by safety requirement #6/#7, separate
    from and prior to any recording.
    """

    pass


class ConsentPhraseCaptureRequest(BaseModel):
    """
    Marks that the spoken consent phrase segment of a continuous capture
    session has completed. Sent by the recording page immediately after the
    participant finishes speaking the consent phrase, BEFORE the reference
    sample segment starts. This is what binds capture_session_id to a
    verified, consenting recording flow (requirement #14).
    """

    capture_session_id: str


class GenerateVoiceRequest(BaseModel):
    session_id: str
    participant_id: str
    text: str = Field(min_length=1, max_length=1000)


class GenerateVoiceResponse(BaseModel):
    blocked: bool
    safety_label: str
    blocked_reason: Optional[str] = None
    audio_url: Optional[str] = None
    provider_used: Optional[str] = None
    fallback_active: bool = False
    disclosure_text: Optional[str] = None
