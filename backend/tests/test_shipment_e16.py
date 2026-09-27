"""E16 — pengiriman: kurir + resi + email shipped/shipped_update.
Public URL + Mongo dari backend/.env.
"""
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN = ("admin@collectorparfum.id", "Admin#2026")
CUST = ("customer@collectorparfum.id", "Customer#2026")


def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_h():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def cust_h():
    return _login(*CUST)


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def variant(db):
    p = db.products.find_one({"status": "active", "variants.0": {"$exists": True}})
    v = p["variants"][0]
    db.products.update_one({"id": p["id"], "variants.sku": v["sku"]},
                           {"$set": {"variants.$.stock": 500}})
    return p["id"], v["sku"]


def _body(pid, sku):
    email = f"tamu_{uuid.uuid4().hex[:6]}@example.com"
    return {
        "items": [{"product_id": pid, "sku": sku, "quantity": 1}],
        "address": {"name": "E16 Test", "phone": "0812", "street": "Jl A",
                    "city": "Bandung", "province": "Jabar", "email": email},
        "shipping_id": "jne-reg",
        "payment": {"group": "online", "method_id": "midtrans"},
    }


def _create_paid_packed(pid, sku, admin_h):
    """Create order -> pay (mock settlement) -> admin packed. Returns order dict."""
    r = requests.post(f"{BASE}/orders", json=_body(pid, sku), timeout=30)
    assert r.status_code == 200, r.text
    o = r.json()
    code = o["code"]
    r = requests.post(f"{BASE}/orders/{code}/pay", params={"t": o["access_token"]}, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/orders/{code}/mock-pay", params={"t": o["access_token"]},
                      json={"outcome": "settlement"}, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.put(f"{BASE}/admin/orders/{code}/status",
                     json={"status": "packed"}, headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    time.sleep(0.5)
    return o


def _cleanup(db, code):
    db.orders.delete_one({"code": code})
    db.analytics_events.delete_many({"order_code": code})
    db.email_logs.delete_many({"order_code": code})
    db.payment_transactions.delete_many({"order_code": code})
    db.analytics_events.delete_many({"order_code": code})


# =====================================================================
# GET /api/admin/couriers
# =====================================================================
class TestCouriers:
    def test_list_couriers_admin(self, admin_h):
        r = requests.get(f"{BASE}/admin/couriers", headers=admin_h, timeout=15)
        assert r.status_code == 200
        data = r.json()
        ids = {c["id"] for c in data}
        assert ids == {"jne", "jnt", "sicepat", "anteraja", "lainnya"}, ids
        for c in data:
            assert "name" in c

    def test_list_couriers_no_auth(self):
        r = requests.get(f"{BASE}/admin/couriers", timeout=15)
        assert r.status_code in (401, 403)

    def test_list_couriers_non_admin(self, cust_h):
        r = requests.get(f"{BASE}/admin/couriers", headers=cust_h, timeout=15)
        assert r.status_code in (401, 403)


# =====================================================================
# PUT /api/admin/orders/{code}/status — shipped path (validation)
# =====================================================================
class TestShipStatusValidation:
    def test_shipped_without_resi_400(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped"}, headers=admin_h, timeout=30)
            assert r.status_code == 400, r.text
            assert "resi" in r.text.lower()
            # order must remain packed
            doc = db.orders.find_one({"code": code})
            assert doc["status"] == "packed"
        finally:
            _cleanup(db, code)

    def test_shipped_short_resi_400_status_unchanged(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped", "courier": "jne",
                                   "tracking_number": "ABC12"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 400, r.text
            doc = db.orders.find_one({"code": code})
            assert doc["status"] == "packed"
        finally:
            _cleanup(db, code)

    def test_shipped_symbol_resi_400(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped", "courier": "jne",
                                   "tracking_number": "ABC@#123$"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 400
            doc = db.orders.find_one({"code": code})
            assert doc["status"] == "packed"
        finally:
            _cleanup(db, code)

    def test_shipped_invalid_courier_400(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped", "courier": "bogus",
                                   "tracking_number": "JP123456789"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 400
            doc = db.orders.find_one({"code": code})
            assert doc["status"] == "packed"
        finally:
            _cleanup(db, code)


# =====================================================================
# Happy path: ship + email + admin update shipment
# =====================================================================
class TestShipHappyPath:
    def test_ship_with_jnt_stores_shipment_and_sends_email(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped", "courier": "jnt",
                                   "tracking_number": "JP 1234 5678 90"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "shipped"
            sh = body["shipment"]
            assert sh["courier"] == "jnt"
            assert sh["courier_name"] == "J&T Express"
            assert sh["tracking_number"] == "JP1234567890"  # spaces stripped
            assert sh["tracking_url"] == "https://jet.co.id/track"
            assert sh["shipped_at"]

            # DB confirms
            doc = db.orders.find_one({"code": code})
            assert doc["status"] == "shipped"
            assert doc["shipment"]["tracking_number"] == "JP1234567890"

            # Wait for background email
            time.sleep(2.5)
            logs = list(db.email_logs.find({"order_code": code, "kind": "shipped"}))
            assert len(logs) == 1, f"expected 1 shipped email, got {len(logs)}"
            lg = logs[0]
            assert lg["status"] == "mocked"
            assert lg["subject"] == f"Pesanan {code} sedang dikirim"
            assert "JP1234567890" in lg["html"]
            assert "J&amp;T Express" in lg["html"] or "J&T Express" in lg["html"]
            assert "https://jet.co.id/track" in lg["html"]
            # Lihat Pesanan link with /pesanan-sukses?code=..&t=..
            assert "/pesanan-sukses?code=" in lg["html"]
            assert "&amp;t=" in lg["html"] or "&t=" in lg["html"]
        finally:
            _cleanup(db, code)

    def test_update_shipment_same_values_no_new_email(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            requests.put(f"{BASE}/admin/orders/{code}/status",
                         json={"status": "shipped", "courier": "jne",
                               "tracking_number": "JNE1234567"},
                         headers=admin_h, timeout=30)
            time.sleep(2.5)
            before = db.email_logs.count_documents(
                {"order_code": code, "kind": {"$in": ["shipped", "shipped_update"]}})
            assert before == 1

            r = requests.put(f"{BASE}/admin/orders/{code}/shipment",
                             json={"courier": "jne", "tracking_number": "JNE1234567"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200
            time.sleep(2.0)
            after = db.email_logs.count_documents(
                {"order_code": code, "kind": {"$in": ["shipped", "shipped_update"]}})
            assert after == before, "no new email expected for same resi"
        finally:
            _cleanup(db, code)

    def test_update_shipment_changed_resi_sends_update_email(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            requests.put(f"{BASE}/admin/orders/{code}/status",
                         json={"status": "shipped", "courier": "jne",
                               "tracking_number": "JNE1111111"},
                         headers=admin_h, timeout=30)
            time.sleep(2.5)

            r = requests.put(f"{BASE}/admin/orders/{code}/shipment",
                             json={"courier": "jne", "tracking_number": "JNE2222222"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200
            body = r.json()
            assert body["shipment"]["tracking_number"] == "JNE2222222"

            time.sleep(2.5)
            upd = list(db.email_logs.find({"order_code": code, "kind": "shipped_update"}))
            assert len(upd) == 1, f"expected 1 shipped_update, got {len(upd)}"
            assert upd[0]["subject"] == f"Pembaruan resi — Pesanan {code}"
            assert "JNE2222222" in upd[0]["html"]

            # original shipped still exactly 1
            first = list(db.email_logs.find({"order_code": code, "kind": "shipped"}))
            assert len(first) == 1
        finally:
            _cleanup(db, code)

    def test_update_shipment_changed_courier_sends_update_email(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            requests.put(f"{BASE}/admin/orders/{code}/status",
                         json={"status": "shipped", "courier": "jne",
                               "tracking_number": "AAA1234567"},
                         headers=admin_h, timeout=30)
            time.sleep(2.5)

            r = requests.put(f"{BASE}/admin/orders/{code}/shipment",
                             json={"courier": "sicepat", "tracking_number": "AAA1234567"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200
            assert r.json()["shipment"]["courier"] == "sicepat"
            assert r.json()["shipment"]["courier_name"] == "SiCepat"

            time.sleep(2.5)
            upd = list(db.email_logs.find({"order_code": code, "kind": "shipped_update"}))
            assert len(upd) == 1, f"expected 1 shipped_update, got {len(upd)}"
        finally:
            _cleanup(db, code)

    def test_lainnya_uses_cekresi(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/status",
                             json={"status": "shipped", "courier": "lainnya",
                                   "tracking_number": "XYZ9999999"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200
            url = r.json()["shipment"]["tracking_url"]
            assert url.startswith("https://cekresi.com/?noresi=")
            assert "XYZ9999999" in url
        finally:
            _cleanup(db, code)

    def test_update_shipment_on_non_shipped_400(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_paid_packed(pid, sku, admin_h)  # packed, not shipped
        code = o["code"]
        try:
            r = requests.put(f"{BASE}/admin/orders/{code}/shipment",
                             json={"courier": "jne", "tracking_number": "JNE1234567"},
                             headers=admin_h, timeout=30)
            assert r.status_code == 400
        finally:
            _cleanup(db, code)


# =====================================================================
# Auth guards
# =====================================================================
class TestAuthGuards:
    def test_shipment_update_no_auth(self):
        r = requests.put(f"{BASE}/admin/orders/BOGUS/shipment",
                         json={"courier": "jne", "tracking_number": "JNE1234567"},
                         timeout=15)
        assert r.status_code in (401, 403)

    def test_shipment_update_non_admin(self, cust_h):
        r = requests.put(f"{BASE}/admin/orders/BOGUS/shipment",
                         json={"courier": "jne", "tracking_number": "JNE1234567"},
                         headers=cust_h, timeout=15)
        assert r.status_code in (401, 403)
