"""
Proves: an audio-sample submission is rejected if its capture_session_id
does not match a completed consent-phrase recording for that participant
(safety requirements #14-#15) -- and that there is no way to submit audio
without going through that binding at all.
"""
import uuid

from tests.conftest import add_participant, create_session, grant_consent, upload_audio_sample


def test_audio_sample_rejected_with_unknown_capture_session_id(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "Bound")
    grant_consent(client, participant["id"])

    # No consent-phrase segment was ever recorded for this capture_session_id.
    bogus_capture_id = str(uuid.uuid4())
    resp = upload_audio_sample(client, participant["id"], bogus_capture_id)

    assert resp.status_code == 409
    assert "consent-phrase" in resp.json()["detail"]


def test_audio_sample_rejected_if_capture_session_belongs_to_different_participant(client):
    session = create_session(client)
    p1 = add_participant(client, session["id"], "P1")
    p2 = add_participant(client, session["id"], "P2")
    grant_consent(client, p1["id"])
    grant_consent(client, p2["id"])

    capture_id = str(uuid.uuid4())
    # P1 completes their consent phrase.
    resp = client.post(f"/participants/{p1['id']}/consent", json={"capture_session_id": capture_id})
    assert resp.status_code == 200

    # P2 tries to submit a sample reusing P1's capture_session_id.
    resp = upload_audio_sample(client, p2["id"], capture_id)
    assert resp.status_code == 409


def test_audio_sample_rejected_before_explicit_consent_granted(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "NoConsentYet")

    # Attempting to mark the consent-phrase segment before the explicit
    # consent button was pressed must fail.
    capture_id = str(uuid.uuid4())
    resp = client.post(
        f"/participants/{participant['id']}/consent", json={"capture_session_id": capture_id}
    )
    assert resp.status_code == 400
