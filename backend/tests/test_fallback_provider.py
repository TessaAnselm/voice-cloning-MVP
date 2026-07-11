"""
Proves: BrowserTTSProvider is never the default provider, and that when it
IS used (because LocalCloneProvider is unavailable), the API surfaces a
clear fallback flag for the frontend to warn the host with.
"""
from app import generation_pipeline
from app.providers import BrowserTTSProvider, LocalCloneProvider
from tests.conftest import create_session, full_consented_participant


def test_default_provider_is_local_clone_not_browser_tts():
    assert isinstance(generation_pipeline._local_provider, LocalCloneProvider)
    assert generation_pipeline._local_provider.name == "local_clone"
    assert generation_pipeline._local_provider.is_cloning_provider is True

    assert isinstance(generation_pipeline._fallback_provider, BrowserTTSProvider)
    assert generation_pipeline._fallback_provider.is_cloning_provider is False


def test_force_fallback_flag_defaults_to_false():
    from app.config import FORCE_FALLBACK_PROVIDER

    assert FORCE_FALLBACK_PROVIDER is False


def test_api_surfaces_fallback_warning_when_local_provider_unavailable(client, monkeypatch):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "FallbackWatcher")

    from app.providers.base import ProviderUnavailableError

    def local_unavailable(*args, **kwargs):
        raise ProviderUnavailableError("forced unavailable for test")

    monkeypatch.setattr(generation_pipeline._local_provider, "generate", local_unavailable)

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello world"},
    )
    body = resp.json()
    assert body["blocked"] is False
    assert body["fallback_active"] is True
    assert body["provider_used"] == "browser_tts_fallback"
