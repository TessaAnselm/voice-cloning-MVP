"""
Proves: there is no generic file-upload endpoint or import path for audio
samples anywhere in the API (safety requirement #13).
"""
from app.main import app


def test_no_generic_upload_or_import_route_exists():
    # Walk the OpenAPI schema rather than app.routes directly -- more
    # robust across FastAPI/Starlette versions' internal route wrapping.
    paths = list(app.openapi()["paths"].keys())
    assert "/participants/{participant_id}/audio-sample" in paths

    forbidden_substrings = ["upload", "import", "from-url", "from-file", "from-path"]
    for path in paths:
        lowered = path.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"Forbidden route found: {path}"


def test_audio_sample_endpoint_requires_capture_session_id_field(client):
    """
    The only endpoint that accepts audio bytes is
    POST /participants/{id}/audio-sample, and it structurally requires a
    capture_session_id (no anonymous/unbound upload is possible).
    """
    from tests.conftest import add_participant, create_session, grant_consent

    session = create_session(client)
    participant = add_participant(client, session["id"], "Test")
    grant_consent(client, participant["id"])

    # Omit capture_session_id entirely.
    resp = client.post(
        f"/participants/{participant['id']}/audio-sample",
        files={"file": ("sample.wav", b"fake audio bytes", "audio/wav")},
    )
    assert resp.status_code == 422  # FastAPI rejects: missing required form field


def test_audio_sample_endpoint_rejects_non_audio_content_type(client):
    from tests.conftest import add_participant, create_session, grant_consent
    import uuid

    session = create_session(client)
    participant = add_participant(client, session["id"], "Test")
    grant_consent(client, participant["id"])
    capture_id = str(uuid.uuid4())
    client.post(f"/participants/{participant['id']}/consent", json={"capture_session_id": capture_id})

    resp = client.post(
        f"/participants/{participant['id']}/audio-sample",
        data={"capture_session_id": capture_id},
        files={"file": ("not_audio.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
