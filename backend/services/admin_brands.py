"""services/admin_brands.py — profil brand (logo, foto, deskripsi, urutan, sembunyikan).

Brand TIDAK punya master sendiri: sumbernya field `brand` produk. Profil disimpan di koleksi
`brands` dengan kunci `name` persis sama; brand tanpa profil tetap tampil (logo/foto kosong).
"""
from core_utils import now_iso, safe_doc
from services.audit import log_action

LIST_MAX = 2000


async def profiles(db):
    return {d["name"]: d async for d in db.brands.find({}, {"_id": 0})}


async def list_admin(db):
    counts = {r["_id"]: r for r in await db.products.aggregate([
        {"$match": {"brand": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$brand", "count": {"$sum": 1},
                    "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}}}},
    ]).to_list(LIST_MAX)}
    prof = await profiles(db)
    rows = []
    for name in sorted(set(counts) | set(prof), key=str.lower):
        p = prof.get(name, {})
        rows.append({"name": name, "count": counts.get(name, {}).get("count", 0),
                     "active_count": counts.get(name, {}).get("active", 0),
                     "logo": p.get("logo", ""), "image": p.get("image", ""), "desc": p.get("desc", ""),
                     "order": p.get("order", 0), "hidden": bool(p.get("hidden")), "has_profile": bool(p)})
    return rows


async def upsert(db, actor_id, data):
    name = str(data["name"]).strip()
    doc = {k: data.get(k) for k in ("logo", "image", "desc", "order", "hidden")}
    doc.update({"name": name, "updated_at": now_iso()})
    await db.brands.update_one({"name": name}, {"$set": doc}, upsert=True)
    await log_action(actor_id, "upsert", "brands", name)
    return safe_doc(await db.brands.find_one({"name": name}))


async def remove(db, actor_id, name):
    res = await db.brands.delete_one({"name": name})
    await log_action(actor_id, "delete", "brands", name)
    return res.deleted_count == 1
