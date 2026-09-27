"""services/reconcile.py — job rekonsiliasi (cron tiap 10 menit): melanjutkan pekerjaan yang terputus.

Semua langkah idempoten (penanda/flag), jadi aman dijalankan berulang/paralel:
  - draf order `reserving` basi → lepas stok/voucher & hapus;
  - order `cancelled` yang kompensasinya belum `released` → lepas stok/voucher;
  - order `completed` yang penandanya belum di-commit → commit;
  - bukti bayar `processing` basi → selesaikan;
  - transaksi Midtrans `paid` yang uangnya belum tercatat + refund tertunda;
  - email transaksional yang gagal → kirim ulang (penanda dilepas saat gagal).
"""
from services import gateway as gateway_svc
from services import notify
from services import payments as payments_svc
from services.order_create import sweep_stale_reserving
from services.order_holds import commit_holds, release_order


async def migrate_flags(db):
    """Sekali saat boot: data sebelum ledger idempoten dianggap sudah selesai diproses."""
    await db.orders.update_many({"status": "cancelled", "released": {"$exists": False}, "hold_v": {"$ne": 2}},
                                {"$set": {"released": True}})
    await db.payment_transactions.update_many(
        {"status": {"$in": ["paid", "refund", "partial_refund"]}, "payment_applied": {"$exists": False}},
        {"$set": {"payment_applied": True}})


async def run(db):
    released, committed = [], []
    for o in await db.orders.find({"status": "cancelled", "released": {"$ne": True}}).to_list(500):
        await release_order(db, o)
        released.append(o["code"])
    for o in await db.orders.find({"status": "completed", "hold_v": 2, "holds_committed": {"$ne": True}}).to_list(500):
        await commit_holds(db, o)
        committed.append(o["code"])
    gw = await gateway_svc.reconcile(db)
    return {
        "reserving_aborted": await sweep_stale_reserving(db),
        "cancel_released": released,
        "holds_committed": committed,
        "proofs_resumed": await payments_svc.resume_processing(db),
        "payments_applied": gw["applied"],
        "refunds_retried": gw["refunds"],
        "emails_retried": await notify.retry_failed(db),
    }
