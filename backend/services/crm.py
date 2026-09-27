"""services/crm.py — segmentasi CRM ringan diturunkan dari orders (Epic E7).

SATU sumber kebenaran: orders (INV-G2 — tak ada store segmen terpisah yang bisa drift).
Segmen: prospek (0 order), new (1), repeat (>=2), high_value (LTV>=ambang), dormant
(order terakhir > DORMANT_DAYS lalu). READ-only; grouping per user dilakukan pipeline Mongo (SALES-20).
LTV = uang bersih (paid_amount − refunded_amount) — definisi sama dengan dashboard (SALES-15).
"""
from datetime import datetime, timezone

USERS_MAX = 50000
HIGH_VALUE_LTV = 1500000     # Rp — ambang pelanggan bernilai tinggi
DORMANT_DAYS = 90
ROWS_MAX = 1000


def _parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _segment(order_count, ltv, last_dt, now):
    if order_count == 0:
        return "prospek"
    if last_dt and (now - last_dt).days > DORMANT_DAYS:
        return "dormant"
    if ltv >= HIGH_VALUE_LTV:
        return "high_value"
    if order_count >= 2:
        return "repeat"
    return "new"


async def _per_user(db):
    rows = await db.orders.aggregate([  # hanya order yang pernah menerima uang (bukan batal tanpa bayar)
        {"$match": {"user_id": {"$nin": [None, ""]}, "paid_amount": {"$gt": 0}}},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "ltv": {"$sum": {"$subtract": [{"$toLong": {"$ifNull": ["$paid_amount", 0]}},
                                           {"$toLong": {"$ifNull": ["$refunded_amount", 0]}}]}},
            "last": {"$max": "$created_at"},
        }},
    ]).to_list(USERS_MAX)
    return {r["_id"]: r for r in rows}


async def segments(db, seg_type="", skip=0, limit=ROWS_MAX, all_rows=False):
    users = await db.users.find(
        {"role": "customer"}, {"_id": 0, "id": 1, "name": 1, "email": 1, "created_at": 1}
    ).to_list(USERS_MAX)
    agg = await _per_user(db)
    now = datetime.now(timezone.utc)
    rows = []
    counts = {}
    for u in users:
        a = agg.get(u["id"]) or {}
        count, ltv, last = int(a.get("count", 0)), max(0, int(a.get("ltv", 0))), _parse_dt(a.get("last"))
        seg = _segment(count, ltv, last, now)
        counts[seg] = counts.get(seg, 0) + 1
        rows.append({
            "user_id": u["id"], "name": u.get("name"), "email": u.get("email"),
            "orders": count, "ltv": ltv,
            "last_order": last.isoformat() if last else None,
            "segment": seg,
        })
    if seg_type:
        rows = [r for r in rows if r["segment"] == seg_type]
    rows.sort(key=lambda r: r["ltv"], reverse=True)
    return {
        "segments": counts,
        "total": len(rows),
        "rows": rows if all_rows else rows[skip:skip + min(limit, ROWS_MAX)],
        "thresholds": {"high_value_ltv": HIGH_VALUE_LTV, "dormant_days": DORMANT_DAYS},
    }


def to_csv(rows):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "nama", "email", "jumlah_order", "ltv_bersih", "order_terakhir", "segmen"])
    for r in rows:
        w.writerow([r["user_id"], r.get("name") or "", r.get("email") or "", r["orders"], r["ltv"],
                    r.get("last_order") or "", r["segment"]])
    return buf.getvalue()
