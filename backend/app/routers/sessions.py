"""Session lifecycle endpoints: create, read, end (purge), add participants."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app import models, schemas
from app.cleanup import purge_session, sweep_expired
from app.database import get_db
from app.serializers import session_to_out

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=schemas.SessionOut)
def create_session(payload: schemas.SessionCreateRequest, db: DBSession = Depends(get_db)):
    # Opportunistic sweep so old demo data never silently accumulates.
    sweep_expired(db)

    now = datetime.utcnow()
    session = models.Session(
        retention_ttl_seconds=payload.retention_ttl_seconds,
        expires_at=now + timedelta(seconds=payload.retention_ttl_seconds),
        created_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session_to_out(db, session)


@router.get("/sessions/{session_id}", response_model=schemas.SessionOut)
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    sweep_expired(db)
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or already expired/ended.")
    return session_to_out(db, session)


@router.delete("/sessions/{session_id}")
def end_session(session_id: str, db: DBSession = Depends(get_db)):
    """
    Host 'end session' action. Safety requirements #20/#21: purges ALL
    consent records, audio samples, and generated clips for this session
    immediately -- not on a delay, not soft-deleted.
    """
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    purge_session(db, session)
    return {"status": "purged", "session_id": session_id}


@router.post("/sessions/{session_id}/participants", response_model=schemas.ParticipantOut)
def add_participant(
    session_id: str, payload: schemas.ParticipantCreateRequest, db: DBSession = Depends(get_db)
):
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session has ended or expired.")

    participant = models.Participant(session_id=session_id, display_name=payload.display_name)
    db.add(participant)
    db.commit()
    db.refresh(participant)

    from app.serializers import participant_to_out

    return participant_to_out(participant)
