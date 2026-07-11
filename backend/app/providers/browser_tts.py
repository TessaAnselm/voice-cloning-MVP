"""
BrowserTTSProvider -- offline fallback ONLY.

"Fallback only. This does not clone voices."

This provider ignores the participant's reference audio entirely (beyond
verifying it exists, for consistency with the interface and so callers get
the same abuse-prevention error if it's missing) and instead speaks the
requested text with a generic system TTS voice, or a tone placeholder if no
system TTS engine is available. It must NEVER be selected as the default
provider -- app/generation_pipeline.py only reaches for it when
LocalCloneProvider raises ProviderUnavailableError, and every time that
happens the API response and host UI must show a fallback warning.
"""
import logging
from pathlib import Path

from app.providers.base import ReferenceAudioMissingError, VoiceCloneProvider
from app.speech import synthesize_speech_wav

logger = logging.getLogger("voice_demo.providers.browser_tts")

FALLBACK_LABEL = "Fallback only. This does not clone voices."


class BrowserTTSProvider(VoiceCloneProvider):
    name = "browser_tts_fallback"
    is_cloning_provider = False

    def generate(
        self,
        *,
        text: str,
        reference_audio_path: str,
        participant_id: str,
        session_id: str,
        out_path: str,
    ) -> str:
        if not reference_audio_path or not Path(reference_audio_path).exists():
            raise ReferenceAudioMissingError(
                f"No verified reference audio sample found for participant {participant_id}."
            )

        logger.warning(
            "%s Generating non-cloned placeholder speech for participant=%s session=%s",
            FALLBACK_LABEL,
            participant_id,
            session_id,
        )
        synthesize_speech_wav(text, out_path)
        return out_path
