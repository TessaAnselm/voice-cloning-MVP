"""Liveness endpoint."""
from fastapi import APIRouter

from app.config import FORCE_FALLBACK_PROVIDER

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "fallback_forced": FORCE_FALLBACK_PROVIDER}
