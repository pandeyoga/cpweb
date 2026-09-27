"""services/order_create.py — pembuatan order (SSOT) dengan urutan tahan-crash (butir 4/11/13).

Urutan: validasi & hitung (server) → INSERT order `reserving` (unik: code + Idempotency-Key)
→ reservasi stok ber-penanda → klaim voucher ber-penanda → CAS `reserving → pending`.
Gagal di langkah mana pun → abort_reservation (idempoten). Proses mati di tengah → job
rekonsiliasi melepas draf `reserving` yang basi. Tak pernah ada order aktif tanpa reservasi.
"""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from core_utils import money, new_id, next_sequence, now_iso, safe_doc
from services import stock
from services.order_helpers import (
    IdempotencyConflict,
    OrderError,
    StockConflict,
    _build_snapshot,
    _clean_address,
    order_fingerprint,
)
from services.order_holds import HOLD_V, abort_reservation, claim_voucher
from services.pricing import compute_subtotal, effective_shipping
from services.vouchers import evaluate_voucher

STALE_RESERVING_MIN = 2


def _payment_deadline():
    hours = int(os.environ["PAYMENT_DEADLINE_HOURS"])
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def find_idempotent(db, key, uid, fp):
    """Order lama untuk key (replay) atau None. Beda pemilik → OrderError; beda isi → 409.
    Draf `reserving` (request paralel masih berjalan) ditunggu sebentar."""
    for _ in range(15):
        prev = await db.orders.find_one({"idempotency_key": key})
        if not prev:
            return None
        if prev.get("user_id") != uid:
            raise OrderError("Idempotency-Key sudah dipakai")
        if prev.get("idempotency_fp") and prev["idempotency_fp"] != fp:
            raise IdempotencyConflict("Isi pesanan berubah sejak percobaan sebelumnya. Silakan buat pesanan lagi.")
        if prev.get("status") != "reserving":
            return safe_doc(prev)
        await asyncio.sleep(0.2)
    raise OrderError("Pesanan sebelumnya masih diproses — coba lagi sebentar")


async def _price(db, user, items_in, shipping_id, payment, voucher_code):
    ship = await db.shipping_methods.find_one({"id": shipping_id, "active": True})
    if not ship:
        raise OrderError("Metode pengiriman tidak valid")
    grp, method_id = (payment or {}).get("group"), (payment or {}).get("method_id")
    if grp == "cod":
        raise OrderError("COD tidak tersedia — silakan bayar online")
    pay = await db.payment_methods.find_one({"id": method_id, "group": grp, "active": True})
    if not pay:
        raise OrderError("Metode pembayaran tidak valid")
    items = await _build_snapshot(db, items_in)
    subtotal = compute_subtotal(items)
    store = await db.settings.find_one({"id": "store"}, {"free_shipping_threshold": 1}) or {}
    shipping_price = effective_shipping(ship.get("price", 0), subtotal, store.get("free_shipping_threshold"))
    discount, v_code = 0, None
    if voucher_code:
        ev = await evaluate_voucher(db, code=voucher_code, subtotal=subtotal, shipping=shipping_price,
                                    user_id=(user or {}).get("id"), items=items)
        if not ev.get("valid"):
            raise OrderError(ev.get("reason") or "Voucher tidak berlaku")
        discount, v_code = money(ev.get("discount", 0)), ev.get("code")
    total = max(0, subtotal - discount + shipping_price)
    if total <= 0:  # butir 10: larang total Rp0 (tak ada jalur lunas tanpa gateway)
        raise OrderError("Total pesanan tidak boleh Rp0. Voucher tidak dapat menggratiskan seluruh pesanan.")
    return {"items": items, "subtotal": subtotal, "discount": discount, "voucher_code": v_code,
            "shipping": {"method_id": ship["id"], "name": ship.get("name", ""), "price": shipping_price,
                         "eta": ship.get("eta", "")},
            "payment": {"group": grp, "method_id": method_id, "name": pay.get("name", "")},
            "cod_fee": 0, "total": total}


async def create_order(db, *, user, items_in, address, shipping_id, payment, voucher_code=None,
                       note="", email=None, idempotency_key=None):
    if not items_in:
        raise OrderError("Keranjang kosong")
    uid = (user or {}).get("id")
    fp = order_fingerprint(uid, items_in, address, shipping_id, payment, voucher_code, note, email)
    if idempotency_key and (prev := await find_idempotent(db, idempotency_key, uid, fp)):
        return prev
    buyer_email = str(email or (user or {}).get("email") or "").strip().lower()
    if not buyer_email:
        raise OrderError("Email wajib diisi untuk menerima status pesanan")
    priced = await _price(db, user, items_in, shipping_id, payment, voucher_code)
    order = {"id": new_id("ord"), "code": await next_sequence(db, "orders", "CP", 8), "user_id": uid,
             "access_token": secrets.token_urlsafe(24), "email": buyer_email[:200], **priced,
             "paid_amount": 0, "address": _clean_address(address), "note": (note or "")[:500],
             "status": "reserving", "payment_status": "belum_bayar", "payment_deadline": _payment_deadline(),
             "hold_v": HOLD_V, "created_at": now_iso(), "updated_at": now_iso()}
    if idempotency_key:
        order.update(idempotency_key=idempotency_key, idempotency_fp=fp)
    try:
        await db.orders.insert_one(order)
    except DuplicateKeyError:
        if idempotency_key and (prev := await find_idempotent(db, idempotency_key, uid, fp)):
            return prev  # request paralel dgn key & isi sama sudah menang
        raise
    try:
        ok, failed = await stock.reserve(db, order["code"], order["items"])
        if not ok:
            raise StockConflict(failed, available=await stock.available_stock(db, failed.get("product_id"), failed.get("sku")))
        await claim_voucher(db, order)
        res = await db.orders.update_one({"code": order["code"], "status": "reserving"},
                                         {"$set": {"status": "pending", "updated_at": now_iso()}})
        if res.modified_count != 1:
            raise OrderError("Pesanan gagal diproses — silakan coba lagi")
    except BaseException:
        await abort_reservation(db, order)
        raise
    order["status"] = "pending"
    order.pop("_id", None)
    return safe_doc(order)


async def sweep_stale_reserving(db):
    """Rekonsiliasi: draf `reserving` basi (proses mati di tengah) → lepas efek & hapus."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_RESERVING_MIN)).isoformat()
    aborted = []
    for o in await db.orders.find({"status": "reserving", "created_at": {"$lt": cutoff}}).to_list(500):
        await abort_reservation(db, o)
        aborted.append(o["code"])
    return aborted
