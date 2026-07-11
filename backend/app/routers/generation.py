"""
POST /generate-voice

This is the single most safety-critical endpoint in the app. Order of
operations is fixed and enforced here:

  1. guards.validate_can_generate()  -- consent, revocation, session,
     audio-sample validity. NOTHING below this line runs if it fails.
  2. content_filter.check_content()  -- keyword/heuristic safety filter.
     NOTHING below this line runs if it fails.
  3. generation_pipeline.run_generation() -- only now is a
     VoiceCloneProvider ever invoked, and only with the participant's OWN
     stored reference sample.

Every attempt, blocked or not, is written to the `generations` table
(requirement #17 -- blocked attempts must be logged, never silently
dropped) and the host dashboard's blocked-count is a live COUNT() query
over that table (see serializers.session_to_out).
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from app import models, schemas
from app.content_filter import check_content
from app.database import get_db
from app.generation_pipeline import run_generation
from app.guards import GuardError, validate_can_generate
from app.providers.base import ProviderUnavailableError, ReferenceAudioMissingError
from app.config import DISCLOSURE_TEXT, GENERATED_DIR

router = APIRouter(tags=["generation"])


def _log_blocked(
    db: DBSession, *, session_id: str, participant_id: str | None, text: str, label: str, reason: str
) -> None:
    row = models.Generation(
        session_id=session_id,
        participant_id=participant_id,
        input_text=text,
        output_file_path=None,
        safety_label=label,
        blocked=True,
        blocked_reason=reason,
        requested_by="host",
    )
    db.add(row)
    db.commit()


@router.post("/generate-voice", response_model=schemas.GenerateVoiceResponse)
def generate_voice(payload: schemas.GenerateVoiceRequest, db: DBSession = Depends(get_db)):
    # --- Step 1: consent / session / audio-sample guards -----------------
    try:
        ctx = validate_can_generate(db, payload.session_id, payload.participant_id)
    except GuardError as exc:
        _log_blocked(
            db,
            session_id=payload.session_id,
            participant_id=payload.participant_id,
            text=payload.text,
            label=f"blocked:{exc.code}",
            reason=exc.message,
        )
        return schemas.GenerateVoiceResponse(
            blocked=True, safety_label=f"blocked:{exc.code}", blocked_reason=exc.message
        )

    # --- Step 2: content filter ------------------------------------------
    participant_names = [p.display_name for p in ctx.session.participants]
    filter_result = check_content(payload.text, participant_names)
    if filter_result.blocked:
        _log_blocked(
            db,
            session_id=payload.session_id,
            participant_id=payload.participant_id,
            text=payload.text,
            label=filter_result.label,
            reason=filter_result.reason or "Blocked by content filter.",
        )
        return schemas.GenerateVoiceResponse(
            blocked=True, safety_label=filter_result.label, blocked_reason=filter_result.reason
        )

    # --- Step 3: provider call (consent + filter already passed) ---------
    try:
        outcome = run_generation(
            text=payload.text,
            reference_audio_path=ctx.audio_sample.file_path,
            participant_id=ctx.participant.id,
            session_id=ctx.session.id,
        )
    except (ReferenceAudioMissingError, ProviderUnavailableError) as exc:
        _log_blocked(
            db,
            session_id=payload.session_id,
            participant_id=payload.participant_id,
            text=payload.text,
            label="blocked:provider_error",
            reason=str(exc),
        )
        return schemas.GenerateVoiceResponse(
            blocked=True, safety_label="blocked:provider_error", blocked_reason=str(exc)
        )

    row = models.Generation(
        session_id=ctx.session.id,
        participant_id=ctx.participant.id,
        input_text=payload.text,
        output_file_path=outcome.output_file_path,
        safety_label="ok",
        blocked=False,
        provider_used=outcome.provider_used,
        requested_by="host",
        expires_at=ctx.session.expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return schemas.GenerateVoiceResponse(
        blocked=False,
        safety_label="ok",
        audio_url=f"/generated-audio/{row.id}",
        provider_used=outcome.provider_used,
        fallback_active=outcome.fallback_active,
        disclosure_text=DISCLOSURE_TEXT,
    )


@router.get("/generated-audio/{generation_id}")
def get_generated_audio(generation_id: str, db: DBSession = Depends(get_db)):
    """
    Serves a previously generated (and disclosure-embedded) clip. Only
    successful, non-blocked generations have a file to serve; expired or
    purged sessions/generations return 404 because the row and file no
    longer exist (see cleanup.py).
    """
    row = db.query(models.Generation).filter(models.Generation.id == generation_id).first()
    if row is None or row.blocked or not row.output_file_path:
        raise HTTPException(status_code=404, detail="Generated audio not found.")

    # CWE-23 hardening: never hand the DB-stored path straight to
    # FileResponse. Generated clips are always flat files directly under
    # GENERATED_DIR (see generation_pipeline.py), so re-derive the path
    # from ONLY the basename (os.path.basename cannot contain a directory
    # separator, so the rejoin below cannot escape GENERATED_DIR), then
    # explicitly re-verify containment against the resolved, real
    # filesystem root immediately before the sink call.
    safe_filename = os.path.basename(row.output_file_path)
    resolved_root = os.path.realpath(GENERATED_DIR)
    resolved_candidate = os.path.realpath(os.path.join(resolved_root, safe_filename))
    if os.path.commonpath([resolved_root, resolved_candidate]) != resolved_root:
        raise HTTPException(status_code=404, detail="Generated audio not found.")
    if not os.path.isfile(resolved_candidate):
        raise HTTPException(status_code=404, detail="Generated audio file no longer exists.")
    return FileResponse(resolved_candidate, media_type="audio/wav")
