"""services/orders.py — SSOT ORDER LIFECYCLE (Epic E3). Pembuatan order: services/order_create.py.

  - transition_order(): SATU-SATUNYA mutator status; `LEGAL_TRANSITIONS` = SSOT (docs/06).
    cancel → kompensasi idempoten (services/order_holds.release_order); completed → commit penanda.
    Order yang sudah menerima uang (paid − refunded > 0) TIDAK bisa dibatalkan tanpa refund (butir 3).
  - record_payment(): `$inc paid_amount` ber-guard + penanda `ref` (bukti/transaksi) → idempoten (butir 12).
  - derive_payment_status(): INV-5 (belum_bayar/dp/lunas) — status TAK memaksa lunas (RC-E4).
"""
import secrets

from core_utils import money, now_iso, safe_doc
from services import notify
from services.order_create import create_order, find_idempotent, sweep_stale_reserving  # noqa: F401 (re-export)
from services.order_helpers import (  # re-export: API publik modul ini TIDAK berubah
    IdempotencyConflict,  # noqa: F401 (re-export)
    InvalidTransition,
    OrderError,
    StockConflict,
    _track_purchase,
    derive_payment_status,
)
from services.order_holds import commit_holds, release_order

LEGAL_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"packed", "cancelled"},
    "packed": {"shipped", "cancelled"},
    "shipped": {"completed"},
    "completed": set(),
    "cancelled": set(),
}
TERMINAL = {"completed", "cancelled"}


async def transition_order(db, order, to_status, reason=None, extra=None):
    """SATU-SATUNYA mutator status. Menegakkan LEGAL_TRANSITIONS + efek samping.

    - Transisi di luar whitelist → InvalidTransition (RC-E7/E8).
    - Update ber-guard `status == frm` (compare-and-set) → anti double-restore stok (BUG-SALES-02).
    - pending→paid non-COD wajib lunas (paid hanya dari pembayaran, BUG-SALES-03).
    - payment_status SELALU diturunkan dari paid_amount (INV-5) — tak dipaksa lunas (RC-E4).
    """
    frm = order.get("status")
    if to_status not in LEGAL_TRANSITIONS.get(frm, set()):
        raise InvalidTransition(f"Transisi ilegal: {frm} -> {to_status}")

    paid = money(order.get("paid_amount", 0))
    total = money(order.get("total", 0))
    is_cod = (order.get("payment") or {}).get("group") == "cod"
    if to_status == "paid" and not is_cod and derive_payment_status(paid, total) != "lunas":
        raise InvalidTransition("Pesanan belum lunas — status Dibayar hanya dari pembayaran terverifikasi")
    held = paid - money(order.get("refunded_amount", 0))
    if to_status == "cancelled" and held > 0:
        raise InvalidTransition(f"Pesanan sudah menerima pembayaran Rp{held:,} — lakukan refund dulu sebelum membatalkan"
                                .replace(",", "."))

    updates = {"status": to_status, "updated_at": now_iso()}
    if to_status == "cancelled":
        updates["cancel_reason"] = reason or "manual"
    # COD: uang tunai DITERIMA saat barang sampai (completed) → lunasi (INV-5 tetap DERIVASI).
    if to_status == "completed" and is_cod and paid < total:
        updates["paid_amount"] = total
    updates.update(extra or {})  # mis. shipped + shipment (resi) dalam SATU update atomik
    res = await db.orders.update_one({"code": order["code"], "status": frm}, {"$set": updates})
    if res.modified_count != 1:
        raise InvalidTransition("Status pesanan sudah berubah — muat ulang halaman")

    if to_status == "cancelled":
        await release_order(db, order)  # stok & kuota voucher kembali (idempoten, SALES-07)
    if to_status == "completed":
        await commit_holds(db, order)
    if to_status == "paid":
        await _track_purchase(db, order)
        notify.paid_async(db, order["code"])  # email konfirmasi lunas (E15), sekali per order

    fresh = await db.orders.find_one({"code": order["code"]})
    ps = derive_payment_status(fresh.get("paid_amount", 0), fresh.get("total", 0))
    await db.orders.update_one({"code": order["code"]}, {"$set": {"payment_status": ps}})
    fresh["payment_status"] = ps
    order.update({k: fresh.get(k) for k in ("status", "paid_amount", "payment_status", "updated_at")})
    return safe_doc(fresh)


async def record_payment(db, order, amount, source="transfer", ref=None):
    """Catat pembayaran (SSOT uang). `$inc paid_amount` ATOMIK ber-guard: order non-terminal
    DAN paid_amount + amount <= total (anti overpay, BUG-SALES-04). payment_status diturunkan
    (INV-5). Bila lunas & masih `pending` → maju ke `paid` LEWAT transition_order.

    - Terminal (cancelled/completed) → InvalidTransition (INV-P2 / RC-E8).
    - amount <= 0 atau melebihi sisa tagihan → OrderError.
    - `ref` (id bukti/transaksi): penanda `applied_payments` di update yang sama → pemanggilan ulang
      (retry/rekonsiliasi) tak pernah menambah dua kali; langkah lanjutan tetap dijalankan.
    """
    if order.get("status") in TERMINAL:
        raise InvalidTransition("Tak bisa mencatat pembayaran pada order terminal")
    amt = money(amount)
    if amt <= 0:
        raise OrderError("Jumlah pembayaran harus > 0")
    flt = {"code": order["code"], "status": {"$nin": list(TERMINAL)},
           "$expr": {"$lte": [{"$add": [{"$ifNull": ["$paid_amount", 0]}, amt]}, "$total"]}}
    upd = {"$inc": {"paid_amount": amt}, "$set": {"updated_at": now_iso()}}
    if ref:
        flt["applied_payments"] = {"$ne": ref}
        upd["$push"] = {"applied_payments": ref}
    res = await db.orders.update_one(flt, upd)
    already = ref and not res.modified_count and await db.orders.count_documents(
        {"code": order["code"], "applied_payments": ref})
    if res.modified_count != 1 and not already:
        cur = await db.orders.find_one({"code": order["code"]}) or {}
        if cur.get("status") in TERMINAL:
            raise InvalidTransition("Tak bisa mencatat pembayaran pada order terminal")
        raise OrderError("Jumlah pembayaran melebihi sisa tagihan")
    fresh = await db.orders.find_one({"code": order["code"]})
    ps = derive_payment_status(fresh.get("paid_amount", 0), fresh.get("total", 0))
    if fresh.get("status") == "pending" and ps == "lunas":
        try:
            return await transition_order(db, fresh, "paid")
        except InvalidTransition:
            fresh = await db.orders.find_one({"code": order["code"]})  # sudah dimajukan paralel
    await db.orders.update_one({"code": order["code"]}, {"$set": {"payment_status": ps}})
    fresh["payment_status"] = ps
    return safe_doc(fresh)


async def list_orders_for_user(db, user_id, limit=20, skip=0):
    """Riwayat pelanggan berhalaman (butir 5). Return (items, total)."""
    flt = {"user_id": user_id, "status": {"$ne": "reserving"}}
    total = await db.orders.count_documents(flt)
    docs = await db.orders.find(flt).sort([("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return [safe_doc(d) for d in docs], total


async def get_order_for_user(db, code, user, token=None):
    """Ambil order (IDOR-safe, RC-E10). Order ber-user → hanya pemilik. Order tamu → WAJIB
    `access_token` yang cocok (kode order berurutan & bisa ditebak, BUG-SALES-01)."""
    doc = await db.orders.find_one({"code": code})
    if not doc:
        return None
    if doc.get("user_id"):
        if doc["user_id"] != (user or {}).get("id"):
            return None  # bukan pemilik → 404 (jangan bocorkan keberadaan)
    elif not (token and doc.get("access_token") and secrets.compare_digest(str(token), doc["access_token"])):
        return None
    return safe_doc(doc)


__all__ = [
    "create_order", "transition_order", "record_payment",
    "list_orders_for_user", "get_order_for_user",
    "derive_payment_status", "LEGAL_TRANSITIONS", "TERMINAL",
    "OrderError", "StockConflict", "InvalidTransition",
]
