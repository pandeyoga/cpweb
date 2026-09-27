"""E15 — email transaksional: konfirmasi lunas, pengingat batas bayar, admin email-logs, cron auth.
Menggunakan REACT_APP_BACKEND_URL (public URL) + Mongo langsung dari backend/.env.
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
CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]

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
                           {"$set": {"variants.$.stock": 200}})
    return p["id"], v["sku"]


def _body(pid, sku, email=None):
    email = email or f"tamu_{uuid.uuid4().hex[:6]}@example.com"
    return {
        "items": [{"product_id": pid, "sku": sku, "quantity": 1}],
        "address": {"name": "Tamu E15", "phone": "0812", "street": "Jl A",
                    "city": "Bandung", "province": "Jabar", "email": email},
        "shipping_id": "jne-reg",
        "payment": {"group": "online", "method_id": "midtrans"},
    }


def _create_online(pid, sku):
    r = requests.post(f"{BASE}/orders", json=_body(pid, sku), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _cleanup(admin_h, code):
    try:
        requests.put(f"{BASE}/admin/orders/{code}/status", json={"status": "cancelled"},
                     headers=admin_h, timeout=30)
    except Exception:
        pass


# =====================================================================
# Cron auth
# =====================================================================
class TestCronAuth:
    @pytest.mark.parametrize("path", ["expire-orders", "payment-reminders", "sync-payments"])
    def test_no_auth_401(self, path):
        r = requests.post(f"{BASE}/cron/{path}", timeout=15)
        assert r.status_code == 401

    @pytest.mark.parametrize("path", ["expire-orders", "payment-reminders", "sync-payments"])
    def test_wrong_bearer_401(self, path):
        r = requests.post(f"{BASE}/cron/{path}",
                          headers={"Authorization": "Bearer wrong"}, timeout=15)
        assert r.status_code == 401

    def test_reminders_ok_202(self):
        r = requests.post(f"{BASE}/cron/payment-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=15)
        assert r.status_code == 202
        j = r.json()
        assert j.get("accepted") is True

    def test_sync_payments_ok_202(self, db):
        r = requests.post(f"{BASE}/cron/sync-payments",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=15)
        assert r.status_code == 202
        run_id = r.json().get("run_id")
        # wait for background completion
        for _ in range(20):
            time.sleep(0.5)
            doc = db.cron_runs.find_one({"run_id": run_id})
            if doc and doc.get("status") in ("done", "failed"):
                break
        assert doc["status"] == "done", doc
        assert "mode" in doc["result"]
        assert "checked" in doc["result"]

    def test_expire_orders_ok_202(self):
        r = requests.post(f"{BASE}/cron/expire-orders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=15)
        assert r.status_code == 202


# =====================================================================
# Paid confirmation email — Midtrans mock happy path
# =====================================================================
class TestPaidConfirmation:
    def test_online_pay_creates_one_paid_email(self, admin_h, variant, db):
        pid, sku = variant
        o = _create_online(pid, sku)
        code = o["code"]
        try:
            # start payment
            r = requests.post(f"{BASE}/orders/{code}/pay",
                              params={"t": o["access_token"]}, timeout=30)
            assert r.status_code == 200, r.text
            # mock settlement
            r = requests.post(f"{BASE}/orders/{code}/mock-pay",
                              params={"t": o["access_token"]},
                              json={"outcome": "settlement"}, timeout=30)
            assert r.status_code == 200, r.text
            # wait for async email task
            time.sleep(2.5)
            logs = list(db.email_logs.find({"order_code": code, "kind": "paid_confirmation"}))
            assert len(logs) == 1, f"expected 1 paid_confirmation, got {len(logs)}"
            lg = logs[0]
            assert lg["status"] == "mocked"
            assert lg["to"] == o["email"]
            assert lg["subject"] == f"Pembayaran diterima — Pesanan {code}"

            # Duplicate mock-pay must NOT create a second log
            requests.post(f"{BASE}/orders/{code}/mock-pay",
                          params={"t": o["access_token"]},
                          json={"outcome": "settlement"}, timeout=30)
            time.sleep(1.5)
            logs2 = list(db.email_logs.find({"order_code": code, "kind": "paid_confirmation"}))
            assert len(logs2) == 1, f"duplicate created ({len(logs2)})"
        finally:
            # order is paid, admin cancel would violate INV. Just clean DB.
            db.orders.delete_one({"code": code})
            db.analytics_events.delete_many({"order_code": code})
            db.email_logs.delete_many({"order_code": code})
            db.payment_transactions.delete_many({"order_code": code})
            db.analytics_events.delete_many({"order_code": code})


# =====================================================================
# Payment reminders cron — slot logic + idempotency
# =====================================================================
class TestPaymentReminders:
    def _run_and_wait(self, db):
        r = requests.post(f"{BASE}/cron/payment-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=15)
        assert r.status_code == 202
        run_id = r.json().get("run_id")
        for _ in range(30):
            time.sleep(0.5)
            doc = db.cron_runs.find_one({"run_id": run_id})
            if doc and doc.get("status") in ("done", "failed"):
                break
        assert doc["status"] == "done", doc
        return doc["result"]

    def test_slot_selection_and_idempotency(self, admin_h, variant, db):
        pid, sku = variant
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        # Create 3 orders with different deadlines
        o_10h = _create_online(pid, sku)  # 10h → 12h slot
        o_90m = _create_online(pid, sku)  # 90 min → 2h slot
        o_far = _create_online(pid, sku)  # 20h → nothing
        codes = [o_10h["code"], o_90m["code"], o_far["code"]]
        try:
            db.orders.update_one({"code": o_10h["code"]},
                                 {"$set": {"payment_deadline": (now + timedelta(hours=10)).isoformat()}})
            db.orders.update_one({"code": o_90m["code"]},
                                 {"$set": {"payment_deadline": (now + timedelta(minutes=90)).isoformat()}})
            db.orders.update_one({"code": o_far["code"]},
                                 {"$set": {"payment_deadline": (now + timedelta(hours=20)).isoformat()}})

            res = self._run_and_wait(db)
            assert "sent" in res and "skipped" in res

            # Validate slots
            l12 = list(db.email_logs.find({"order_code": o_10h["code"], "kind": "reminder_12h"}))
            l2 = list(db.email_logs.find({"order_code": o_90m["code"], "kind": "reminder_2h"}))
            lfar = list(db.email_logs.find({"order_code": o_far["code"]}))
            assert len(l12) == 1, f"12h slot expected once, got {len(l12)}"
            assert len(l2) == 1, f"2h slot expected once, got {len(l2)}"
            assert len(lfar) == 0, f"far-future got {len(lfar)} email(s)"

            assert l12[0]["status"] == "mocked"
            assert l12[0]["to"] == o_10h["email"]
            assert l2[0]["status"] == "mocked"

            # orders.emails_sent recorded
            d10 = db.orders.find_one({"code": o_10h["code"]})
            d90 = db.orders.find_one({"code": o_90m["code"]})
            assert "reminder_12h" in (d10.get("emails_sent") or [])
            assert "reminder_2h" in (d90.get("emails_sent") or [])

            # Run again → no duplicates (use new run_id)
            self._run_and_wait(db)
            l12b = list(db.email_logs.find({"order_code": o_10h["code"], "kind": "reminder_12h"}))
            l2b = list(db.email_logs.find({"order_code": o_90m["code"], "kind": "reminder_2h"}))
            assert len(l12b) == 1, "12h duplicated on rerun"
            assert len(l2b) == 1, "2h duplicated on rerun"
        finally:
            for c in codes:
                _cleanup(admin_h, c)
                db.email_logs.delete_many({"order_code": c})


# =====================================================================
# Admin email-logs endpoints
# =====================================================================
class TestAdminEmailLogs:
    def test_non_admin_forbidden(self, cust_h):
        r = requests.get(f"{BASE}/admin/email-logs", headers=cust_h, timeout=15)
        assert r.status_code in (401, 403)
        r = requests.get(f"{BASE}/admin/email-logs", timeout=15)
        assert r.status_code in (401, 403)

    def test_list_shape_and_detail_and_resend(self, admin_h, variant, db):
        pid, sku = variant
        # produce one email
        o = _create_online(pid, sku)
        code = o["code"]
        try:
            r = requests.post(f"{BASE}/orders/{code}/pay",
                              params={"t": o["access_token"]}, timeout=30)
            assert r.status_code == 200
            r = requests.post(f"{BASE}/orders/{code}/mock-pay",
                              params={"t": o["access_token"]},
                              json={"outcome": "settlement"}, timeout=30)
            assert r.status_code == 200
            time.sleep(2.5)

            r = requests.get(f"{BASE}/admin/email-logs", headers=admin_h, timeout=30)
            assert r.status_code == 200
            data = r.json()
            assert data["mode"] == "mock"
            assert data["from_email"] == "noreply@collectorparfum.com"
            assert isinstance(data["items"], list) and len(data["items"]) >= 1
            first = data["items"][0]
            assert "html" not in first  # list must not include html
            # find our log
            mine = next((x for x in data["items"] if x.get("order_code") == code
                         and x["kind"] == "paid_confirmation"), None)
            assert mine is not None
            log_id = mine["id"]

            # detail includes html
            r = requests.get(f"{BASE}/admin/email-logs/{log_id}", headers=admin_h, timeout=30)
            assert r.status_code == 200
            det = r.json()
            assert "html" in det and det["html"]
            html = det["html"]
            assert code in html
            # item name present
            item_name = o["items"][0].get("name", "")
            if item_name:
                assert item_name[:20] in html or item_name in html
            # currency formatting Rp x.xxx
            assert "Rp " in html
            assert "/pesanan-sukses?code=" in html

            # resend creates a new log (status mocked)
            before = db.email_logs.count_documents({"order_code": code})
            r = requests.post(f"{BASE}/admin/email-logs/{log_id}/resend",
                              headers=admin_h, timeout=30)
            assert r.status_code == 200
            resent = r.json()
            assert resent["status"] == "mocked"
            assert resent["kind"] == "paid_confirmation"
            after = db.email_logs.count_documents({"order_code": code})
            assert after == before + 1

            # 404 on unknown id
            r = requests.get(f"{BASE}/admin/email-logs/bogus_id_xxx", headers=admin_h, timeout=15)
            assert r.status_code == 404
        finally:
            db.orders.delete_one({"code": code})
            db.analytics_events.delete_many({"order_code": code})
            db.email_logs.delete_many({"order_code": code})
            db.payment_transactions.delete_many({"order_code": code})
            db.analytics_events.delete_many({"order_code": code})
