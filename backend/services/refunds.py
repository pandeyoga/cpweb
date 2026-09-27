"""services/refunds.py — refund pesanan yang aman diulang (butir 3).

- Identitas refund STABIL: dokumen `refunds` berstatus `requested` dibuat SEBELUM memanggil gateway;
  retry (timeout/klik ulang/rekonsiliasi) memakai id yang sama sebagai `refund_key` Midtrans.
- Efek uang idempoten: `orders.refunded_amount` & `payment_transactions.refunded_amount` dinaikkan
  dengan penanda `applied_refunds` di update yang sama → tak pernah dobel.
- Sisa refund = dana masuk − refund; transaksi yatim (dibayar setelah order batal) punya saldo sendiri.
- Pembayaran manual (transfer/e-wallet) → refund dicatat manual (tanpa gateway).
- Refund yang dibuat di luar aplikasi (dashboard Midtrans) direkam dari notifikasi (`record_gateway_refunds`).
"""
from datetime import datetime, timedelta, timezone

from core_utils import new_id, now_iso, safe_doc
from services import midtrans as mt
from services.audit import log_action


class RefundError(Exception):
    """400 — aturan refund."""


async def _apply(db, ref, order_code, tx_id, amount):
    """Naikkan saldo refund order (+ transaksi) tepat sekali untuk refund `ref`."""
    await db.orders.update_one({"code": order_code, "applied_refunds": {"$ne": ref}},
                               {"$inc": {"refunded_amount": amount}, "$push": {"applied_refunds": ref}})
    if tx_id:
        await db.payment_transactions.update_one(
            {"id": tx_id, "applied_refunds": {"$ne": ref}},
            {"$inc": {"refunded_amount": amount}, "$push": {"applied_refunds": ref}})
        tx = await db.payment_transactions.find_one({"id": tx_id})
        left = int(tx["gross_amount"]) - int(tx.get("refunded_amount", 0) or 0)
        await db.payment_transactions.update_one({"id": tx_id}, {"$set": {
            "status": "refund" if left <= 0 else "partial_refund",
            "needs_refund": bool(tx.get("orphan")) and left > 0, "updated_at": now_iso()}})


def _refundable(order, tx):
    if tx and tx.get("orphan"):  # dana tak pernah tercatat di order → saldo transaksi sendiri
        return int(tx["gross_amount"]) - int(tx.get("refunded_amount", 0) or 0)
    return int(order.get("paid_amount", 0) or 0) - int(order.get("refunded_amount", 0) or 0)


async def _finish(db, rf):
    """Terapkan refund `requested` yang sudah diterima gateway (idempoten) → `done`."""
    await _apply(db, rf["id"], rf["order_code"], rf.get("tx_id"), int(rf["amount"]))
    await db.refunds.update_one({"id": rf["id"]}, {"$set": {"status": "done", "done_at": now_iso()}})


async def refund_order(db, admin_id, order, amount, reason, transition):
    """`transition(db, order, to, reason)` = orders.transition_order (disuntik, hindari impor melingkar)."""
    pending = await db.refunds.find_one({"order_code": order["code"], "status": "requested"})
    if pending:  # retry → identitas & nominal yang sama
        rf = pending
    else:
        tx = await db.payment_transactions.find_one(
            {"order_code": order["code"], "status": {"$in": ["paid", "partial_refund"]}},
            sort=[("needs_refund", -1), ("created_at", 1)])
        online = (order.get("payment") or {}).get("group") == "online"
        if not tx and online:
            raise RefundError("Tidak ada pembayaran online yang bisa di-refund")
        refundable = _refundable(order, tx)
        amount = int(amount or refundable)
        if amount <= 0 or amount > refundable:
            raise RefundError("Nominal refund melebihi dana yang bisa dikembalikan")
        rf = {"id": new_id("rfd"), "order_code": order["code"], "tx_id": (tx or {}).get("id"),
              "gateway_order_id": (tx or {}).get("gateway_order_id"), "amount": amount,
              "orphan": bool((tx or {}).get("orphan")), "manual": not tx, "reason": (reason or "")[:250],
              "admin_id": admin_id, "status": "requested", "source": "admin", "created_at": now_iso()}
        await db.refunds.insert_one(dict(rf))
    if rf.get("gateway_order_id"):
        try:
            await mt.refund(rf["gateway_order_id"], int(rf["amount"]), rf.get("reason") or "Refund pesanan", rf["id"])
        except mt.GatewayError as e:
            raise RefundError(f"{e} — refund tersimpan sebagai tertunda; ulangi untuk mencoba lagi") from e
    await _finish(db, rf)
    await log_action(admin_id, "refund", "orders", order["code"],
                     {"amount": int(rf["amount"]), "orphan": rf.get("orphan"), "manual": rf.get("manual")})
    fresh = await db.orders.find_one({"code": order["code"]})
    fully = int(fresh.get("paid_amount", 0) or 0) - int(fresh.get("refunded_amount", 0) or 0) <= 0
    if not rf.get("orphan") and fully and fresh["status"] in ("paid", "packed"):
        return await transition(db, fresh, "cancelled", reason="refunded")
    return safe_doc(fresh)


async def record_gateway_refunds(db, tx, n):
    """Notifikasi/status refund dari Midtrans: rekam refund yang belum dikenal (idempoten per refund_key)."""
    for r in n.get("refunds") or []:
        key = str(r.get("refund_key") or r.get("refund_chargeback_id") or "")[:80]
        try:
            amount = int(float(r.get("refund_amount", 0)))
        except (TypeError, ValueError):
            continue
        if not key or amount <= 0:
            continue
        await db.refunds.update_one({"id": key}, {"$setOnInsert": {
            "id": key, "order_code": tx["order_code"], "tx_id": tx["id"], "gateway_order_id": tx["gateway_order_id"],
            "amount": amount, "orphan": bool(tx.get("orphan")), "manual": False, "reason": "Refund dari Midtrans",
            "admin_id": "gateway", "status": "requested", "source": "gateway", "created_at": now_iso()}}, upsert=True)
        rf = await db.refunds.find_one({"id": key})
        if rf["status"] == "requested":
            await _finish(db, rf)


async def retry_pending(db, min_age_minutes=5):
    """Rekonsiliasi: refund `requested` yang terputus → ulangi dengan refund_key yang sama."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)).isoformat()
    done = []
    for rf in await db.refunds.find({"status": "requested", "created_at": {"$lt": cutoff}}).to_list(100):
        try:
            if rf.get("gateway_order_id") and rf.get("source") == "admin":
                await mt.refund(rf["gateway_order_id"], int(rf["amount"]), rf.get("reason") or "Refund", rf["id"])
            await _finish(db, rf)
            done.append(rf["id"])
        except mt.GatewayError:
            continue
    return done
