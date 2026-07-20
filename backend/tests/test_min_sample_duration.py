"""
Proves: an audio-sample submission is rejected if it's shorter than
MIN_AUDIO_SAMPLE_DURATION_SECONDS, and is never marked sample_completed in
that case (see findings.md Finding 3: a too-short reference clip produces a
weak speaker embedding, which XTTS renders as garbled/unintelligible speech
instead of erroring out).
"""
import uuid

from app.config import MIN_AUDIO_SAMPLE_DURATION_SECONDS
from tests.conftest import add_participant, create_session, grant_consent, mark_consent_phrase


def _upload_with_duration(client, participant_id, capture_session_id, duration_seconds):
    fake_audio_bytes = b"RIFF....WAVEfmt fake audio bytes for test purposes only"
    return client.post(
        f"/participants/{participant_id}/audio-sample",
        data={
            "capture_session_id": capture_session_id,
            "duration_seconds": str(duration_seconds),
            "peak_level_dbfs": "-20.0",
        },
        files={"file": ("sample.wav", fake_audio_bytes, "audio/wav")},
    )


def test_audio_sample_rejected_when_shorter_than_minimum_duration(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "TooShort")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    resp = _upload_with_duration(
        client, participant["id"], capture_id, MIN_AUDIO_SAMPLE_DURATION_SECONDS - 0.1
    )

    assert resp.status_code == 400
    assert "too short" in resp.json()["detail"]

    session_state = client.get(f"/sessions/{session['id']}").json()
    (participant_state,) = [p for p in session_state["participants"] if p["id"] == participant["id"]]
    assert participant_state["has_audio_sample"] is False


def test_audio_sample_rejected_when_duration_missing(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "NoDuration")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    fake_audio_bytes = b"RIFF....WAVEfmt fake audio bytes for test purposes only"
    resp = client.post(
        f"/participants/{participant['id']}/audio-sample",
        data={"capture_session_id": capture_id},
        files={"file": ("sample.wav", fake_audio_bytes, "audio/wav")},
    )

    assert resp.status_code == 400


def test_audio_sample_accepted_at_minimum_duration(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "JustLongEnough")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    resp = _upload_with_duration(
        client, participant["id"], capture_id, MIN_AUDIO_SAMPLE_DURATION_SECONDS
    )

    assert resp.status_code == 200
    assert resp.json()["has_audio_sample"] is True
