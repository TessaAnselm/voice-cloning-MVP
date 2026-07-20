"""
Proves: an audio-sample submission is rejected if its reported peak level
is below MIN_AUDIO_SAMPLE_PEAK_DBFS, and is never marked sample_completed in
that case. This catches a silent/near-silent recording (muted mic, wrong
input device) that would otherwise pass the duration check but give XTTS no
real voice to condition on, producing a generic/unrelated-sounding clone
instead of erroring out.
"""
import uuid

from app.config import MIN_AUDIO_SAMPLE_PEAK_DBFS
from tests.conftest import add_participant, create_session, grant_consent, mark_consent_phrase


def _upload_with_peak_level(client, participant_id, capture_session_id, peak_level_dbfs):
    fake_audio_bytes = b"RIFF....WAVEfmt fake audio bytes for test purposes only"
    return client.post(
        f"/participants/{participant_id}/audio-sample",
        data={
            "capture_session_id": capture_session_id,
            "duration_seconds": "8.0",
            "peak_level_dbfs": str(peak_level_dbfs),
        },
        files={"file": ("sample.wav", fake_audio_bytes, "audio/wav")},
    )


def test_audio_sample_rejected_when_quieter_than_minimum_peak_level(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "TooQuiet")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    resp = _upload_with_peak_level(
        client, participant["id"], capture_id, MIN_AUDIO_SAMPLE_PEAK_DBFS - 1
    )

    assert resp.status_code == 400
    assert "quiet" in resp.json()["detail"] or "silent" in resp.json()["detail"]

    session_state = client.get(f"/sessions/{session['id']}").json()
    (participant_state,) = [p for p in session_state["participants"] if p["id"] == participant["id"]]
    assert participant_state["has_audio_sample"] is False


def test_audio_sample_rejected_when_peak_level_missing(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "NoPeakLevel")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    fake_audio_bytes = b"RIFF....WAVEfmt fake audio bytes for test purposes only"
    resp = client.post(
        f"/participants/{participant['id']}/audio-sample",
        data={"capture_session_id": capture_id, "duration_seconds": "8.0"},
        files={"file": ("sample.wav", fake_audio_bytes, "audio/wav")},
    )

    assert resp.status_code == 400


def test_audio_sample_accepted_at_minimum_peak_level(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "JustLoudEnough")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    mark_consent_phrase(client, participant["id"], capture_id)

    resp = _upload_with_peak_level(
        client, participant["id"], capture_id, MIN_AUDIO_SAMPLE_PEAK_DBFS
    )

    assert resp.status_code == 200
    assert resp.json()["has_audio_sample"] is True
