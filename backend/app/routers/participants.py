"""
Participant-facing endpoints: consent, revoke, live-recorded audio sample
submission/deletion, and a small read-only lookup used by the participant's
private link page.

*** No file-upload / import endpoint exists anywhere in this router. ***
The only way audio bytes reach the server is the multipart body of
POST /participants/{participant_id}/audio-sample, and that body must be a
live MediaRecorder capture tagged with a capture_session_id that already
completed its consent-phrase segment (safety requirements #13-#15). There
is no URL-import, file-path-import, or cloud-storage-link parameter
anywhere in this file -- by design, not by oversight.
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from app import models, schemas
from app.config import AUDIO_SAMPLE_DIR, CAPTURE_SESSION_MAX_GAP_SECONDS, MAX_AUDIO_UPLOAD_BYTES
from app.database import get_db
from app.path_safety import UnsafePathError, ensure_within
from app.serializers import participant_to_out

router = APIRouter(tags=["participants"])
logger = logging.getLogger("voice_demo.routers.participants")

# Never trust the client-supplied filename for the stored file's extension
# (CWE-23 hardening) -- map from the already-validated audio/* content
# type instead, so no user-controlled string ever reaches path
# construction.
_CONTENT_TYPE_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}
_DEFAULT_AUDIO_EXTENSION = ".webm"


def _delete_sample_file_if_safe(file_path: str) -> None:
    """Delete a stored audio-sample file, refusing to touch anything outside
    AUDIO_SAMPLE_DIR even though every stored path is server-generated."""
    try:
        safe_path = ensure_within(file_path, [AUDIO_SAMPLE_DIR])
    except UnsafePathError:
        logger.warning("Refusing to delete out-of-bounds path: %s", file_path)
        return
    if safe_path.exists():
        safe_path.unlink(missing_ok=True)


def _get_participant_or_404(db: DBSession, participant_id: str) -> models.Participant:
    participant = db.query(models.Participant).filter(models.Participant.id == participant_id).first()
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found.")
    return participant


def _require_active_session_or_400(participant: models.Participant) -> models.Session:
    session = participant.session
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session has ended or expired.")
    return session


@router.get("/participants/token/{participant_token}", response_model=schemas.ParticipantPublicOut)
def get_participant_by_token(participant_token: str, db: DBSession = Depends(get_db)):
    """
    Resolves a participant's private link token to their public state, so
    the participant's browser page knows what step to show. Read-only,
    exposes nothing about other participants.
    """
    participant = (
        db.query(models.Participant)
        .filter(models.Participant.participant_token == participant_token)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Invalid participant link.")

    has_sample = any(s.deleted_at is None and s.expires_at > datetime.utcnow() for s in participant.audio_samples)
    return schemas.ParticipantPublicOut(
        id=participant.id,
        session_id=participant.session_id,
        display_name=participant.display_name,
        consent_status=participant.consent_status,
        has_audio_sample=has_sample,
        session_is_active=participant.session.is_active,
    )


@router.post("/participants/{participant_id}/consent", response_model=schemas.ParticipantOut)
def grant_consent_or_mark_phrase(
    participant_id: str,
    payload: schemas.ConsentPhraseCaptureRequest | None = None,
    db: DBSession = Depends(get_db),
):
    """
    Two things happen through this single endpoint, matching the two
    consent-related moments in the required user flow:

    1. Explicit consent button click (no body / no capture_session_id):
       sets consent_status='granted' + consent_timestamp. This MUST happen
       before any recording UI is shown (requirement #6/#7 -- consent
       before recording, never implied or retroactive).

    2. Immediately after the participant speaks the consent phrase during
       the continuous recording (body includes capture_session_id): marks
       that capture session's consent-phrase segment as completed. This is
       the binding step requirement #14 describes -- it does NOT grant
       consent by itself, consent must already have been granted in step 1.
    """
    participant = _get_participant_or_404(db, participant_id)
    session = _require_active_session_or_400(participant)

    if participant.consent_status == "revoked":
        raise HTTPException(
            status_code=400,
            detail="Consent was previously revoked. Start a new session to consent again.",
        )

    capture_session_id = payload.capture_session_id if payload else None

    if capture_session_id is None:
        # Step 1: the explicit consent button.
        participant.consent_status = "granted"
        participant.consent_timestamp = datetime.utcnow()
        db.commit()
        db.refresh(participant)
        return participant_to_out(participant)

    # Step 2: mark the spoken consent-phrase segment complete. Consent must
    # already be granted -- you cannot record before consenting.
    if participant.consent_status != "granted":
        raise HTTPException(
            status_code=400,
            detail="Explicit consent must be granted before recording the consent phrase.",
        )

    capture = models.CaptureSession(
        participant_id=participant.id,
        capture_session_id=capture_session_id,
        consent_phrase_completed=True,
        started_at=datetime.utcnow(),
    )
    db.add(capture)
    db.commit()
    db.refresh(participant)
    return participant_to_out(participant)


@router.post("/participants/{participant_id}/revoke-consent", response_model=schemas.ParticipantOut)
def revoke_consent(participant_id: str, db: DBSession = Depends(get_db)):
    """
    Requirement #7: participant can withdraw consent at any time. Revoking
    consent immediately blocks all future generation for this participant
    (enforced in guards.py) even if their audio sample is still on disk.
    """
    participant = _get_participant_or_404(db, participant_id)
    participant.consent_status = "revoked"
    participant.revoke_timestamp = datetime.utcnow()
    db.commit()
    db.refresh(participant)
    return participant_to_out(participant)


@router.post("/participants/{participant_id}/audio-sample", response_model=schemas.ParticipantOut)
async def submit_audio_sample(
    participant_id: str,
    capture_session_id: str = Form(...),
    duration_seconds: float | None = Form(default=None),
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
):
    """
    Accepts ONLY a live-browser-recorded clip tied to a capture_session_id
    that already has a completed consent-phrase segment for this SAME
    participant (requirement #15). There is no other way to attach audio
    to a participant record in this codebase.
    """
    participant = _get_participant_or_404(db, participant_id)
    session = _require_active_session_or_400(participant)

    if participant.consent_status != "granted":
        raise HTTPException(status_code=403, detail="Participant has not consented.")

    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Only audio content is accepted.")

    # --- Core binding check (requirement #15) ---------------------------
    capture = (
        db.query(models.CaptureSession)
        .filter(
            models.CaptureSession.participant_id == participant.id,
            models.CaptureSession.capture_session_id == capture_session_id,
        )
        .order_by(models.CaptureSession.started_at.desc())
        .first()
    )
    if capture is None or not capture.is_valid_for_sample:
        raise HTTPException(
            status_code=409,
            detail=(
                "This audio sample's capture_session_id does not match a completed, "
                "valid consent-phrase recording for this participant. Please redo the "
                "continuous recording from the start."
            ),
        )

    gap = (datetime.utcnow() - capture.started_at).total_seconds()
    if gap > CAPTURE_SESSION_MAX_GAP_SECONDS:
        capture.invalidated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "Too much time elapsed since the consent phrase was recorded, so this "
                "capture can no longer be treated as one continuous session. Please "
                "redo the recording."
            ),
        )

    body = await file.read()
    if len(body) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio sample too large.")
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    ext = _CONTENT_TYPE_EXTENSIONS.get(file.content_type, _DEFAULT_AUDIO_EXTENSION)
    # participant.id is a server-generated UUID (models.py), never user
    # input, so this join can't be steered outside AUDIO_SAMPLE_DIR either.
    participant_dir = AUDIO_SAMPLE_DIR / participant.id
    participant_dir.mkdir(parents=True, exist_ok=True)
    file_path = participant_dir / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(body)

    # Any previous sample is superseded; delete its file so stale voice
    # data doesn't linger just because a new one was recorded.
    for old in participant.audio_samples:
        if old.deleted_at is None:
            _delete_sample_file_if_safe(old.file_path)
            old.deleted_at = datetime.utcnow()

    sample = models.AudioSample(
        participant_id=participant.id,
        capture_session_id=capture_session_id,
        source="live_recording",  # only valid value -- see models.py
        file_path=str(file_path),
        duration_seconds=duration_seconds,
        expires_at=session.expires_at,
    )
    db.add(sample)

    capture.sample_completed = True
    capture.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(participant)
    return participant_to_out(participant)


@router.delete("/participants/{participant_id}/audio-sample", response_model=schemas.ParticipantOut)
def delete_audio_sample(participant_id: str, db: DBSession = Depends(get_db)):
    """Requirement #7: participant (or host, on their behalf) can delete the voice sample."""
    participant = _get_participant_or_404(db, participant_id)

    for sample in participant.audio_samples:
        if sample.deleted_at is None:
            _delete_sample_file_if_safe(sample.file_path)
            sample.deleted_at = datetime.utcnow()

    db.commit()
    db.refresh(participant)
    return participant_to_out(participant)
