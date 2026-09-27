"""routers/health.py — health & root.

GET /api/            : root (dipakai gate.sh untuk deteksi backend UP).
GET /api/health      : ringkasan status service + koneksi DB + kesiapan inisialisasi (ready, init_errors).
"""
from fastapi import APIRouter

from core_utils import now_iso
from db import get_db
from services.startup import STATE

router = APIRouter(tags=["health"])


@router.get("/")
async def root():
    return {"service": "collector-parfum", "status": "ok", "message": "Collector Parfum API"}


@router.get("/health")
async def health():
    db = get_db()
    db_ok = True
    try:
        await db.command("ping")
    except Exception:
        db_ok = False
    ready = db_ok and STATE["ready"]
    return {"status": "ok" if ready else "degraded", "db": db_ok, "ready": ready,
            "init_errors": STATE["errors"][:20], "time": now_iso()}
