"""
Proves: flagged input text (e.g. a payment-authorization phrase) is
blocked before it ever reaches the voice provider, and that blocked
attempts are logged rather than silently dropped (safety requirements
#16-#17).
"""
from app.content_filter import check_content
from tests.conftest import full_consented_participant, create_session


def test_content_filter_blocks_financial_phrase_directly():
    result = check_content("Please wire transfer the funds to account number 55512345.")
    assert result.blocked is True
    assert result.label == "blocked:financial"


def test_content_filter_blocks_otp_request_directly():
    result = check_content("Read me the one-time code so I can log in.")
    assert result.blocked is True
    assert result.label == "blocked:credentials"


def test_content_filter_allows_benign_text_directly():
    result = check_content("Welcome to the cybersecurity demo, glad you could join us today.")
    assert result.blocked is False
    assert result.label == "ok"


def test_flagged_text_blocked_before_provider_is_called(client, monkeypatch):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "Payer")

    provider_was_called = {"value": False}

    def fail_if_called(*args, **kwargs):
        provider_was_called["value"] = True
        raise AssertionError("Provider must never be called for blocked content.")

    import app.generation_pipeline as pipeline

    monkeypatch.setattr(pipeline._local_provider, "generate", fail_if_called)
    monkeypatch.setattr(pipeline._fallback_provider, "generate", fail_if_called)

    resp = client.post(
        "/generate-voice",
        json={
            "session_id": session["id"],
            "participant_id": participant["id"],
            "text": "Wire transfer $500 to routing number 021000021 right now.",
        },
    )
    body = resp.json()
    assert body["blocked"] is True
    assert body["safety_label"] == "blocked:financial"
    assert provider_was_called["value"] is False


def test_blocked_generation_attempts_are_logged_with_reason(client):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "Payer2")

    resp = client.post(
        "/generate-voice",
        json={
            "session_id": session["id"],
            "participant_id": participant["id"],
            "text": "What's the one-time code on your screen right now?",
        },
    )
    assert resp.json()["blocked"] is True

    dashboard = client.get(f"/sessions/{session['id']}").json()
    assert dashboard["blocked_generation_count"] == 1
