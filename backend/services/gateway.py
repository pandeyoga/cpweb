"""services/gateway.py — alur pembayaran ONLINE (Midtrans Snap) di atas SSOT order. Epic E14.

- start_payment(): buat/pakai ulang snap_token per order (attempt baru → `CODE-n`). Nominal SELALU
  dari server (`order.total`); item_details dijumlahkan persis = gross_amount.
- apply_notification(): pemetaan status Midtrans → SSOT (`record_payment` / `transition_order`).
  Idempoten & dapat dipulihkan (butir 3): tx `paid` + `payment_applied` terpisah; record_payment
  ber-penanda id transaksi → webhook ulang / rekonsiliasi melengkapi uang yang belum tercatat.
- start_payment(): kunci per order (`pay_locks`) → dua request /pay paralel tak membuat dua attempt.
- refund_order(): services/refunds (identitas stabil, saldo parsial, yatim, manual).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from core_utils import new_id, now_iso
from services import midtrans as mt
from services import orders as orders_svc
from services import refunds as refunds_svc

PAID, PENDING = {"settlement", "capture"}, "pending"
SETTLED = ["paid", "refund", "partial_refund"]  # dana pernah masuk (rekonsiliasi INV-P1)


class PaymentError(Exception):
    """400/409 — aturan bisnis pembayaran online."""


def _items(order):
    items = [{"id": (it.get("sku") or it["product_id"])[:50], "price": int(it["unit_price"]),
              "quantity": int(it["quantity"]), "name": f"{it.get('name', '')} {it.get('variant_type', '')}".strip()[:50]}
             for it in order.get("items", [])]
    ship = int((order.get("shipping") or {}).get("price", 0) or 0)
    if ship:
        items.append({"id": "ONGKIR", "price": ship, "quantity": 1, "name": "Ongkos kirim"[:50]})
    if int(order.get("discount", 0) or 0):
        items.append({"id": "DISKON", "price": -int(order["discount"]), "quantity": 1,
                      "name": f"Voucher {order.get('voucher_code') or ''}".strip()[:50]})
    return items


def _minutes_left(order):
    dl = datetime.fromisoformat(order["payment_deadline"])
    return int((dl - datetime.now(timezone.utc)).total_seconds() // 60)


async def start_payment(db, order):
    if not mt.enabled():
        raise PaymentError("Pembayaran online belum dikonfigurasi")
    if (order.get("payment") or {}).get("group") != "online":
        raise PaymentError("Pesanan ini tidak memakai pembayaran online")
    if order.get("status") != "pending" or order.get("payment_status") != "belum_bayar":
        raise PaymentError("Pesanan tidak menunggu pembayaran")
    minutes = _minutes_left(order)
    if minutes < 1:
        raise PaymentError("Batas waktu pembayaran sudah lewat")
    live = await _live_tx(db, order["code"])
    if live:
        return _public_tx(live)
    lock_exp = datetime.now(timezone.utc) + timedelta(seconds=30)
    try:
        await db.pay_locks.insert_one({"order_code": order["code"], "expires_at": lock_exp})
    except DuplicateKeyError:  # request paralel sedang membuat attempt → tunggu hasilnya
        for _ in range(25):
            await asyncio.sleep(0.2)
            if live := await _live_tx(db, order["code"]):
                return _public_tx(live)
        raise PaymentError("Pembayaran sedang disiapkan — coba lagi sebentar")
    try:
        return await _create_attempt(db, order, minutes)
    finally:
        await db.pay_locks.delete_one({"order_code": order["code"]})


async def _live_tx(db, code):
    return await db.payment_transactions.find_one(
        {"order_code": code, "status": PENDING, "expires_at": {"$gt": now_iso()}})


async def _create_attempt(db, order, minutes):
    if live := await _live_tx(db, order["code"]):
        return _public_tx(live)
    attempt = await db.payment_transactions.count_documents({"order_code": order["code"]}) + 1
    gid = f"{order['code']}-{attempt}"
    items = _items(order)
    assert sum(i["price"] * i["quantity"] for i in items) == int(order["total"]), "item_details != total"
    addr = order.get("address") or {}
    payload = {"transaction_details": {"order_id": gid, "gross_amount": int(order["total"])},
               "item_details": items, "credit_card": {"secure": True},
               "customer_details": {"first_name": addr.get("name", "")[:50], "email": order.get("email"),
                                    "phone": addr.get("phone", "")},
               "expiry": {"unit": "minutes", "duration": minutes}}
    try:
        res = await mt.create_snap(payload)
    except mt.GatewayError as e:
        raise PaymentError(str(e)) from e
    tx = {"id": new_id("ptx"), "order_code": order["code"], "provider": "midtrans", "mode": mt.mode(),
          "gateway_order_id": gid, "snap_token": res["token"], "redirect_url": res.get("redirect_url"),
          "gross_amount": int(order["total"]), "status": PENDING, "payment_type": None,
          "expires_at": order["payment_deadline"], "created_at": now_iso(), "updated_at": now_iso()}
    await db.payment_transactions.insert_one(tx)
    return _public_tx(tx)


def _public_tx(tx):
    return {"token": tx["snap_token"], "redirect_url": tx.get("redirect_url"),
            "gateway_order_id": tx["gateway_order_id"], "mode": tx.get("mode")}


def _state(n):
    ts = str(n.get("transaction_status", "")).lower()
    fraud = str(n.get("fraud_status", "") or "").lower()
    if ts in PAID:
        return "paid" if fraud in ("", "accept") else "failed"
    return {"pending": "pending", "expire": "expired", "deny": "failed", "cancel": "failed",
            "failure": "failed", "refund": "refund", "partial_refund": "partial_refund"}.get(ts, "unknown")


async def apply_notification(db, n):
    """Terapkan status (sudah terverifikasi) ke transaksi & order. Return state."""
    tx = await db.payment_transactions.find_one({"gateway_order_id": n.get("order_id")})
    if not tx:
        return "unknown_tx"
    try:
        amount = int(float(n.get("gross_amount", 0)))
    except (TypeError, ValueError):
        amount = -1
    if amount != tx["gross_amount"]:
        return "amount_mismatch"
    state = _state(n)
    info = {"payment_type": n.get("payment_type"), "fraud_status": n.get("fraud_status"),
            "va_numbers": n.get("va_numbers"), "last_notification": n, "updated_at": now_iso()}
    if state == "paid":
        if tx["status"] in (PENDING, "expired", "failed", "unknown", None):
            await db.payment_transactions.update_one({"id": tx["id"], "status": tx["status"]},
                                                     {"$set": {"status": "paid", **info}})
        await apply_paid(db, await db.payment_transactions.find_one({"id": tx["id"]}))
        return state
    if state in ("refund", "partial_refund"):
        await refunds_svc.record_gateway_refunds(db, tx, n)
    if tx["status"] in ("paid", "refund", "partial_refund"):
        await db.payment_transactions.update_one({"id": tx["id"]}, {"$set": {"last_notification": n}})
        if not tx.get("payment_applied"):
            await apply_paid(db, tx)  # uang pernah masuk tapi belum tercatat → pulihkan
        return state  # status hanya maju; tak turun dari paid
    await db.payment_transactions.update_one({"id": tx["id"]}, {"$set": {"status": state, **info}})
    if state == "expired":
        order = await db.orders.find_one({"code": tx["order_code"]})
        others = await db.payment_transactions.count_documents(
            {"order_code": tx["order_code"], "status": PENDING, "id": {"$ne": tx["id"]}})
        if order and order["status"] == "pending" and order.get("payment_status") == "belum_bayar" and not others:
            try:
                await orders_svc.transition_order(db, order, "cancelled", reason="expired")
            except orders_svc.InvalidTransition:
                pass
    return state


async def apply_paid(db, tx):
    """Catat uang tx `paid` ke order tepat sekali (penanda = id tx). Aman diulang."""
    if tx.get("payment_applied"):
        return
    order = await db.orders.find_one({"code": tx["order_code"]})
    try:
        await orders_svc.record_payment(db, order, tx["gross_amount"], source="midtrans", ref=tx["id"])
        flags = {"payment_applied": True}
    except (orders_svc.OrderError, orders_svc.InvalidTransition):
        # dibayar setelah batal/kedaluwarsa → dana yatim, admin wajib refund
        flags = {"payment_applied": True, "needs_refund": True, "orphan": True}
    await db.payment_transactions.update_one({"id": tx["id"]}, {"$set": flags})


async def reconcile(db):
    """Cron: transaksi `paid` yang uangnya belum tercatat + refund tertunda."""
    fixed = []
    for tx in await db.payment_transactions.find(
            {"status": {"$in": SETTLED}, "payment_applied": {"$ne": True}}).to_list(200):
        await apply_paid(db, tx)
        fixed.append(tx["gateway_order_id"])
    return {"applied": fixed, "refunds": await refunds_svc.retry_pending(db)}


async def handle_webhook(db, n):
    """Webhook Midtrans. Signature wajib; mode live → status diambil ulang dari API (defense in depth)."""
    if not mt.enabled() or not mt.verify_signature(n):
        return None
    fresh = await mt.get_status(n.get("order_id"))
    return await apply_notification(db, fresh or n)


async def sync_status(db, order_code):
    """Tarik status transaksi pending dari Midtrans (live) — dipakai polling FE & sweeper."""
    for tx in await db.payment_transactions.find({"order_code": order_code, "status": PENDING}).to_list(20):
        try:
            fresh = await mt.get_status(tx["gateway_order_id"])
        except mt.GatewayError:
            continue
        if fresh and str(fresh.get("status_code")) != "404":
            await apply_notification(db, fresh)


async def sync_pending(db, min_age_minutes=2):
    """Cron cadangan: webhook terlewat → tarik status transaksi pending yang masih berlaku."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)).isoformat()
    codes = await db.payment_transactions.distinct(
        "order_code", {"status": PENDING, "created_at": {"$lt": cutoff}, "expires_at": {"$gt": now_iso()}})
    for code in codes[:200]:
        await sync_status(db, code)
    return {"checked": codes[:200], "mode": mt.mode()}


async def mock_complete(db, order_code, outcome):
    """SIMULASI (mode mock saja): kirim notifikasi bertanda-tangan seolah dari Midtrans."""
    tx = await db.payment_transactions.find_one({"order_code": order_code, "status": PENDING},
                                                sort=[("created_at", -1)])
    if mt.mode() != "mock" or not tx:
        raise PaymentError("Simulasi tidak tersedia")
    gross = f"{tx['gross_amount']}.00"
    code = {"settlement": "200", "pending": "201"}.get(outcome, "407")
    n = {"order_id": tx["gateway_order_id"], "status_code": code, "gross_amount": gross,
         "transaction_status": outcome, "payment_type": "mock", "fraud_status": "accept"}
    n["signature_key"] = mt.signature(n["order_id"], code, gross)
    return await handle_webhook(db, n)


async def refund_order(db, admin_id, order, amount, reason):
    try:
        return await refunds_svc.refund_order(db, admin_id, order, amount, reason, orders_svc.transition_order)
    except refunds_svc.RefundError as e:
        raise PaymentError(str(e)) from e


async def sync_payment_methods(db):
    """Aktifkan 'Bayar Online' bila gateway aktif; transfer/e-wallet manual mati (keputusan owner)."""
    on = mt.enabled()
    await db.payment_methods.update_one({"id": "midtrans"}, {"$set": {
        "group": "online", "name": "Bayar Online", "extra": "VA · QRIS · E-Wallet · Kartu",
        "fee": 0, "active": on}}, upsert=True)
    await db.payment_methods.update_many({"group": {"$in": ["transfer", "ewallet"]}}, {"$set": {"active": not on}})
