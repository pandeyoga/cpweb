"""Pytest — regresi 5 bug SALES + edge cases (BUG-SALES-01..05).
Menggunakan REACT_APP_BACKEND_URL (public) dan kredensial dari /app/memory/test_credentials.md.
"""
import asyncio
import os
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN = ("admin@collectorparfum.id", "Admin#2026")
CUST = ("customer@collectorparfum.id", "Customer#2026")


# ---------- helpers ----------
def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_h():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def cust_h():
    return _login(*CUST)


@pytest.fixture(scope="module")
def variant():
    """Return (pid, sku) of an active product with stock >= 50 (bumped)."""
    async def _prep():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        p = await db.products.find_one({"status": "active", "variants.0": {"$exists": True}})
        v = p["variants"][0]
        await db.products.update_one({"id": p["id"], "variants.sku": v["sku"]},
                                     {"$set": {"variants.$.stock": 100}})
        return p["id"], v["sku"]
    return asyncio.get_event_loop().run_until_complete(_prep())


def _body(pid, sku, qty=1, email="tamu@example.com"):
    return {"items": [{"product_id": pid, "sku": sku, "quantity": qty}],
            "address": {"name": "Tamu", "phone": "0812", "street": "Jl A", "city": "Bandung",
                        "province": "Jabar", "email": email},
            "shipping_id": "jne-reg", "payment": {"group": "online", "method_id": "midtrans"}}


class _Resp:
    def __init__(self, r, data):
        self.status_code, self.text, self._d = r.status_code, r.text, data

    def json(self):
        return self._d


def _post_order(json=None, headers=None, timeout=30):
    """POST /orders (online) lalu ubah jadi transfer manual di DB utk uji alur bukti (legacy)."""
    r = requests.post(f"{BASE}/orders", json=json, headers=headers or {}, timeout=timeout)
    if r.status_code != 200:
        return _Resp(r, r.json() if r.content else {})
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    pay = {"group": "transfer", "method_id": "bca", "name": "Transfer BCA"}
    db.orders.update_one({"code": r.json()["code"]}, {"$set": {"payment": pay}})
    return _Resp(r, {**r.json(), "payment": pay})


def _create_order(headers=None, pid=None, sku=None, qty=1):
    r = _post_order(json=_body(pid, sku, qty), headers=headers or {}, timeout=30)
    assert r.status_code == 200, r.text
    # Alur bukti transfer manual (legacy): ubah order jadi transfer di DB — tanpa mengaktifkan metode
    # manual secara global (aman utk worker xdist paralel).
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    pay = {"group": "transfer", "method_id": "bca", "name": "Transfer BCA"}
    db.orders.update_one({"code": r.json()["code"]}, {"$set": {"payment": pay}})
    return {**r.json(), "payment": pay}


def _admin_cancel(admin_h, code):
    """Cancel order uji. Order yg sudah dibayar dihapus langsung (admin-cancel order lunas
    melanggar INV-P2 sampai alur refund SALES-16 ada)."""
    import os
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    o = db.orders.find_one({"code": code}) or {}
    if int(o.get("paid_amount", 0) or 0) <= 0:
        requests.put(f"{BASE}/admin/orders/{code}/status", json={"status": "cancelled"}, headers=admin_h, timeout=30)
        return
    if o.get("status") != "cancelled":
        for it in o.get("items", []):
            db.products.update_one({"id": it["product_id"], "variants.sku": it["sku"]},
                                   {"$inc": {"variants.$.stock": it["quantity"]}})
    db.payment_proofs.delete_many({"order_code": code})
    db.orders.delete_one({"code": code})
    db.analytics_events.delete_many({"order_code": code})
    db.analytics_events.delete_many({"order_code": code})


# ---------- BUG-SALES-01: guest access-token + IDOR ----------
class TestBugSales01:
    def test_guest_checkout_returns_access_token_and_404_without(self, variant):
        pid, sku = variant
        o = _create_order(pid=pid, sku=sku)
        assert "access_token" in o and o["access_token"], "guest order MUST return access_token"
        assert o["code"].startswith("CP"), f"code={o['code']}"

        # No token -> 404
        r = requests.get(f"{BASE}/orders/{o['code']}", timeout=30)
        assert r.status_code == 404

        # Wrong token -> 404
        r = requests.get(f"{BASE}/orders/{o['code']}", params={"t": "wrongtoken"}, timeout=30)
        assert r.status_code == 404

        # Correct token -> 200 with data
        r = requests.get(f"{BASE}/orders/{o['code']}", params={"t": o["access_token"]}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == o["code"]
        assert data["total"] == o["total"]

        # Cleanup
        admin = _login(*ADMIN)
        _admin_cancel(admin, o["code"])

    def test_logged_in_owner_vs_other_user(self, cust_h, admin_h, variant):
        pid, sku = variant
        # Owner cust creates order
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        assert r.status_code == 200, r.text
        code = r.json()["code"]

        # Owner GET without token -> 200
        r = requests.get(f"{BASE}/orders/{code}", headers=cust_h, timeout=30)
        assert r.status_code == 200

        # Another user (admin) GET -> 404 (admin uses same endpoint w/o admin route)
        r = requests.get(f"{BASE}/orders/{code}", headers=admin_h, timeout=30)
        assert r.status_code == 404

        # Anon -> 404
        r = requests.get(f"{BASE}/orders/{code}", timeout=30)
        assert r.status_code == 404

        _admin_cancel(admin_h, code)


# ---------- BUG-SALES-02: concurrent admin cancel restores stock once ----------
@pytest.fixture
def isolated_variant():
    """Produk klon sekali-pakai: stoknya tak disentuh tes lain yang jalan paralel (xdist)."""
    import uuid
    tag = uuid.uuid4().hex[:8]
    pid, sku = f"prd_test_cancel_{tag}", f"TEST-CANCEL-{tag}"

    async def _mk():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        src = await db.products.find_one({"status": "active", "variants.0": {"$exists": True}}, {"_id": 0})
        v = {**src["variants"][0], "sku": sku, "stock": 100}
        src.update(id=pid, slug=f"test-cancel-{tag}", name=f"TEST Cancel {tag}", variants=[v],
                   volumes=[{**(src.get("volumes") or [{}])[0], "sku": sku, "stock": 100}])
        await db.products.insert_one(src)

    async def _rm():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        codes = await db.orders.distinct("code", {"items.product_id": pid})
        await db.orders.delete_many({"code": {"$in": codes}})
        await db.analytics_events.delete_many({"order_code": {"$in": codes}})
        await db.products.delete_one({"id": pid})

    asyncio.get_event_loop().run_until_complete(_mk())
    yield pid, sku
    asyncio.get_event_loop().run_until_complete(_rm())


class TestBugSales02:
    def test_concurrent_cancels_restore_once(self, cust_h, admin_h, isolated_variant):
        pid, sku = isolated_variant

        async def run():
            db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
            r = _post_order(json=_body(pid, sku, 2), headers=cust_h, timeout=30)
            code = r.json()["code"]
            p = await db.products.find_one({"id": pid})
            before = next(v["stock"] for v in p["variants"] if v["sku"] == sku)

            import httpx
            async with httpx.AsyncClient(timeout=30) as c:
                results = await asyncio.gather(*[
                    c.put(f"{BASE}/admin/orders/{code}/status", json={"status": "cancelled"}, headers=admin_h)
                    for _ in range(5)
                ])
            codes = sorted([r.status_code for r in results])
            p = await db.products.find_one({"id": pid})
            after = next(v["stock"] for v in p["variants"] if v["sku"] == sku)
            return before, after, codes

        before, after, codes = asyncio.get_event_loop().run_until_complete(run())
        assert after - before == 2, f"stock restored {after-before}x, expected 1x*qty2"
        assert codes.count(200) == 1, f"expected exactly one 200, got {codes}"
        assert codes.count(400) >= 1, f"expected 400s for losers, got {codes}"


# ---------- BUG-SALES-03: manual pending->paid ----------
class TestBugSales03:
    def test_transfer_pending_to_paid_manual_rejected(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        code = r.json()["code"]
        r = requests.put(f"{BASE}/admin/orders/{code}/status", json={"status": "paid"}, headers=admin_h, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"
        _admin_cancel(admin_h, code)

    def test_cod_pending_to_paid_allowed(self, cust_h, admin_h, variant):
        pid, sku = variant
        body = _body(pid, sku)
        body["payment"] = {"group": "cod", "method_id": "cod"}
        r = _post_order(json=body, headers=cust_h, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"COD method not configured: {r.status_code} {r.text}")
        code = r.json()["code"]
        r = requests.put(f"{BASE}/admin/orders/{code}/status", json={"status": "paid"}, headers=admin_h, timeout=30)
        assert r.status_code == 200, f"COD manual paid should succeed, got {r.status_code} {r.text}"
        _admin_cancel(admin_h, code)

    def test_transfer_paid_via_verified_proof(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        o = r.json()
        r = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                         json={"amount": o["total"]}, headers=cust_h, timeout=30)
        assert r.status_code == 200
        pid_proof = r.json()["id"]
        r = requests.put(f"{BASE}/admin/payments/{pid_proof}/verify",
                        json={"approve": True}, headers=admin_h, timeout=30)
        assert r.status_code == 200
        # Fetch order state
        r = requests.get(f"{BASE}/orders/{o['code']}", headers=cust_h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "paid"
        assert d["payment_status"] == "lunas"
        _admin_cancel(admin_h, o["code"])


# ---------- BUG-SALES-04: overpay protection & partial DP ----------
class TestBugSales04:
    def test_overpay_single_proof_rejected(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        o = r.json()
        r = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                         json={"amount": o["total"] + 1}, headers=cust_h, timeout=30)
        assert r.status_code == 400
        _admin_cancel(admin_h, o["code"])

    def test_two_full_proofs_second_verify_fails_and_reverts(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        o = r.json()
        # Submit two proofs each = total
        r1 = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                          json={"amount": o["total"]}, headers=cust_h, timeout=30)
        r2 = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                          json={"amount": o["total"]}, headers=cust_h, timeout=30)
        assert r1.status_code == 200
        assert r2.status_code == 200, f"second submit should succeed (still pending); got {r2.status_code} {r2.text}"
        p1 = r1.json()["id"]
        p2 = r2.json()["id"]
        # Verify first: 200 lunas
        v1 = requests.put(f"{BASE}/admin/payments/{p1}/verify", json={"approve": True}, headers=admin_h, timeout=30)
        assert v1.status_code == 200
        # Verify second: must fail (over sisa)
        v2 = requests.put(f"{BASE}/admin/payments/{p2}/verify", json={"approve": True}, headers=admin_h, timeout=30)
        assert v2.status_code == 400, f"second verify must fail, got {v2.status_code} {v2.text}"
        # Second proof must be reverted to pending
        # Query via admin payments list (may not exist), fallback to DB check
        async def _check():
            db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
            proof = await db.payment_proofs.find_one({"id": p2})
            order = await db.orders.find_one({"code": o["code"]})
            return proof, order
        proof, order = asyncio.get_event_loop().run_until_complete(_check())
        assert proof["status"] == "pending", f"second proof status={proof['status']} (expected pending revert)"
        assert order["paid_amount"] == order["total"], "paid_amount must equal total (never exceed)"
        _admin_cancel(admin_h, o["code"])

    def test_partial_dp_then_remainder(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        o = r.json()
        half = int(o["total"]) // 2
        rest = int(o["total"]) - half
        r1 = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                          json={"amount": half}, headers=cust_h, timeout=30)
        assert r1.status_code == 200
        p1 = r1.json()["id"]
        v1 = requests.put(f"{BASE}/admin/payments/{p1}/verify", json={"approve": True}, headers=admin_h, timeout=30)
        assert v1.status_code == 200
        # Second (remainder)
        r2 = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                          json={"amount": rest}, headers=cust_h, timeout=30)
        assert r2.status_code == 200
        p2 = r2.json()["id"]
        v2 = requests.put(f"{BASE}/admin/payments/{p2}/verify", json={"approve": True}, headers=admin_h, timeout=30)
        assert v2.status_code == 200
        r = requests.get(f"{BASE}/orders/{o['code']}", headers=cust_h, timeout=30)
        d = r.json()
        assert d["payment_status"] == "lunas"
        assert d["status"] == "paid"
        _admin_cancel(admin_h, o["code"])


# ---------- BUG-SALES-05: customer cancel only pending ----------
class TestBugSales05:
    def test_cancel_pending_ok(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        code = r.json()["code"]
        r = requests.post(f"{BASE}/orders/{code}/cancel", headers=cust_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cancel_paid_rejected(self, cust_h, admin_h, variant):
        pid, sku = variant
        r = _post_order(json=_body(pid, sku), headers=cust_h, timeout=30)
        o = r.json()
        r = requests.post(f"{BASE}/orders/{o['code']}/payment-proof",
                         json={"amount": o["total"]}, headers=cust_h, timeout=30)
        pid_proof = r.json()["id"]
        requests.put(f"{BASE}/admin/payments/{pid_proof}/verify",
                    json={"approve": True}, headers=admin_h, timeout=30)
        # Now paid
        r = requests.post(f"{BASE}/orders/{o['code']}/cancel", headers=cust_h, timeout=30)
        assert r.status_code == 400
        _admin_cancel(admin_h, o["code"])
