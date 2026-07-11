"""
FastAPI application entrypoint.

Wires up all routers, CORS, DB init, and a background sweep task that
enforces data-expiration (safety requirement #19) even if no one hits the
API for a while.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cleanup import purge_expired_audio_samples, sweep_expired
from app.config import CLEANUP_INTERVAL_SECONDS, HOST_CORS_ORIGINS
from app.database import SessionLocal, init_db
from app.routers import generation, health, participants, sessions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_demo.main")


async def _cleanup_loop():
    while True:
        try:
            db = SessionLocal()
            try:
                purged = sweep_expired(db)
                stale_samples = purge_expired_audio_samples(db)
                if purged or stale_samples:
                    logger.info(
                        "Cleanup sweep: purged %d expired session(s), %d stale sample(s).",
                        purged,
                        stale_samples,
                    )
            finally:
                db.close()
        except Exception:  # pragma: no cover - keep the sweep loop alive
            logger.exception("Cleanup sweep failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="Consent-Based Voice Cloning Demo",
    description=(
        "Local cybersecurity education proof-of-concept demonstrating a "
        "consent-based voice-cloning product flow. Not for production use. "
        "See SECURITY.md."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=HOST_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(participants.router)
app.include_router(generation.router)
