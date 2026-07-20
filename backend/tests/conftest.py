import os
import tempfile
import uuid
from pathlib import Path

# Point the app at an isolated temp DB/storage dir BEFORE importing app.main,
# since app.config/app.database read these env vars at import time. This
# keeps test runs from touching the developer's real voice_demo.db/storage.
_TEST_DIR = tempfile.mkdtemp(prefix="voice_demo_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
os.environ["STORAGE_DIR"] = _TEST_DIR
os.environ["CLEANUP_INTERVAL_SECONDS"] = "3600"  # don't race the background sweep in tests

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_engine, tmp_path, monkeypatch):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Route storage for this test to an isolated tmp dir.
    import app.config as config

    monkeypatch.setattr(config, "AUDIO_SAMPLE_DIR", tmp_path / "audio_samples")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    config.AUDIO_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    import app.routers.participants as participants_router

    monkeypatch.setattr(participants_router, "AUDIO_SAMPLE_DIR", config.AUDIO_SAMPLE_DIR)

    import app.generation_pipeline as pipeline

    monkeypatch.setattr(pipeline, "GENERATED_DIR", config.GENERATED_DIR)

    import app.routers.generation as generation_router

    monkeypatch.setattr(generation_router, "GENERATED_DIR", config.GENERATED_DIR)

    import app.cleanup as cleanup

    monkeypatch.setattr(cleanup, "AUDIO_SAMPLE_DIR", config.AUDIO_SAMPLE_DIR)
    monkeypatch.setattr(cleanup, "GENERATED_DIR", config.GENERATED_DIR)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_session(client, ttl_seconds: int = 86400) -> dict:
    resp = client.post("/sessions", json={"retention_ttl_seconds": ttl_seconds})
    assert resp.status_code == 200
    return resp.json()


def add_participant(client, session_id: str, name: str = "Alex") -> dict:
    resp = client.post(f"/sessions/{session_id}/participants", json={"display_name": name})
    assert resp.status_code == 200
    return resp.json()


def grant_consent(client, participant_id: str) -> dict:
    resp = client.post(f"/participants/{participant_id}/consent")
    assert resp.status_code == 200
    return resp.json()


def mark_consent_phrase(client, participant_id: str, capture_session_id: str) -> dict:
    resp = client.post(
        f"/participants/{participant_id}/consent",
        json={"capture_session_id": capture_session_id},
    )
    assert resp.status_code == 200
    return resp.json()


def upload_audio_sample(client, participant_id: str, capture_session_id: str, filename="sample.wav"):
    fake_audio_bytes = b"RIFF....WAVEfmt fake audio bytes for test purposes only"
    return client.post(
        f"/participants/{participant_id}/audio-sample",
        data={
            "capture_session_id": capture_session_id,
            "duration_seconds": "8.0",
            "peak_level_dbfs": "-20.0",
        },
        files={"file": (filename, fake_audio_bytes, "audio/wav")},
    )


def full_consented_participant(client, session_id: str, name: str = "Alex") -> dict:
    """Walks a participant through the full required consent+capture flow."""
    participant = add_participant(client, session_id, name)
    grant_consent(client, participant["id"])
    capture_session_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_session_id)
    resp = upload_audio_sample(client, participant["id"], capture_session_id)
    assert resp.status_code == 200, resp.text
    return resp.json()
