"""services/admin_stats.py — agregat dashboard admin (READ-only, Epic E5 BR-1).

Hanya membaca & meringkas (revenue, orders-by-status, produk aktif, low-stock, pesanan terbaru).
Semua agregasi dilakukan di MongoDB (pipeline) — tidak memuat seluruh order/produk ke memori (SALES-20).
"""
from core_utils import safe_doc

LOW_STOCK_DEFAULT = 5
RECENT_MAX = 8
LOW_STOCK_MAX = 24
REVENUE_STATES = ["paid", "packed", "shipped", "completed"]


def _i(field):
    return {"$toLong": {"$ifNull": [field, 0]}}


async def _order_totals(db):
    rows = await db.orders.aggregate([{"$group": {
        "_id": {"$ifNull": ["$status", "pending"]},
        "count": {"$sum": 1},
        "total": {"$sum": _i("$total")},
        "net_paid": {"$sum": {"$subtract": [_i("$paid_amount"), _i("$refunded_amount")]}},
    }}]).to_list(20)
    by_status = {r["_id"]: r["count"] for r in rows}
    revenue = sum(r["total"] for r in rows if r["_id"] in REVENUE_STATES)
    paid_revenue = sum(r["net_paid"] for r in rows)  # uang bersih = dibayar − direfund (SALES-15/16)
    return by_status, int(revenue), int(paid_revenue)


async def _low_stock(db, threshold):
    """Varian aktif dengan stok <= ambang. Fallback `volumes` untuk dokumen legacy."""
    rows = await db.products.aggregate([
        {"$match": {"status": "active"}},
        {"$project": {"_id": 0, "name": 1, "slug": 1,
                      "rows": {"$ifNull": ["$variants", {"$ifNull": ["$volumes", []]}]}}},
        {"$unwind": "$rows"},
        {"$addFields": {"stock": _i("$rows.stock")}},
        {"$match": {"stock": {"$lte": threshold}}},
        {"$sort": {"stock": 1}},
        {"$limit": LOW_STOCK_MAX},
    ]).to_list(LOW_STOCK_MAX)
    out = []
    for r in rows:
        v = r["rows"]
        opts = v.get("options") or {}
        label = " / ".join(str(x) for x in opts.values()) if opts else (
            f"{v.get('ml')}ml" if v.get("ml") else v.get("sku", ""))
        out.append({"slug": r.get("slug"), "name": r.get("name"), "ml": label,
                    "sku": v.get("sku"), "stock": int(r["stock"])})
    return out


async def dashboard(db):
    """Ringkasan operasional toko. Revenue = Σ total order berstatus terbayar/diproses."""
    orders_by_status, revenue, paid_revenue = await _order_totals(db)
    settings = await db.settings.find_one({"id": "store"}) or {}
    threshold = int(settings.get("low_stock_threshold", LOW_STOCK_DEFAULT) or LOW_STOCK_DEFAULT)
    recent = await db.orders.find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(RECENT_MAX)
    return {
        "revenue": revenue,
        "paid_revenue": paid_revenue,
        "total_orders": sum(orders_by_status.values()),
        "orders_by_status": orders_by_status,
        "active_products": await db.products.count_documents({"status": "active"}),
        "archived_products": await db.products.count_documents({"status": "archived"}),
        "low_stock_threshold": threshold,
        "low_stock": await _low_stock(db, threshold),
        "pending_reviews": await db.reviews.count_documents({"status": "pending"}),
        "recent": [safe_doc(o) for o in recent],
    }
