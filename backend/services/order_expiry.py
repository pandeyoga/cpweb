"""services/order_expiry.py — batalkan otomatis order `pending` yang lewat batas bayar (SALES-06).

Dipanggil cron (POST /api/cron/expire-orders). Pembatalan LEWAT transition_order (SSOT) →
stok & kuota voucher kembali, compare-and-set mencegah dobel. Order yang punya bukti bayar
`pending` (menunggu verifikasi admin) atau sudah DP TIDAK disentuh.
Fase Midtrans: cek status transaksi gateway dulu sebelum membatalkan.
"""
from core_utils import now_iso
from services import gateway as gateway_svc
from services import orders as orders_svc
from services.audit import log_action

BATCH_MAX = 500


MAX_BATCHES = 20


async def expire_overdue_orders(db, now=None):
    """Batch berurutan per `payment_deadline`; order ber-bukti pending DIKECUALIKAN di query
    (butir 13) sehingga 500 order tertahan tak menghalangi batch berikutnya."""
    cutoff = now or now_iso()
    held = await db.payment_proofs.distinct("order_code", {"status": {"$in": ["pending", "processing"]}})
    skipped = await db.orders.distinct("code", {"code": {"$in": held}, "status": "pending",
                                                "payment_deadline": {"$lt": cutoff}})
    expired, seen = [], set()
    for _ in range(MAX_BATCHES):
        docs = await db.orders.find({
            "status": "pending", "payment_status": "belum_bayar",
            "payment_deadline": {"$lt": cutoff}, "code": {"$nin": held + list(seen)},
        }).sort("payment_deadline", 1).to_list(BATCH_MAX)
        if not docs:
            break
        for o in docs:
            seen.add(o["code"])
            await _expire_one(db, o, expired)
    if expired:
        await log_action("system", "expire", "orders", ",".join(expired)[:500], {"count": len(expired)})
    return {"expired": expired, "skipped": skipped}


async def _expire_one(db, o, expired):
    if await db.payment_transactions.count_documents({"order_code": o["code"], "status": "pending"}):
        await gateway_svc.sync_status(db, o["code"])  # webhook terlewat? cek Midtrans dulu
        o = await db.orders.find_one({"code": o["code"]})
        if o["status"] != "pending" or o.get("payment_status") != "belum_bayar":
            return
    try:
        await orders_svc.transition_order(db, o, "cancelled", reason="expired")
        expired.append(o["code"])
    except orders_svc.InvalidTransition:
        return  # sudah dibayar/dibatalkan paralel
