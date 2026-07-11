"""
LocalCloneProvider -- the default voice-cloning provider.

Uses a local, open-source zero-shot voice-cloning model (Coqui XTTS-v2)
that conditions generation on a short reference clip, entirely offline
after the model weights are downloaded once. No audio or text ever leaves
the machine.

This is a heavyweight optional dependency (torch + coqui-tts, several GB
of model weights on first run) that is deliberately NOT required to run
the demo -- see requirements.txt and README.md. If the `TTS` package or
model isn't available, this provider raises ProviderUnavailableError and
the generation pipeline falls back to BrowserTTSProvider, surfacing a
clearly labeled warning to the host (safety requirement: fallback must
never be silent).
"""
import logging
from pathlib import Path
from typing import Optional

from app.providers.base import (
    ProviderUnavailableError,
    ReferenceAudioMissingError,
    VoiceCloneProvider,
)

logger = logging.getLogger("voice_demo.providers.local_clone")


class LocalCloneProvider(VoiceCloneProvider):
    name = "local_clone"
    is_cloning_provider = True

    def __init__(self, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        self.model_name = model_name
        self._model = None  # lazy-loaded on first successful generate()

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            # Imported lazily: importing torch/TTS is slow and, in most
            # local demo setups, this package simply isn't installed --
            # that's expected and handled by falling back below.
            from TTS.api import TTS  # type: ignore
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Local voice-cloning model ('TTS' / Coqui XTTS-v2) is not installed "
                f"or failed to import: {exc}. Install it per README.md to enable real "
                f"voice cloning, or continue using the labeled BrowserTTSProvider fallback."
            ) from exc

        try:
            self._model = TTS(self.model_name)
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Failed to load local voice-cloning model '{self.model_name}': {exc}"
            ) from exc
        return self._model

    def generate(
        self,
        *,
        text: str,
        reference_audio_path: str,
        participant_id: str,
        session_id: str,
        out_path: str,
    ) -> str:
        # Abuse-prevention control: never call the model without a real,
        # already-validated reference sample belonging to this participant.
        # The caller (generation_pipeline.py) is responsible for having
        # already verified consent + sample validity; this is a defense in
        # depth check against programming errors, not the primary gate.
        if not reference_audio_path or not Path(reference_audio_path).exists():
            raise ReferenceAudioMissingError(
                f"No verified reference audio sample found for participant {participant_id}."
            )

        model = self._load_model()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            model.tts_to_file(
                text=text,
                speaker_wav=reference_audio_path,
                language="en",
                file_path=out_path,
            )
        except Exception as exc:
            raise ProviderUnavailableError(f"Local voice-cloning generation failed: {exc}") from exc

        logger.info(
            "local_clone generated audio for participant=%s session=%s", participant_id, session_id
        )
        return out_path
