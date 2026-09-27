"""services/startup.py — inisialisasi saat boot, TIAP langkah terisolasi (butir 12).

Satu indeks bentrok tak lagi melewati sisa inisialisasi diam-diam: setiap langkah dijalankan
sendiri, kegagalan dicatat di `STATE["errors"]` dan dilaporkan `GET /api/health` (ready=false).
"""
import logging

from pymongo import ASCENDING

logger = logging.getLogger("collector_parfum")
STATE = {"ready": False, "errors": []}
_U = {"unique": True}

INDEXES = [
    ("users", "email", _U), ("users", "id", _U), ("sessions", "token", _U), ("sessions", "user_id", {}),
    ("products", "slug", _U), ("products", "category", {}), ("products", "status", {}),
    ("products", "characters", {}), ("products", "stock_holds", {}),
    ("categories", "slug", _U), ("occasions", "slug", _U), ("characters", "slug", _U),
    ("vouchers", "code", _U), ("voucher_redemptions", "voucher_code", {}),
    ("voucher_redemptions", [("voucher_code", 1), ("user_id", 1)], {}), ("voucher_redemptions", "order_code", {}),
    ("voucher_user_usage", [("voucher_code", 1), ("user_id", 1)], _U),
    ("orders", "code", _U), ("orders", "user_id", {}), ("orders", "status", {}), ("orders", "payment_deadline", {}),
    ("orders", "created_at", {}),
    ("orders", "idempotency_key", {"unique": True, "partialFilterExpression": {"idempotency_key": {"$type": "string"}}}),
    ("cron_runs", "run_id", _U),
    ("payment_transactions", "gateway_order_id", _U), ("payment_transactions", "order_code", {}),
    ("pay_locks", "order_code", _U), ("pay_locks", "expires_at", {"expireAfterSeconds": 0}),
    ("email_logs", [("created_at", -1)], {}), ("email_logs", "order_code", {}),
    ("refunds", "order_code", {}), ("refunds", "id", _U),
    ("addresses", "user_id", {}),
    ("wishlists", "user_id", _U), ("carts", "user_id", _U), ("counters", "name", _U),
    ("media_assets", "id", _U), ("audit_logs", "created_at", {}), ("audit_logs", "entity", {}),
    ("payment_proofs", "id", _U), ("payment_proofs", "order_code", {}), ("payment_proofs", "status", {}),
    ("analytics_events", "id", _U), ("analytics_events", "type", {}), ("analytics_events", "created_at", {}),
    ("content", "id", _U), ("store_locations", "id", _U), ("store_locations", "order", {}),
    ("store_reviews", "id", _U), ("backups", "id", _U), ("backups", "created_at", {}), ("brands", "name", _U),
] + [("products", [("status", 1), (f, 1)], {}) for f in ("tier", "date_night", "variants.options.Tipe", "characters", "category")]


async def _step(name, coro):
    try:
        await coro
    except Exception as e:  # dicatat & dilaporkan, langkah lain tetap jalan
        logger.warning(f"startup step gagal: {name}: {e}")
        STATE["errors"].append(f"{name}: {str(e)[:200]}")


async def run(db, extra_steps):
    STATE["errors"] = []
    for coll, keys, opts in INDEXES:
        spec = [(keys, ASCENDING)] if isinstance(keys, str) else keys
        await _step(f"index {coll}.{keys}", db[coll].create_index(spec, **opts))
    for name, factory in extra_steps:
        await _step(name, factory())
    STATE["ready"] = not STATE["errors"]
    logger.info(f"Startup selesai: ready={STATE['ready']} errors={len(STATE['errors'])}")
