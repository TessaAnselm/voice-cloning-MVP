from tests.conftest import create_session, full_consented_participant


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_generation_blocked_when_session_ended(client):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "EndedSession")

    client.delete(f"/sessions/{session['id']}")

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "hello"},
    )
    body = resp.json()
    assert body["blocked"] is True
    assert body["safety_label"] == "blocked:session_not_found"
