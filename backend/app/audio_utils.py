"""
Minimal, dependency-free WAV utilities.

These are only used for audio clips WE synthesize server-side (the spoken
disclosure, and the BrowserTTSProvider fallback's placeholder speech/tone).
Participant reference recordings from the browser are stored as-is and are
never rewritten by this module -- see providers/local_clone.py for why.

Deliberately avoids ffmpeg/pydub/audioop (audioop is removed in newer
Python versions) so the demo has no native/system audio dependency beyond
whatever the optional `pyttsx3` package needs.
"""
import array
import math
import wave
from pathlib import Path
from typing import List

from app.config import SYNTH_CHANNELS, SYNTH_SAMPLE_RATE, SYNTH_SAMPLE_WIDTH


def read_wav_int16_mono(path: str) -> "tuple[int, array.array]":
    """Read a WAV file and return (sample_rate, samples) as mono int16."""
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth != 2:
        raise ValueError(f"Unsupported sample width {sampwidth}; expected 16-bit PCM.")

    samples = array.array("h")
    samples.frombytes(raw)

    if channels > 1:
        # Downmix to mono by averaging channels.
        mono = array.array("h", [0] * (len(samples) // channels))
        for i in range(len(mono)):
            frame = samples[i * channels : (i + 1) * channels]
            mono[i] = int(sum(frame) / channels)
        samples = mono

    return sample_rate, samples


def write_wav_int16_mono(path: str, sample_rate: int, samples: array.array) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def _resample_linear(samples: array.array, src_rate: int, dst_rate: int) -> array.array:
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    ratio = dst_rate / src_rate
    out_len = max(1, int(len(samples) * ratio))
    out = array.array("h", [0] * out_len)
    for i in range(out_len):
        src_pos = i / ratio
        idx = int(src_pos)
        frac = src_pos - idx
        s0 = samples[idx] if idx < len(samples) else samples[-1]
        s1 = samples[idx + 1] if idx + 1 < len(samples) else s0
        out[i] = int(s0 + (s1 - s0) * frac)
    return out


def standardize_wav(in_path: str, out_path: str) -> str:
    """Rewrite any 16-bit WAV to the project-standard mono/rate for concatenation."""
    sample_rate, samples = read_wav_int16_mono(in_path)
    resampled = _resample_linear(samples, sample_rate, SYNTH_SAMPLE_RATE)
    write_wav_int16_mono(out_path, SYNTH_SAMPLE_RATE, resampled)
    return out_path


def concat_wavs(paths: List[str], out_path: str, gap_ms: int = 400) -> str:
    """
    Concatenate already-standardized (same rate/mono/16-bit) WAV files with a
    short silence gap between them. Used to append the spoken disclosure to
    every generated clip (safety requirement #18).
    """
    gap_samples = array.array("h", [0] * int(SYNTH_SAMPLE_RATE * gap_ms / 1000))
    combined = array.array("h")
    for i, path in enumerate(paths):
        _, samples = read_wav_int16_mono(path)
        combined.extend(samples)
        if i != len(paths) - 1:
            combined.extend(gap_samples)
    write_wav_int16_mono(out_path, SYNTH_SAMPLE_RATE, combined)
    return out_path


def synthesize_tone_placeholder(text: str, out_path: str) -> str:
    """
    Last-resort, zero-dependency "speech" synthesis: a short sequence of
    tones whose length scales with the text length. This is NOT real
    speech. It exists purely so the demo never crashes when no system TTS
    engine is available (e.g. a headless Linux box with no `espeak`), and
    it is only ever used by BrowserTTSProvider, which is already labeled
    "does not clone voices" everywhere in the UI and logs.
    """
    duration_s = max(0.6, min(4.0, 0.05 * len(text)))
    n_samples = int(SYNTH_SAMPLE_RATE * duration_s)
    samples = array.array("h", [0] * n_samples)
    freq = 220.0
    amplitude = 6000
    for i in range(n_samples):
        t = i / SYNTH_SAMPLE_RATE
        # Gentle warble so it's audibly distinct from silence/disclosure tone.
        f = freq * (1 + 0.15 * math.sin(2 * math.pi * 2 * t))
        samples[i] = int(amplitude * math.sin(2 * math.pi * f * t))
    write_wav_int16_mono(out_path, SYNTH_SAMPLE_RATE, samples)
    return out_path


def wav_duration_seconds(path: str) -> float:
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())
