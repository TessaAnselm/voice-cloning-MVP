"""
Generation pipeline: the ONLY code path allowed to call a VoiceCloneProvider.

Order of operations is the core safety contract of this app and must never
be reordered:

  1. Consent / session / audio-sample guards        (app/guards.py)
  2. Content filter                                  (app/content_filter.py)
  3. Provider.generate()  (LocalCloneProvider, falling back to
     BrowserTTSProvider only if the local model is unavailable)
  4. Spoken disclosure is embedded into the output    (app/audio_utils.py)

If step 1 or 2 fails, the provider is never invoked. Every attempt --
blocked or not -- is logged by the router via the Generation table.
"""
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.audio_utils import concat_wavs, standardize_wav
from app.config import DISCLOSURE_TEXT, FORCE_FALLBACK_PROVIDER, GENERATED_DIR
from app.providers import (
    BrowserTTSProvider,
    LocalCloneProvider,
    ProviderUnavailableError,
    ReferenceAudioMissingError,
)
from app.speech import synthesize_speech_wav

logger = logging.getLogger("voice_demo.generation_pipeline")

_local_provider = LocalCloneProvider()
_fallback_provider = BrowserTTSProvider()


@dataclass
class GenerationOutcome:
    output_file_path: str
    provider_used: str
    fallback_active: bool


def run_generation(
    *,
    text: str,
    reference_audio_path: str,
    participant_id: str,
    session_id: str,
) -> GenerationOutcome:
    """
    Runs ONLY after guards.py and content_filter.py have already approved
    the request (enforced by the /generate-voice router, not here -- this
    function assumes it's safe to call the provider).
    """
    generation_id = str(uuid.uuid4())
    raw_out_path = str(GENERATED_DIR / f"{generation_id}_raw.wav")

    provider_used = "local_clone"
    fallback_active = False

    if FORCE_FALLBACK_PROVIDER:
        # Test-only escape hatch -- see config.py. Never true by default.
        fallback_active = True
        provider_used = _fallback_provider.name
        _fallback_provider.generate(
            text=text,
            reference_audio_path=reference_audio_path,
            participant_id=participant_id,
            session_id=session_id,
            out_path=raw_out_path,
        )
    else:
        try:
            _local_provider.generate(
                text=text,
                reference_audio_path=reference_audio_path,
                participant_id=participant_id,
                session_id=session_id,
                out_path=raw_out_path,
            )
        except ReferenceAudioMissingError:
            # Do NOT fall back on missing reference audio -- that's a
            # consent/data problem, not a provider-availability problem,
            # and falling back would let generation succeed without a
            # verified sample. Propagate so the router blocks the request.
            raise
        except ProviderUnavailableError as exc:
            logger.warning(
                "LocalCloneProvider unavailable (%s); using BrowserTTSProvider fallback. "
                "This clip will NOT be a real voice clone.",
                exc,
            )
            fallback_active = True
            provider_used = _fallback_provider.name
            _fallback_provider.generate(
                text=text,
                reference_audio_path=reference_audio_path,
                participant_id=participant_id,
                session_id=session_id,
                out_path=raw_out_path,
            )

    # Safety requirement #18: every generated clip, from every provider,
    # gets the spoken disclosure appended -- no provider can opt out of
    # this because it happens here, outside the provider classes.
    standardized_raw = str(GENERATED_DIR / f"{generation_id}_raw_std.wav")
    standardize_wav(raw_out_path, standardized_raw)

    disclosure_path = str(GENERATED_DIR / f"{generation_id}_disclosure.wav")
    synthesize_speech_wav(DISCLOSURE_TEXT, disclosure_path)

    final_path = str(GENERATED_DIR / f"{generation_id}_final.wav")
    concat_wavs([standardized_raw, disclosure_path], final_path)

    # Clean up intermediate files; only the final disclosed clip is kept.
    for p in (raw_out_path, standardized_raw, disclosure_path):
        Path(p).unlink(missing_ok=True)

    return GenerationOutcome(
        output_file_path=final_path,
        provider_used=provider_used,
        fallback_active=fallback_active,
    )
