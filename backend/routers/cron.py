"""routers/cron.py — endpoint cron terjadwal (platform `.emergent/crons.yml` / cron VPS).

Semua: Authorization: Bearer $WEBHOOK_CRON_SECRET -> 202. Kerja nyata di background;
run_id (X-Webhook-Id) dipakai sebagai kunci idempotensi.
POST /api/cron/expire-orders      — batalkan order lewat batas bayar (tiap 15 menit)
POST /api/cron/payment-reminders  — email pengingat 12 jam & 2 jam sebelum batas bayar (tiap 15 menit)
POST /api/cron/sync-payments      — tarik ulang status transaksi Midtrans pending (webhook terlewat, tiap 10 menit)
POST /api/cron/daily-backup       — backup harian otomatis semua koleksi (simpan 14 terakhir)
POST /api/cron/reconcile          — lanjutkan pekerjaan terputus: reservasi, pembatalan, bukti, uang gateway, refund, email (tiap 10 menit)
run_id yang `failed` atau macet (`queued`/`running` > STALE_MIN menit, worker mati) DIAMBIL ULANG saat dikirim lagi.
"""
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pymongo.errors import DuplicateKeyError

from core_utils import new_id, now_iso
from db import get_db
from services import gateway as gateway_svc
from services import notify
from services.backup_auto import daily_backup
from services.order_expiry import expire_overdue_orders
from services import reconcile as reconcile_svc

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger("collector_parfum")

JOBS = {
    "expire-orders": expire_overdue_orders,
    "payment-reminders": notify.send_payment_reminders,
    "sync-payments": gateway_svc.sync_pending,
    "daily-backup": daily_backup,
    "reconcile": reconcile_svc.run,
}
STALE_MIN = 10


def _authorized(authorization):
    secret = os.environ["WEBHOOK_CRON_SECRET"]
    if not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization[7:].strip(), secret)


async def _run(job, run_id):
    db = get_db()
    await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "running", "started_at": now_iso()}})
    try:
        res = await JOBS[job](db)
        summary = {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {
            "status": "done", "result": summary, "finished_at": now_iso()}})
    except Exception as e:  # dicatat, tak boleh mematikan worker
        logger.exception("cron %s gagal", job)
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "error": str(e)[:300]}})


async def _reclaim(run_id):
    """run_id sama: ambil ulang bila gagal / macet (worker mati) — CAS agar hanya satu yang menang."""
    db = get_db()
    cur = await db.cron_runs.find_one({"run_id": run_id})
    stale = (datetime.now(timezone.utc) - timedelta(minutes=STALE_MIN)).isoformat()
    touched = cur.get("started_at") or cur.get("created_at") or ""
    if not cur or not (cur.get("status") == "failed" or (cur.get("status") in ("queued", "running") and touched < stale)):
        return False
    res = await db.cron_runs.update_one(
        {"run_id": run_id, "status": cur["status"], "attempt": cur.get("attempt")},
        {"$set": {"status": "queued", "created_at": now_iso(), "attempt": int(cur.get("attempt") or 1) + 1}})
    return res.modified_count == 1


async def _accept(job, background, authorization, x_webhook_id):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = (x_webhook_id or new_id("cron"))[:120]
    try:
        await get_db().cron_runs.insert_one({"run_id": run_id, "job": job,
                                             "status": "queued", "created_at": now_iso()})
    except DuplicateKeyError:
        if not await _reclaim(run_id):
            return {"accepted": True, "duplicate": True}
    background.add_task(_run, job, run_id)
    return {"accepted": True, "run_id": run_id}


@router.post("/expire-orders", status_code=202)
async def expire_orders(background: BackgroundTasks, authorization: str = Header(default=""),
                        x_webhook_id: str = Header(default="")):
    return await _accept("expire-orders", background, authorization, x_webhook_id)


@router.post("/payment-reminders", status_code=202)
async def payment_reminders(background: BackgroundTasks, authorization: str = Header(default=""),
                            x_webhook_id: str = Header(default="")):
    return await _accept("payment-reminders", background, authorization, x_webhook_id)


@router.post("/sync-payments", status_code=202)
async def sync_payments(background: BackgroundTasks, authorization: str = Header(default=""),
                        x_webhook_id: str = Header(default="")):
    return await _accept("sync-payments", background, authorization, x_webhook_id)


@router.post("/daily-backup", status_code=202)
async def daily_backup_job(background: BackgroundTasks, authorization: str = Header(default=""),
                           x_webhook_id: str = Header(default="")):
    return await _accept("daily-backup", background, authorization, x_webhook_id)


@router.post("/reconcile", status_code=202)
async def reconcile_job(background: BackgroundTasks, authorization: str = Header(default=""),
                        x_webhook_id: str = Header(default="")):
    return await _accept("reconcile", background, authorization, x_webhook_id)
