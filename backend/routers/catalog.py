"""routers/catalog.py — Katalog publik (read-path, Epic E1).

Kontrak (respons = ARRAY/OBJEK telanjang; TANPA envelope):
  GET /api/brands          -> [{name, count, images[], sample[]}]  (brand produk aktif)
  GET /api/products?category&gender&tier&day_night(day,night)&tipe&character&brand&min_price&max_price&q&ids&tag&sort&limit&skip
      -> [Product, ...]   (hanya status=active) + header X-Total-Count
      q = pencarian toleran typo/singkatan; sort default/relevance → urut relevansi; header X-Did-You-Mean.
  GET /api/search/suggest?q&limit -> {query, did_you_mean, total, products[], terms[]}  (saran instan)
  GET /api/products/{slug} -> Product          (404 bila tak ada / archived)
  GET /api/categories      -> [Category, ...]  (hanya active)
  GET /api/reviews?product_id -> [Review, ...] (hanya published)

Router TIPIS: hanya I/O + validasi ringan; logika query ada di services/catalog.py.
Param numerik diterima sebagai string lalu di-clamp (services.parse_int) → tak pernah 5xx.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response

from db import get_db
from services import catalog as svc
from services import search as search_svc

router = APIRouter(tags=["catalog"])


@router.get("/products")
async def get_products(
    response: Response,
    category: Optional[str] = Query(default=None),
    gender: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
    day_night: Optional[str] = Query(default=None),
    date_night: Optional[str] = Query(default=None),
    tipe: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    occasion: Optional[str] = Query(default=None),
    character: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    ids: Optional[str] = Query(default=None),
    min_price: Optional[str] = Query(default=None),
    max_price: Optional[str] = Query(default=None),
    best_seller: Optional[str] = Query(default=None),
    is_new: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default="featured"),
    limit: Optional[str] = Query(default=None),
    skip: Optional[str] = Query(default=None),
):
    db = get_db()
    filt = svc.build_product_filter(
        category=category, gender=gender, tier=tier, day_night=day_night, date_night=date_night, tipe=tipe,
        tag=tag, occasion=occasion, character=character, brand=brand,
        min_price=min_price, max_price=max_price,
        best_seller=best_seller, is_new=is_new, ids=ids,
    )
    rank = None
    if q and q.strip():
        rank, dym = await search_svc.ranked_ids(db, q[:80])
        if "id" in filt:
            allowed = set(filt["id"]["$in"])
            rank = [i for i in rank if i in allowed]
        filt["id"] = {"$in": rank}
        if dym:
            response.headers["X-Did-You-Mean"] = dym
        if (sort or "featured").strip().lower() not in ("featured", "relevance"):
            rank = None  # sort eksplisit (harga/terbaru) menang atas relevansi
    items, total = await svc.list_products(
        db, filt=filt, sort_spec=svc.resolve_sort(sort),
        skip=skip if skip is not None else 0,
        limit=limit if limit is not None else svc.LIMIT_DEFAULT,
        tipes=svc._multi(tipe), rank=rank,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/search/suggest")
async def search_suggest(q: Optional[str] = Query(default=""), limit: Optional[str] = Query(default="6")):
    db = get_db()
    q = (q or "").strip()[:80]
    if not q:
        return {"query": "", "did_you_mean": None, "total": 0, "products": [], "terms": []}
    n = svc.parse_int(limit, 6, lo=1, hi=12)
    rank, dym = await search_svc.ranked_ids(db, q)
    items, total = await svc.list_products(db, filt={"status": "active", "id": {"$in": rank}},
                                           sort_spec=svc.resolve_sort("featured"), limit=n, rank=rank)
    return {"query": q, "did_you_mean": dym, "total": total, "products": items,
            "terms": await search_svc.suggest_terms(db, q)}


@router.get("/products/{slug}")
async def get_product(slug: str):
    db = get_db()
    product = await svc.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return product


@router.get("/categories")
async def get_categories():
    db = get_db()
    return await svc.list_categories(db)


@router.get("/occasions")
async def get_occasions():
    db = get_db()
    return await svc.list_occasions(db)


@router.get("/characters")
async def get_characters():
    db = get_db()
    return await svc.list_characters(db)


@router.get("/brands")
async def get_brands():
    db = get_db()
    return await svc.list_brands(db)


@router.get("/reviews")
async def get_reviews(product_id: Optional[str] = Query(default=None)):
    db = get_db()
    return await svc.list_reviews(db, product_id)
