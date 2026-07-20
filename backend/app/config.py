"""
Central configuration for the voice-cloning demo backend.

All values are read from environment variables (see .env.example) so the
demo can be reconfigured without touching code. Nothing here should be
treated as production-grade hardening -- see SECURITY.md.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite database file. Kept local and file-based on purpose: this is a
# local proof-of-concept, not a multi-tenant service.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'voice_demo.db'}")

# Where uploaded live-recorded reference samples and generated clips live.
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
AUDIO_SAMPLE_DIR = STORAGE_DIR / "audio_samples"
GENERATED_DIR = STORAGE_DIR / "generated"
AUDIO_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# --- Data retention / TTL -------------------------------------------------
# Non-negotiable safety requirement #19/#21: nothing persists indefinitely.
# Default TTL is intentionally short (24h) and is configurable per-session
# by the host at creation time (bounded by MAX/MIN below).
DEFAULT_TTL_SECONDS = int(os.getenv("DEFAULT_TTL_SECONDS", str(24 * 60 * 60)))
MIN_TTL_SECONDS = int(os.getenv("MIN_TTL_SECONDS", str(5 * 60)))          # 5 minutes
MAX_TTL_SECONDS = int(os.getenv("MAX_TTL_SECONDS", str(7 * 24 * 60 * 60)))  # 7 days

# How often the background cleanup sweep runs (seconds).
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "60"))

# --- Capture session binding ----------------------------------------------
# Safety requirement #14/#15: the consent phrase and the reference sample
# must come from one uninterrupted browser capture. We allow a short grace
# window between the two segments landing on the server (network latency),
# but anything longer strongly suggests the "continuous capture" was
# actually interrupted, so we invalidate it.
CAPTURE_SESSION_MAX_GAP_SECONDS = int(os.getenv("CAPTURE_SESSION_MAX_GAP_SECONDS", "120"))

# --- Voice provider ---------------------------------------------------------
# Safety requirement: LocalCloneProvider is ALWAYS the default. This flag
# exists purely so automated tests can force fallback behavior without
# needing to uninstall ML dependencies. It must never be enabled to make
# BrowserTTSProvider the product default in a real deployment.
FORCE_FALLBACK_PROVIDER = os.getenv("FORCE_FALLBACK_PROVIDER", "false").lower() == "true"

# Sample audio format used for every clip WE synthesize (disclosure speech,
# and BrowserTTSProvider fallback output). Standardizing this makes it safe
# to concatenate clips with simple stdlib WAV handling (no ffmpeg/pydub
# dependency needed for the demo).
SYNTH_SAMPLE_RATE = 22050
SYNTH_SAMPLE_WIDTH = 2  # bytes (16-bit PCM)
SYNTH_CHANNELS = 1

DISCLOSURE_TEXT = (
    "This is AI-generated audio created for a consent-based cybersecurity "
    "education demo."
)

CONSENT_PHRASE_TEXT = (
    "I consent to this voice sample being used for this cybersecurity "
    "education demo."
)

HOST_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Reject audio-sample uploads larger than this. This is a demo running on
# a single machine for short clips, not a media platform.
MAX_AUDIO_UPLOAD_BYTES = int(os.getenv("MAX_AUDIO_UPLOAD_BYTES", str(20 * 1024 * 1024)))  # 20 MB

# Reject reference samples shorter than this (see findings.md Finding 3: a
# too-short clip produces a weak speaker embedding, which XTTS renders as
# garbled/unintelligible speech instead of erroring out).
MIN_AUDIO_SAMPLE_DURATION_SECONDS = float(os.getenv("MIN_AUDIO_SAMPLE_DURATION_SECONDS", "5"))

# Reject reference samples whose peak level (dBFS, reported by the browser
# after decoding its own recording) is below this. A silent/near-silent
# clip (e.g. muted mic, wrong input device) still has a normal duration but
# gives XTTS no real voice to condition on, producing a generic/unrelated-
# sounding clone instead of erroring out. -50 dBFS is well below any actual
# recorded speech but well above true silence/room noise floor.
MIN_AUDIO_SAMPLE_PEAK_DBFS = float(os.getenv("MIN_AUDIO_SAMPLE_PEAK_DBFS", "-50"))

