"""
Proves: generation is blocked when consent is missing, blocked after
consent is revoked, and blocked when there's no audio sample. These are
the core consent-based-by-design guarantees (safety requirements #1, #4-5).
"""
from tests.conftest import add_participant, create_session, full_consented_participant, grant_consent


def test_generation_blocked_when_consent_missing(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "NoConsent")

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello there"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert "consent" in body["safety_label"]

    # And it must be logged, not silently dropped.
    dashboard = client.get(f"/sessions/{session['id']}").json()
    assert dashboard["blocked_generation_count"] == 1


def test_generation_blocked_after_consent_revoked(client):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "RevokeMe")

    revoke_resp = client.post(f"/participants/{participant['id']}/revoke-consent")
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["consent_status"] == "revoked"

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello there"},
    )
    body = resp.json()
    assert body["blocked"] is True
    assert body["safety_label"] == "blocked:consent_revoked"


def test_generation_blocked_without_audio_sample(client):
    session = create_session(client)
    participant = add_participant(client, session["id"], "NoSample")
    grant_consent(client, participant["id"])

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello there"},
    )
    body = resp.json()
    assert body["blocked"] is True
    assert body["safety_label"] == "blocked:no_audio_sample"


def test_generation_blocked_after_audio_sample_deleted(client):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "DeleteSample")

    del_resp = client.delete(f"/participants/{participant['id']}/audio-sample")
    assert del_resp.status_code == 200
    assert del_resp.json()["has_audio_sample"] is False

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello there"},
    )
    body = resp.json()
    assert body["blocked"] is True
    assert body["safety_label"] == "blocked:audio_sample_deleted"
