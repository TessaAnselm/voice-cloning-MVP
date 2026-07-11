"""
Data-expiration and purge logic.

Safety requirements #19-#21: nothing persists indefinitely, and ending a
session immediately purges everything for it. Two mechanisms call into
this module:

  1. A background asyncio task (started in main.py's lifespan) that sweeps
     for expired sessions periodically.
  2. Lazy checks: guards.py's require_active_session() independently
     re-checks expiry on every request, so even if the sweep hasn't run
     yet, an expired session can never be used for generation.

purge_session() is also called directly and synchronously by the
DELETE /sessions/{id} (host "end session") endpoint.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from app import models
from app.config import AUDIO_SAMPLE_DIR, GENERATED_DIR
from app.path_safety import UnsafePathError, ensure_within

logger = logging.getLogger("voice_demo.cleanup")


def _delete_file_if_exists(path: str) -> None:
    if not path:
        return
    try:
        # Defense in depth (CWE-23): every stored path is server-generated,
        # but we still confirm it resolves inside one of our own storage
        # roots before deleting it.
        p = ensure_within(path, [AUDIO_SAMPLE_DIR, GENERATED_DIR])
    except UnsafePathError:
        logger.warning("Refusing to delete out-of-bounds path: %s", path)
        return
    try:
        if p.exists():
            p.unlink()
    except OSError as exc:  # pragma: no cover - filesystem edge cases
        logger.warning("Failed to delete file %s: %s", path, exc)


def purge_session(db: DBSession, session: models.Session) -> None:
    """
    Immediately and irreversibly deletes ALL data for a session: consent
    records, audio sample files + rows, generated clip files + rows, and
    the session row itself. Used both by "host ends session" and by TTL
    expiration sweeps.
    """
    participants = db.query(models.Participant).filter(
        models.Participant.session_id == session.id
    ).all()

    for participant in participants:
        for sample in participant.audio_samples:
            _delete_file_if_exists(sample.file_path)

    generations = db.query(models.Generation).filter(
        models.Generation.session_id == session.id
    ).all()
    for gen in generations:
        if gen.output_file_path:
            _delete_file_if_exists(gen.output_file_path)

    # Cascades (configured in models.py relationships) remove participants,
    # capture_sessions, audio_samples, and generations rows.
    db.delete(session)
    db.commit()
    logger.info("Purged all data for session %s", session.id)


def sweep_expired(db: DBSession) -> int:
    """
    Finds sessions that are past their TTL (or already ended but not yet
    purged) and purges them. Returns the number of sessions purged.
    Safe to call repeatedly / concurrently -- it's just a DELETE.
    """
    now = datetime.utcnow()
    expired_sessions = (
        db.query(models.Session)
        .filter((models.Session.expires_at <= now) | (models.Session.ended_at.isnot(None)))
        .all()
    )
    for session in expired_sessions:
        purge_session(db, session)
    return len(expired_sessions)


def purge_expired_audio_samples(db: DBSession) -> int:
    """
    Belt-and-suspenders: even within a still-active session, individual
    audio samples that outlived their own expires_at get their file
    deleted and are marked deleted_at, so a stale reference clip is never
    usable even before the whole session expires.
    """
    now = datetime.utcnow()
    stale = (
        db.query(models.AudioSample)
        .filter(models.AudioSample.expires_at <= now, models.AudioSample.deleted_at.is_(None))
        .all()
    )
    for sample in stale:
        _delete_file_if_exists(sample.file_path)
        sample.deleted_at = now
    if stale:
        db.commit()
    return len(stale)
