"""
Proves: session/participant/audio/generation data is deleted once the TTL
expires, and immediately when the host ends the session (safety
requirements #19-#21).
"""
from datetime import datetime, timedelta
from pathlib import Path

from app import models
from app.cleanup import sweep_expired
from app.database import get_db
from app.main import app
from tests.conftest import create_session, full_consented_participant


def _get_test_db_session(client):
    override = app.dependency_overrides[get_db]
    gen = override()
    return next(gen)


def test_ttl_expiration_purges_all_session_data(client):
    session = create_session(client, ttl_seconds=300)
    participant = full_consented_participant(client, session["id"], "Expiring")

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "hi there"},
    )
    assert resp.status_code == 200

    db = _get_test_db_session(client)
    try:
        db_session = db.query(models.Session).filter(models.Session.id == session["id"]).first()
        assert db_session is not None
        sample_paths = [s.file_path for p in db_session.participants for s in p.audio_samples]
        assert all(Path(p).exists() for p in sample_paths)

        # Force expiry into the past, as if the TTL had elapsed.
        db_session.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

        purged_count = sweep_expired(db)
        assert purged_count == 1

        assert db.query(models.Session).filter(models.Session.id == session["id"]).first() is None
        assert db.query(models.Participant).filter(
            models.Participant.id == participant["id"]
        ).first() is None
        assert all(not Path(p).exists() for p in sample_paths)
    finally:
        db.close()


def test_ending_session_immediately_purges_all_data(client):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "EndMe")

    gen_resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "hi there"},
    )
    assert gen_resp.status_code == 200
    generated_path = None
    if not gen_resp.json()["blocked"]:
        db = _get_test_db_session(client)
        row = (
            db.query(models.Generation)
            .filter(models.Generation.session_id == session["id"], models.Generation.blocked.is_(False))
            .first()
        )
        generated_path = row.output_file_path if row else None
        db.close()

    end_resp = client.delete(f"/sessions/{session['id']}")
    assert end_resp.status_code == 200

    # GET now 404s -- the session is fully gone, not soft-deleted.
    assert client.get(f"/sessions/{session['id']}").status_code == 404

    db = _get_test_db_session(client)
    try:
        assert db.query(models.Session).filter(models.Session.id == session["id"]).first() is None
        assert db.query(models.Participant).filter(
            models.Participant.id == participant["id"]
        ).first() is None
        assert db.query(models.AudioSample).filter(
            models.AudioSample.participant_id == participant["id"]
        ).first() is None
        assert db.query(models.Generation).filter(
            models.Generation.session_id == session["id"]
        ).first() is None
        if generated_path:
            assert not Path(generated_path).exists()
    finally:
        db.close()
