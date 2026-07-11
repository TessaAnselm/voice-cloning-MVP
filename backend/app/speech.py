"""
Text-to-speech helper shared by the spoken disclosure (required on every
generated clip, safety requirement #18) and BrowserTTSProvider's fallback
output.

Three-tier fallback, each tier requiring nothing beyond what's already on
the machine or in requirements.txt:

  1. macOS `say` CLI, asked to emit a real WAV (LEI16@22050) directly --
     avoids the fact that pyttsx3's macOS backend (NSSpeechSynthesizer)
     only writes AIFF-C, which Python's stdlib can no longer decode
     (the `aifc` module was removed in Python 3.13).
  2. `pyttsx3` (wraps SAPI5 on Windows, espeak on Linux) for other OSes.
  3. A non-speech tone placeholder so the app never crashes even on a
     machine with no system TTS engine at all -- intentionally
     unrealistic-sounding so nobody mistakes it for a real voice.
"""
import logging
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.audio_utils import standardize_wav, synthesize_tone_placeholder

logger = logging.getLogger("voice_demo.speech")


def _try_macos_say(text: str, raw_path: str) -> bool:
    if platform.system() != "Darwin" or shutil.which("say") is None:
        return False
    try:
        subprocess.run(
            [
                "say",
                "-o", raw_path,
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
                text,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return Path(raw_path).exists() and Path(raw_path).stat().st_size > 0
    except Exception as exc:  # pragma: no cover - depends on host `say` availability
        logger.warning("macOS `say` TTS failed (%s); trying next fallback.", exc)
        return False


def _try_pyttsx3(text: str, raw_path: str) -> bool:
    try:
        import pyttsx3  # optional dependency, see requirements.txt

        engine = pyttsx3.init()
        engine.save_to_file(text, raw_path)
        engine.runAndWait()
        engine.stop()
        return Path(raw_path).exists() and Path(raw_path).stat().st_size > 0
    except Exception as exc:  # pragma: no cover - depends on host TTS engine availability
        logger.warning("pyttsx3 TTS unavailable (%s); trying next fallback.", exc)
        return False


def synthesize_speech_wav(text: str, out_path: str) -> str:
    """Render `text` to a standardized mono WAV file at `out_path`."""
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = str(Path(tmp) / "raw_tts_output.wav")

        if _try_macos_say(text, raw_path):
            try:
                return standardize_wav(raw_path, out_path)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to standardize `say` output (%s); trying next fallback.", exc)

        if _try_pyttsx3(text, raw_path):
            try:
                return standardize_wav(raw_path, out_path)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to standardize pyttsx3 output (%s); using tone placeholder.", exc)

    logger.warning("No system TTS engine produced usable output; using tone placeholder.")
    return synthesize_tone_placeholder(text, out_path)
