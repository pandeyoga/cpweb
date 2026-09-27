"""Hardening E17: kontrak config admin (strict), edit parsial voucher/kategori, ?ids=, logout server,
brute-force login, idempotency fingerprint, anti-SSRF unduh media, header aman SVG."""
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
LOCAL = "http://localhost:8001/api"  # IP klien stabil (egress publik pod berganti-ganti IP NAT)
MONGO_URL, DB_NAME = os.environ["MONGO_URL"], os.environ["DB_NAME"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@collectorparfum.id", "password": "Admin#2026"}, timeout=30)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_config_endpoints_reject_unknown_fields(admin_h):
    for path, body in (("/admin/settings", {"store_nama": "x"}), ("/admin/store-config", {"intro": "x"}),
                       ("/admin/store-config", {"rating_avg": 4.1}), ("/admin/settings", {"cod_fee": 1})):
        r = requests.put(f"{BASE}{path}", json=body, headers=admin_h, timeout=30)
        assert r.status_code == 422, (path, body, r.text)


def test_store_config_round_trip_every_field(admin_h):
    before = requests.get(f"{BASE}/admin/store-config", headers=admin_h, timeout=30).json()
    tag = uuid.uuid4().hex[:6]
    body = {"maps_mode": "embed", "reviews_source": "manual", "google_maps_api_key": f"k{tag}",
            "google_places_api_key": f"p{tag}", "google_place_id": f"id{tag}",
            "store_rating_avg": 4.3, "store_rating_count": 1234, "stores_intro": f"Intro {tag}"}
    try:
        r = requests.put(f"{BASE}/admin/store-config", json=body, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        got = requests.get(f"{BASE}/admin/store-config", headers=admin_h, timeout=30).json()
        for k, v in body.items():
            assert got[k] == v, k
        pub = requests.get(f"{BASE}/stores", timeout=30).json()["config"]
        assert pub["intro"] == f"Intro {tag}" and pub["rating"] == {"avg": 4.3, "count": 1234}
    finally:
        requests.put(f"{BASE}/admin/store-config", headers=admin_h, timeout=30, json={
            k: before.get(k) for k in body if before.get(k) is not None})


def test_settings_round_trip(admin_h):
    before = requests.get(f"{BASE}/admin/settings", headers=admin_h, timeout=30).json()
    body = {"support_phone": "0811-000", "low_stock_threshold": 7, "inspired_by_label": "Terinspirasi"}
    try:
        assert requests.put(f"{BASE}/admin/settings", json=body, headers=admin_h, timeout=30).status_code == 200
        got = requests.get(f"{BASE}/admin/settings", headers=admin_h, timeout=30).json()
        assert all(got[k] == v for k, v in body.items())
    finally:
        requests.put(f"{BASE}/admin/settings", headers=admin_h, timeout=30,
                     json={k: before[k] for k in body if k in before})


def test_voucher_edit_keeps_scope_and_campaign(admin_h):
    code = f"KEEP{uuid.uuid4().hex[:5].upper()}"
    r = requests.post(f"{BASE}/admin/vouchers", headers=admin_h, timeout=30, json={
        "code": code, "type": "flat", "value": 5000, "scope": {"category": "woody", "product_ids": []},
        "starts_at": "2026-01-01T00:00:00+00:00", "ends_at": "2027-01-01T00:00:00+00:00",
        "campaign": {"name": "Kampanye", "theme": "x"}})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    try:
        r2 = requests.put(f"{BASE}/admin/vouchers/{vid}", headers=admin_h, timeout=30, json={
            "code": code, "type": "flat", "value": 7000, "label": "baru", "min_spend": 0,
            "usage_limit": 0, "per_user_limit": 0, "active": True})
        assert r2.status_code == 200, r2.text
        v = r2.json()
        assert v["value"] == 7000 and v["scope"]["category"] == "woody"
        assert v["starts_at"] and v["ends_at"] and v["campaign"]["name"] == "Kampanye"
    finally:
        requests.delete(f"{BASE}/admin/vouchers/{vid}", headers=admin_h, timeout=30)


def test_category_edit_keeps_seo(admin_h):
    r = requests.post(f"{BASE}/admin/categories", headers=admin_h, timeout=30, json={
        "name": f"Uji {uuid.uuid4().hex[:5]}", "seo": {"title": "SEO Judul", "description": "d"}})
    cid = r.json()["id"]
    try:
        c = requests.put(f"{BASE}/admin/categories/{cid}", headers=admin_h, timeout=30,
                         json={"name": "Uji Ganti", "desc": "baru", "active": True}).json()
        assert c["seo"]["title"] == "SEO Judul" and c["desc"] == "baru"
    finally:
        requests.delete(f"{BASE}/admin/categories/{cid}", headers=admin_h, timeout=30)


def test_products_by_ids_exact():
    items = requests.get(f"{BASE}/products", params={"limit": 100, "sort": "low"}, timeout=30).json()
    pick = [items[-1]["id"], items[0]["id"]]
    r = requests.get(f"{BASE}/products", params={"ids": ",".join(pick + ["prd_tidak_ada"])}, timeout=30)
    assert r.status_code == 200 and sorted(p["id"] for p in r.json()) == sorted(pick)
    assert r.headers["X-Total-Count"] == "2"


def test_logout_revokes_session():
    r = requests.post(f"{BASE}/auth/login", json={"email": "customer@collectorparfum.id", "password": "Customer#2026"}, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert requests.get(f"{BASE}/auth/me", headers=h, timeout=30).status_code == 200
    assert requests.post(f"{BASE}/auth/logout", headers=h, timeout=30).json() == {"ok": True}
    assert requests.get(f"{BASE}/auth/me", headers=h, timeout=30).status_code == 401


def _clean_brute(email):
    async def clean():
        db = _db()
        await db.login_attempts.delete_many({"identifier": {"$regex": email.replace(".", r"\.")}})
        u = await db.users.find_one_and_delete({"email": email})
        if u:
            await db.sessions.delete_many({"user_id": u["id"]})
    _run(clean())


def test_login_lockout_email_wide_resists_spoofed_forwarded_for():
    email = f"brute_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{LOCAL}/auth/register", json={"name": "Uji", "email": email, "password": "Rahasia#123"}, timeout=30)
    try:
        for i in range(20):  # rotasi X-Forwarded-For palsu tiap percobaan
            requests.post(f"{LOCAL}/auth/login", json={"email": email, "password": "salah"},
                          headers={"X-Forwarded-For": f"203.0.113.{i}"}, timeout=30)
        r = requests.post(f"{LOCAL}/auth/login", json={"email": email, "password": "Rahasia#123"},
                          headers={"X-Forwarded-For": "198.51.100.7"}, timeout=30)
        assert r.status_code == 429
    finally:
        _clean_brute(email)


def test_login_lockout_after_five_failures():
    email = f"brute_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{LOCAL}/auth/register", json={"name": "Uji", "email": email, "password": "Rahasia#123"}, timeout=30)
    try:
        codes = [requests.post(f"{LOCAL}/auth/login", json={"email": email, "password": "salah"}, timeout=30).status_code
                 for _ in range(5)]
        assert codes == [401] * 5
        r = requests.post(f"{LOCAL}/auth/login", json={"email": email, "password": "Rahasia#123"}, timeout=30)
        assert r.status_code == 429 and "Retry-After" in r.headers
    finally:
        _clean_brute(email)


def _order_body(pid, sku, qty=1):
    return {"items": [{"product_id": pid, "sku": sku, "quantity": qty}],
            "address": {"name": "Tamu Idem", "phone": "0812", "street": "Jl A", "city": "Bandung", "province": "Jabar"},
            "email": "idem@example.com", "shipping_id": "jne-reg", "payment": {"group": "online", "method_id": "midtrans"}}


def test_idempotency_key_bound_to_payload(admin_h):
    async def pick():
        p = await _db().products.find_one({"status": "active", "variants.stock": {"$gt": 5}})
        return p["id"], next(v["sku"] for v in p["variants"] if v["stock"] > 5)
    pid, sku = _run(pick())
    key = uuid.uuid4().hex
    h = {"Idempotency-Key": key}
    r1 = requests.post(f"{BASE}/orders", json=_order_body(pid, sku), headers=h, timeout=30)
    assert r1.status_code == 200, r1.text
    code = r1.json()["code"]
    try:
        r2 = requests.post(f"{BASE}/orders", json=_order_body(pid, sku), headers=h, timeout=30)
        assert r2.status_code == 200 and r2.json()["code"] == code
        r3 = requests.post(f"{BASE}/orders", json=_order_body(pid, sku, qty=2), headers=h, timeout=30)
        assert r3.status_code == 409 and r3.json()["detail"]["code"] == "idempotency_conflict"
        assert _run(_db().orders.count_documents({"idempotency_key": key})) == 1
    finally:
        requests.put(f"{BASE}/admin/orders/{code}/status", json={"status": "cancelled"}, headers=admin_h, timeout=30)
        _run(_db().orders.delete_one({"code": code}))


@pytest.mark.parametrize("url", ["http://127.0.0.1:8001/api/health", "http://169.254.169.254/latest/meta-data",
                                 "http://localhost/x.png", "http://10.0.0.1/a.jpg"])
def test_media_from_url_blocks_internal_hosts(admin_h, url):
    r = requests.post(f"{BASE}/admin/media/from-url", json={"url": url, "download": True}, headers=admin_h, timeout=30)
    assert r.status_code == 400 and ("internal" in r.text or "privat" in r.text), r.text


def test_svg_served_with_sandbox_csp(admin_h):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><script>alert(1)</script></svg>'
    r = requests.post(f"{BASE}/admin/media/upload", headers=admin_h, timeout=30,
                      files={"files": ("uji.svg", svg, "image/svg+xml")})
    assert r.status_code == 201, r.text
    asset = r.json()["uploaded"][0]
    try:
        url = asset["url"]
        g = requests.get(url if url.startswith("http") else BASE.rsplit("/api", 1)[0] + url, timeout=30)
        assert g.status_code == 200
        assert "sandbox" in g.headers.get("Content-Security-Policy", "")
        assert g.headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        requests.delete(f"{BASE}/admin/media/assets/{asset['id']}", headers=admin_h, timeout=30)
