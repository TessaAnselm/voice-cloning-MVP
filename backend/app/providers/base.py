"""
VoiceCloneProvider interface.

Every provider implementation must accept the SAME arguments and return a
path to a raw generated WAV file. Consent checks, content filtering,
blocked-attempt logging, and spoken-disclosure embedding all happen OUTSIDE
providers, in app/generation_pipeline.py, so they apply identically no
matter which provider produced the audio. Providers themselves must never
be reachable except through that pipeline.
"""
from abc import ABC, abstractmethod


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider cannot run (e.g. its model/engine isn't installed)."""


class ReferenceAudioMissingError(RuntimeError):
    """Raised when the participant has no valid, verified reference sample."""


class VoiceCloneProvider(ABC):
    #: Machine-readable identifier stored on the generation record.
    name: str = "base"
    #: True for providers that actually clone the reference voice.
    is_cloning_provider: bool = False

    @abstractmethod
    def generate(
        self,
        *,
        text: str,
        reference_audio_path: str,
        participant_id: str,
        session_id: str,
        out_path: str,
    ) -> str:
        """
        Generate speech for `text` and write it to `out_path`.

        `reference_audio_path` MUST be the participant's own stored
        live-captured audio sample (never anyone else's, never a synthetic
        or third-party clip). Callers are responsible for verifying that
        path belongs to a consenting, non-revoked, non-expired participant
        BEFORE calling this method -- see app/guards.py.

        Must raise ReferenceAudioMissingError if `reference_audio_path`
        does not exist / is falsy. Must raise ProviderUnavailableError if
        the underlying model/engine cannot run at all (caller may then
        fall back to another provider).
        """
        raise NotImplementedError
