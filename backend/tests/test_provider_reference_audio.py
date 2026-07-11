"""
Proves: the cloning provider is always called with the participant's OWN
stored reference sample, and generation fails outright if that verified
reference sample is missing (safety requirement: providers must never run
without a real, participant-owned reference clip).
"""
import pytest

from app.providers import BrowserTTSProvider, LocalCloneProvider
from app.providers.base import ReferenceAudioMissingError
from tests.conftest import create_session, full_consented_participant


def test_local_clone_provider_requires_reference_audio(tmp_path):
    provider = LocalCloneProvider()
    with pytest.raises(ReferenceAudioMissingError):
        provider.generate(
            text="hello",
            reference_audio_path=str(tmp_path / "missing.wav"),
            participant_id="p1",
            session_id="s1",
            out_path=str(tmp_path / "out.wav"),
        )


def test_browser_tts_provider_requires_reference_audio(tmp_path):
    provider = BrowserTTSProvider()
    with pytest.raises(ReferenceAudioMissingError):
        provider.generate(
            text="hello",
            reference_audio_path=str(tmp_path / "missing.wav"),
            participant_id="p1",
            session_id="s1",
            out_path=str(tmp_path / "out.wav"),
        )


def test_provider_is_called_with_participants_own_reference_sample(client, monkeypatch):
    session = create_session(client)
    participant = full_consented_participant(client, session["id"], "Owner")

    # Force LocalCloneProvider unavailable so the deterministic fallback
    # path runs regardless of whether Coqui TTS happens to be installed in
    # this environment, and capture what reference path each provider saw.
    import app.generation_pipeline as pipeline
    from app.providers.base import ProviderUnavailableError

    seen = {}

    def local_unavailable(*args, **kwargs):
        raise ProviderUnavailableError("forced unavailable for test")

    def fallback_capture(*, text, reference_audio_path, participant_id, session_id, out_path):
        seen["reference_audio_path"] = reference_audio_path
        seen["participant_id"] = participant_id
        from app.audio_utils import synthesize_tone_placeholder

        return synthesize_tone_placeholder(text, out_path)

    monkeypatch.setattr(pipeline._local_provider, "generate", local_unavailable)
    monkeypatch.setattr(pipeline._fallback_provider, "generate", fallback_capture)

    resp = client.post(
        "/generate-voice",
        json={"session_id": session["id"], "participant_id": participant["id"], "text": "Hello world"},
    )
    body = resp.json()
    assert body["blocked"] is False

    # The reference path passed to the provider must be this participant's
    # own stored sample file, not anyone else's.
    assert seen["participant_id"] == participant["id"]
    assert participant["id"] in seen["reference_audio_path"]
