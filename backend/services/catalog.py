"""services/catalog.py — logika read-path katalog (Epic E1).

Prinsip:
- Query TERBATAS (bounded .to_list(limit)) + clamp param → anti unbounded / adversarial 5xx.
- Filter/sort/paginate DILAKUKAN DI SERVER (bukan kirim seluruh katalog ke browser).
- `q` → services/search (toleran typo + singkatan) menghasilkan daftar id berperingkat relevansi.
- rating_avg/rating_count = nilai derivasi tersimpan (di-seed dari reviews) → tanpa N+1.
- safe_doc menutup _id + field sensitif; uang tetap integer rupiah.
"""

from core_utils import safe_doc
from services import variants as V

# Batas aman.
LIMIT_DEFAULT = 24
LIMIT_MAX = 100
REVIEWS_MAX = 500
CATEGORIES_MAX = 200

# Peta sort publik -> spesifikasi Mongo (whitelist; nilai tak dikenal -> 'featured').
SORT_SPECS = {
    "featured": [("best_seller", -1), ("is_new", -1), ("created_at", -1)],
    "newest": [("is_new", -1), ("created_at", -1)],
    "best": [("best_seller", -1), ("created_at", -1)],
    "low": [("price", 1), ("created_at", -1)],
    "high": [("price", -1), ("created_at", -1)],
    "rating": [("rating_avg", -1), ("rating_count", -1), ("created_at", -1)],  # Editor's Picks
}
BRANDS_MAX = 500
TIERS = ("CP01", "CP02", "CP03", "EXCLUSIVE")
TYPE_OPTION = "Tipe"   # dimensi varian Basic/Refine/Intense


def parse_int(value, default=0, lo=None, hi=None):
    """Konversi aman -> int lalu clamp. Nilai sampah -> default (tak pernah error)."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        n = default
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def _multi(value):
    """CSV -> list bersih (dukung filter multi-facet dari storefront)."""
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _truthy(value):
    """Interpretasi param boolean dari query string (1/true/yes)."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_product_filter(*, category=None, gender=None, tier=None, date_night=None,
                         tag=None, occasion=None, character=None, q=None, brand=None,
                         min_price=None, max_price=None, tipe=None,
                         best_seller=None, is_new=None, ids=None):
    """Susun filter Mongo untuk /api/products (hanya status=active).
    Tipe + harga dievaluasi PER VARIAN ($elemMatch) → harga yang cocok = harga tipe terpilih."""
    filt = {"status": "active"}
    cats, genders, tags = _multi(category), _multi(gender), _multi(tag)
    chars, tiers, tipes = _multi(character), [t for t in _multi(tier) if t in TIERS], _multi(tipe)
    id_list = _multi(ids)[:LIMIT_MAX]
    if id_list:  # wishlist/keranjang: ambil produk tepat berdasarkan id (tak bergantung cache 100 pertama)
        filt["id"] = {"$in": id_list}
    if cats:
        filt["category"] = {"$in": cats}
    brands = _multi(brand)[:50]
    if brands:
        filt["brand"] = {"$in": brands}
    if genders:
        filt["gender"] = {"$in": genders}
    if tiers:
        filt["tier"] = {"$in": tiers}
    if tags:
        filt["tags"] = {"$in": tags}
    if _truthy(date_night) or "date-night" in _multi(occasion):  # ?occasion=date-night = URL lama
        filt["date_night"] = True
    if chars:
        filt["characters"] = {"$in": chars}
    if _truthy(best_seller):
        filt["best_seller"] = True
    if _truthy(is_new):
        filt["is_new"] = True

    price_cond = {}
    if min_price is not None:
        price_cond["$gte"] = parse_int(min_price, 0, lo=0)
    if max_price is not None:
        mx = parse_int(max_price, 0, lo=0)
        if mx > 0:
            price_cond["$lte"] = mx
    if tipes:
        em = {f"options.{TYPE_OPTION}": {"$in": tipes}}
        if price_cond:
            em["price"] = price_cond
        filt["variants"] = {"$elemMatch": em}
    elif price_cond:
        filt["price"] = price_cond
    return filt


def resolve_sort(sort):
    return SORT_SPECS.get((sort or "featured").strip().lower(), SORT_SPECS["featured"])


def _type_price_expr(tipes, op):
    return {op: {"$map": {"input": {"$filter": {"input": "$variants", "as": "v", "cond": {
        "$in": [f"$$v.options.{TYPE_OPTION}", tipes]}}}, "as": "v", "in": "$$v.price"}}}


async def _ranked(db, filt, tipes, rank, skip, limit):
    """Urut relevansi pencarian (rank = id berperingkat, maks search.MAX_RANKED)."""
    if tipes:
        docs = await db.products.aggregate([
            {"$match": filt},
            {"$addFields": {"type_price_min": _type_price_expr(tipes, "$min"),
                            "type_price_max": _type_price_expr(tipes, "$max")}},
        ]).to_list(len(rank))
    else:
        docs = await db.products.find(filt).to_list(len(rank))
    pos = {pid: n for n, pid in enumerate(rank)}
    docs.sort(key=lambda d: pos.get(d.get("id"), len(pos)))
    return [V.serialize_product(safe_doc(d)) for d in docs[skip:skip + limit]], len(docs)


async def list_products(db, *, filt, sort_spec, skip=0, limit=LIMIT_DEFAULT, tipes=None, rank=None):
    """Kembalikan (items, total). Bounded — aman untuk N+1 & performa.
    Dengan `tipes`: harga tampil & sort memakai varian tipe tsb (type_price_min/max).
    Dengan `rank` (hasil pencarian, sort default): urut relevansi."""
    skip = parse_int(skip, 0, lo=0, hi=100000)
    limit = parse_int(limit, LIMIT_DEFAULT, lo=1, hi=LIMIT_MAX)
    if rank is not None:
        return await _ranked(db, filt, tipes, rank, skip, limit)
    total = await db.products.count_documents(filt)
    if tipes:
        sort_doc = {("type_price_min" if k == "price" else k): d for k, d in sort_spec}
        sort_doc["id"] = 1  # paginasi stabil
        docs = await db.products.aggregate([
            {"$match": filt},
            {"$addFields": {"type_price_min": _type_price_expr(tipes, "$min"),
                            "type_price_max": _type_price_expr(tipes, "$max")}},
            {"$sort": sort_doc}, {"$skip": skip}, {"$limit": limit},
        ]).to_list(limit)
        return [V.serialize_product(safe_doc(d)) for d in docs], total
    cursor = db.products.find(filt).sort(sort_spec).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [V.serialize_product(safe_doc(d)) for d in docs], total


async def get_product_by_slug(db, slug: str):
    if not slug:
        return None
    doc = await db.products.find_one({"slug": slug, "status": "active"})
    return V.serialize_product(safe_doc(doc)) if doc else None


async def list_categories(db):
    docs = await db.categories.find({"active": True}).sort([("name", 1)]).to_list(CATEGORIES_MAX)
    return [safe_doc(d) for d in docs]


async def list_occasions(db):
    docs = await db.occasions.find({"active": True}).sort([("order", 1), ("name", 1)]).to_list(CATEGORIES_MAX)
    return [safe_doc(d) for d in docs]


async def list_characters(db):
    """Karakter aktif + `count` produk aktif (untuk pencarian facet & kartu discovery)."""
    docs = await db.characters.find({"active": True}).sort([("order", 1), ("name", 1)]).to_list(CATEGORIES_MAX)
    counts = {r["_id"]: r["n"] async for r in db.products.aggregate([
        {"$match": {"status": "active"}}, {"$unwind": "$characters"},
        {"$group": {"_id": "$characters", "n": {"$sum": 1}}}])}
    return [{**safe_doc(d), "count": counts.get(d.get("slug"), 0)} for d in docs]


async def list_brands(db):
    """Brand dari produk aktif + profil (logo/foto/desc/urutan; `hidden` disembunyikan)."""
    from services.admin_brands import profiles
    rows = await db.products.aggregate([
        {"$match": {"status": "active", "brand": {"$nin": [None, ""]}}},
        {"$sort": {"best_seller": -1, "rating_avg": -1}},
        {"$group": {"_id": "$brand", "count": {"$sum": 1},
                    "images": {"$push": {"$arrayElemAt": ["$images", 0]}},
                    "names": {"$push": "$name"}}},
        {"$limit": BRANDS_MAX},
    ]).to_list(BRANDS_MAX)
    prof = await profiles(db)
    out = []
    for r in rows:
        p = prof.get(r["_id"], {})
        if p.get("hidden"):
            continue
        out.append({"name": r["_id"], "count": r["count"], "images": [i for i in r["images"] if i][:3],
                    "sample": r["names"][:3], "logo": p.get("logo", ""), "image": p.get("image", ""),
                    "desc": p.get("desc", ""), "order": p.get("order", 0)})
    # urutan manual (order > 0) dulu, lalu jumlah produk terbanyak
    out.sort(key=lambda b: (b["order"] <= 0, b["order"], -b["count"], b["name"].lower()))
    return out
