"""services/notify.py — email transaksional pesanan (E15): konfirmasi lunas + pengingat batas bayar.

Idempoten: tiap jenis email ditandai di `orders.emails_sent` via compare-and-set ($ne + $addToSet)
→ webhook ganda / cron paralel tak pernah mengirim dobel. SMTP gagal → penanda DILEPAS dan kunci masuk
`emails_failed` → job rekonsiliasi mengirim ulang (maks MAX_ATTEMPTS) tanpa duplikasi (butir 9).
Pengingat: slot 12 jam & 2 jam sebelum `payment_deadline` (bila tersisa ≤2 jam, hanya slot 2 jam).
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from services import email_templates as tpl
from services import mailer

logger = logging.getLogger("collector_parfum")
REMINDER_HORIZON_H = 12
MAX_ATTEMPTS = 5
_tasks = set()


def order_link(order):
    site = os.environ["PUBLIC_SITE_URL"].rstrip("/")
    return f"{site}/pesanan-sukses?code={quote(order['code'])}&t={quote(order.get('access_token') or '')}"


async def _claim(db, code, key):
    res = await db.orders.update_one({"code": code, "emails_sent": {"$ne": key}},
                                     {"$addToSet": {"emails_sent": key}})
    return res.modified_count == 1


async def _deliver(db, code, key, **mail):
    """Kirim; bila gagal lepas penanda agar bisa diulang (bukan tertandai terkirim selamanya)."""
    log = await mailer.send(db, order_code=code, **mail)
    if (log or {}).get("status") == "failed":
        await db.orders.update_one({"code": code}, {"$pull": {"emails_sent": key},
                                                    "$addToSet": {"emails_failed": key},
                                                    "$inc": {f"email_attempts.{key.replace('.', '_')}": 1}})
    return log


async def retry_failed(db):
    """Kirim ulang email transaksional yang gagal (paid/shipped). Pengingat kedaluwarsa tak diulang."""
    retried = []
    for o in await db.orders.find({"emails_failed.0": {"$exists": True}}, {"code": 1, "emails_failed": 1,
                                                                            "email_attempts": 1}).to_list(100):
        for key in o["emails_failed"]:
            res = await db.orders.update_one({"code": o["code"], "emails_failed": key}, {"$pull": {"emails_failed": key}})
            if not res.modified_count or (o.get("email_attempts") or {}).get(key.replace(".", "_"), 0) >= MAX_ATTEMPTS:
                continue
            if key == "paid":
                await send_paid_confirmation(db, o["code"])
            elif key.startswith("shipped:"):
                await send_shipped(db, o["code"])
            retried.append(f"{o['code']}:{key}")
    return retried


async def send_paid_confirmation(db, code):
    order = await db.orders.find_one({"code": code})
    if not order or not order.get("email") or not await _claim(db, code, "paid"):
        return None
    subject, html, text = tpl.paid_confirmation(order, order_link(order))
    return await _deliver(db, code, "paid", kind="paid_confirmation", to=order["email"], subject=subject,
                          html=html, text=text)


async def _safe(coro):
    try:
        await coro
    except Exception:  # email tak boleh menggagalkan alur pembayaran
        logger.exception("kirim email gagal")


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(_safe(coro))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def paid_async(db, code):
    """Dipanggil saat order → paid. Tak menahan webhook/verifikasi admin."""
    _spawn(send_paid_confirmation(db, code))


async def send_shipped(db, code):
    """Email resi. Kunci dedupe per kurir+resi → koreksi resi = email ulang, simpan ulang = tidak."""
    order = await db.orders.find_one({"code": code})
    sh = (order or {}).get("shipment") or {}
    if not order or not order.get("email") or not sh.get("tracking_number"):
        return None
    first = not any(str(k).startswith("shipped:") for k in order.get("emails_sent", []))
    key = f"shipped:{sh['courier']}:{sh['tracking_number']}"
    if not await _claim(db, code, key):
        return None
    subject, html, text = tpl.order_shipped(order, order_link(order), correction=not first)
    return await _deliver(db, code, key, kind="shipped" if first else "shipped_update", to=order["email"],
                          subject=subject, html=html, text=text)


def shipped_async(db, code):
    _spawn(send_shipped(db, code))


async def send_payment_reminders(db, now=None):
    now = now or datetime.now(timezone.utc)
    horizon = (now + timedelta(hours=REMINDER_HORIZON_H)).isoformat()
    docs = await db.orders.find({
        "status": "pending", "payment_status": "belum_bayar", "email": {"$nin": ["", None]},
        "payment_deadline": {"$gt": now.isoformat(), "$lte": horizon},
    }).to_list(500)
    sent, skipped = [], []
    for o in docs:
        if await db.payment_proofs.count_documents({"order_code": o["code"], "status": "pending"}):
            skipped.append(o["code"])  # bukti transfer menunggu verifikasi admin
            continue
        left_h = (datetime.fromisoformat(o["payment_deadline"]) - now).total_seconds() / 3600
        slot = "reminder_2h" if left_h <= 2 else "reminder_12h"
        if not await _claim(db, o["code"], slot):
            continue
        subject, html, text = tpl.payment_reminder(o, order_link(o), left_h)
        await _deliver(db, o["code"], slot, kind=slot, to=o["email"], subject=subject, html=html, text=text)
        sent.append(o["code"])
    return {"sent": sent, "skipped": skipped}
