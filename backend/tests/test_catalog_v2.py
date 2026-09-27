"""Kontrak katalog v2 + temuan audit (tier, date_night, tipe, konsentrasi dihapus, kontak/newsletter,
paginasi order admin, total Rp0 ditolak)."""
import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONGO_URL, DB_NAME = os.environ["MONGO_URL"], os.environ["DB_NAME"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@collectorparfum.id", "password": "Admin#2026"}, timeout=30)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _products(**params):
    r = requests.get(f"{BASE}/products", params={"limit": 100, **params}, timeout=30)
    assert r.status_code == 200
    return r.json(), int(r.headers["X-Total-Count"])


def test_public_product_has_no_concentration_or_ingredients():
    items, _ = _products()
    assert items
    for p in items:
        assert "concentration" not in p and "ingredients" not in p
        assert p.get("tier") in ("CP01", "CP02", "CP03", "EXCLUSIVE")
        assert isinstance(p.get("date_night"), bool)


def test_filters_tier_datenight_tipe_combine():
    all_items, total = _products()
    dn, n_dn = _products(date_night=1)
    assert n_dn == sum(p["date_night"] for p in all_items) and all(p["date_night"] for p in dn)
    legacy, n_legacy = _products(occasion="date-night")
    assert n_legacy == n_dn
    t, n_t = _products(tier="CP01")
    assert n_t == sum(p["tier"] == "CP01" for p in all_items) and all(p["tier"] == "CP01" for p in t)
    refine, _ = _products(tipe="Refine", sort="low")
    for p in refine:
        prices = [v["price"] for v in p["variants"] if v["options"].get("Tipe") == "Refine"]
        assert prices and p["type_price_min"] == min(prices)
    assert [p["type_price_min"] for p in refine] == sorted(p["type_price_min"] for p in refine)
    cap = min(p["type_price_min"] for p in refine) if refine else 0
    within, _ = _products(tipe="Refine", max_price=cap)
    assert all(p["type_price_min"] <= cap for p in within)
    combo, n_combo = _products(tier="CP01", date_night=1, tipe="Basic")
    assert all(p["tier"] == "CP01" and p["date_night"] for p in combo)
    assert n_combo <= min(n_t, n_dn)


def test_only_date_night_occasion_public():
    r = requests.get(f"{BASE}/occasions", timeout=30)
    assert [o["slug"] for o in r.json()] == ["date-night"]


def test_admin_tier_datenight_roundtrip_and_export(admin_h):
    p = _run(_db().products.find_one({"slug": "noir-oud-intense"}))
    r = requests.get(f"{BASE}/admin/products/{p['id']}", headers=admin_h, timeout=30)
    body = r.json()
    payload = {k: body[k] for k in ("name", "slug", "brand", "category", "gender", "options", "variants",
                                    "characters", "description", "images", "status")}
    payload.update(tier="EXCLUSIVE", date_night=False, concentration="EDP")
    r = requests.put(f"{BASE}/admin/products/{p['id']}", json=payload, headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tier"] == "EXCLUSIVE" and d["date_night"] is False and d["occasions"] == []
    assert "concentration" not in d
    exp = requests.get(f"{BASE}/admin/products/io/export", params={"format": "csv"}, headers=admin_h, timeout=60)
    head = exp.text.splitlines()[0]
    assert "tier" in head and "date_night" in head and "concentration" not in head and "ingredients" not in head
    payload.update(tier=body.get("tier") or "CP01", date_night=body.get("date_night", True))
    requests.put(f"{BASE}/admin/products/{p['id']}", json=payload, headers=admin_h, timeout=30)


def test_contact_and_newsletter_persist(admin_h):
    tag = uuid.uuid4().hex[:8]
    r = requests.post(f"{BASE}/contact", json={"name": "Uji", "email": f"u{tag}@example.com", "message": f"halo {tag}"}, timeout=30)
    assert r.status_code == 200
    msgs = requests.get(f"{BASE}/admin/contact-messages", headers=admin_h, timeout=30).json()
    assert any(m["message"] == f"halo {tag}" for m in msgs)
    assert requests.post(f"{BASE}/contact", json={"name": "x", "email": "bukan-email", "message": "m"}, timeout=30).status_code == 422
    for _ in range(2):
        assert requests.post(f"{BASE}/newsletter", json={"email": f"N{tag}@Example.com"}, timeout=30).status_code == 200
    assert _run(_db().newsletter_subscribers.count_documents({"email": f"n{tag}@example.com"})) == 1


def test_admin_orders_paginated_and_search(admin_h):
    r = requests.get(f"{BASE}/admin/orders", params={"limit": 2}, headers=admin_h, timeout=30)
    total = int(r.headers["X-Total-Count"])
    if total == 0:
        pytest.skip("belum ada pesanan di DB")
    assert len(r.json()) == min(2, total)
    if total > 2:
        r2 = requests.get(f"{BASE}/admin/orders", params={"limit": 2, "skip": 2}, headers=admin_h, timeout=30)
        assert {o["code"] for o in r.json()}.isdisjoint({o["code"] for o in r2.json()})
    code = r.json()[0]["code"]
    r3 = requests.get(f"{BASE}/admin/orders", params={"q": code}, headers=admin_h, timeout=30)
    assert [o["code"] for o in r3.json()] == [code]


def test_zero_total_order_rejected():
    async def prep():
        db = _db()
        ship = await db.shipping_methods.find_one({"id": "jne-reg"}, {"_id": 0})
        await db.shipping_methods.update_one({"id": "test-free"}, {"$set": {**ship, "id": "test-free", "price": 0}}, upsert=True)
        await db.vouchers.update_one({"code": "TESTNOL100"}, {"$set": {
            "code": "TESTNOL100", "type": "percent", "value": 100, "active": True, "min_spend": 0,
            "per_user_limit": 0, "usage_limit": 0, "label": "uji"}, "$setOnInsert": {"id": "vcr_testnol", "used_count": 0}}, upsert=True)
        p = await db.products.find_one({"status": "active", "variants.stock": {"$gt": 0}})
        v = next(x for x in p["variants"] if x["stock"] > 0)
        return p["id"], v["sku"]
    pid, sku = _run(prep())
    body = {"items": [{"product_id": pid, "sku": sku, "quantity": 1}], "voucher_code": "TESTNOL100",
            "address": {"name": "Tamu", "phone": "0812", "street": "Jl A", "city": "Bandung", "province": "Jabar"},
            "email": "tamu@example.com", "shipping_id": "test-free", "payment": {"group": "online", "method_id": "midtrans"}}
    try:
        r = requests.post(f"{BASE}/orders", json=body, headers={"Idempotency-Key": uuid.uuid4().hex}, timeout=30)
        assert r.status_code == 400 and "Rp0" in r.text, r.text
    finally:
        async def clean():
            db = _db()
            await db.shipping_methods.delete_one({"id": "test-free"})
            await db.vouchers.delete_one({"code": "TESTNOL100"})
        _run(clean())
