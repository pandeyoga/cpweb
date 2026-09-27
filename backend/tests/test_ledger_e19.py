"""E19 ledger idempoten & rekonsiliasi (butir 3,4,5,8,9,11,12,13,14): uji in-process + fault injection.

Tes bernama `test_unit_*` hanya butuh MongoDB (fixture dibuat sendiri) — dipakai CI.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
os.environ.setdefault("PAYMENT_DEADLINE_HOURS", "24")
os.environ.setdefault("MIDTRANS_MOCK", "true")
os.environ.setdefault("PUBLIC_SITE_URL", "http://localhost")

from services import account, backup, gateway, midtrans as mt, orders, payments, reconcile, stock  # noqa: E402
from services import product_io_session as sess  # noqa: E402
from services import startup  # noqa: E402
from services.order_create import sweep_stale_reserving  # noqa: E402

TAG = uuid.uuid4().hex[:6]
_INDEXED = []


def run(fn):
    async def main():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"] + "_unit"]  # DB terpisah: tak ganggu tes HTTP paralel
        if not _INDEXED:
            await startup.run(db, [])  # indeks unik (pay_locks, idempotency…) = bagian dari jaminan yang diuji
            _INDEXED.append(True)
        return await fn(db)
    return asyncio.run(main())


class Crash(Exception):
    pass


class FaultyDB:
    """Setelah `after` operasi tulis, SEMUA tulis berikutnya gagal (= proses mati)."""
    WRITES = {"insert_one", "insert_many", "update_one", "update_many", "delete_one", "delete_many",
              "find_one_and_update", "replace_one"}

    def __init__(self, db, after):
        self._db, self.left = db, after

    def __getitem__(self, name):
        return _FaultyColl(self, self._db[name])

    def __getattr__(self, name):
        return _FaultyColl(self, getattr(self._db, name))


class _FaultyColl:
    def __init__(self, parent, coll):
        self._p, self._c = parent, coll

    def __getattr__(self, name):
        attr = getattr(self._c, name)
        if name not in FaultyDB.WRITES:
            return attr

        async def wrapped(*a, **kw):
            if self._p.left <= 0:
                raise Crash(name)
            self._p.left -= 1
            return await attr(*a, **kw)
        return wrapped


async def _fixtures(db, stock=10, voucher_limit=0):
    pid, code = f"t_prod_{TAG}_{uuid.uuid4().hex[:4]}", f"TV{uuid.uuid4().hex[:6].upper()}"
    await db.shipping_methods.update_one({"id": "t-ship"}, {"$set": {"id": "t-ship", "name": "Uji", "price": 10000,
                                                                      "active": True, "eta": "1"}}, upsert=True)
    await db.payment_methods.update_one({"id": "t-pay"}, {"$set": {"id": "t-pay", "group": "online", "name": "Uji",
                                                                    "active": True, "fee": 0}}, upsert=True)
    variants = [{"sku": f"{pid}-{t}-{ml}", "options": {"Tipe": t, "Ukuran": f"{ml}ml"}, "price": 100000, "stock": stock}
                for t in ("Basic", "Refine", "Intense") for ml in (35, 60, 100)]
    await db.products.insert_one({"id": pid, "slug": pid, "name": "Uji", "status": "active", "category": "woody",
                                  "tier": "CP01", "date_night": False, "characters": [],
                                  "images": [], "options": [{"name": "Tipe", "values": ["Basic", "Refine", "Intense"]},
                                                            {"name": "Ukuran", "values": ["35ml", "60ml", "100ml"]}],
                                  "variants": variants})
    await db.vouchers.insert_one({"code": code, "type": "flat", "value": 5000, "active": True, "min_spend": 0,
                                  "usage_limit": voucher_limit, "per_user_limit": 0, "used_count": 0})
    return pid, code, variants


async def _stock(db, pid):
    return {v["sku"]: v["stock"] for v in (await db.products.find_one({"id": pid}))["variants"]}


def _payload(pid, variants, code):
    return dict(user=None, items_in=[{"product_id": pid, "sku": variants[0]["sku"], "quantity": 2},
                                     {"product_id": pid, "sku": variants[5]["sku"], "quantity": 1}],
                address={"name": "U", "phone": "1", "street": "s", "city": "c", "province": "p"},
                shipping_id="t-ship", payment={"group": "online", "method_id": "t-pay"}, voucher_code=code,
                email="u@example.com")


async def _cleanup(db, pid, code):
    codes = await db.orders.distinct("code", {"items.product_id": pid})
    await db.voucher_redemptions.delete_many({"$or": [{"voucher_code": code}, {"order_code": {"$in": codes}}]})
    await db.products.delete_one({"id": pid})
    await db.vouchers.delete_one({"code": code})
    await db.orders.delete_many({"items.product_id": pid})
    await db.shipping_methods.delete_one({"id": "t-ship"})
    await db.payment_methods.delete_one({"id": "t-pay"})


def test_unit_nine_variants_reserve_release_idempotent():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            items = [{"product_id": pid, "sku": v["sku"], "quantity": 1 + i % 3} for i, v in enumerate(vs)]
            for _ in range(2):
                assert (await stock.reserve(db, "T-1", items))[0]
            after = await _stock(db, pid)
            assert all(after[v["sku"]] == 10 - (1 + i % 3) for i, v in enumerate(vs))  # tak tertukar, tak dobel
            for _ in range(2):
                await stock.release(db, "T-1", items)
            assert set((await _stock(db, pid)).values()) == {10}
        finally:
            await _cleanup(db, pid, code)
    run(t)


@pytest.mark.parametrize("after", range(0, 9))
def test_unit_create_order_crash_at_every_write_is_recoverable(after):
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            try:
                await orders.create_order(FaultyDB(db, after), **_payload(pid, vs, code))
            except Exception:
                pass
            left = await db.orders.find_one({"items.product_id": pid})
            if left and left["status"] == "pending":  # semua langkah selesai sebelum crash → order sah & konsisten
                st = await _stock(db, pid)
                assert st[vs[0]["sku"]] == 8 and st[vs[5]["sku"]] == 9
                assert (await db.vouchers.find_one({"code": code}))["used_count"] == 1
                return
            await db.orders.update_many({"items.product_id": pid},
                                        {"$set": {"created_at": "2000-01-01T00:00:00+00:00"}})
            await sweep_stale_reserving(db)
            assert await db.orders.count_documents({"items.product_id": pid}) == 0
            assert set((await _stock(db, pid)).values()) == {10}
            v = await db.vouchers.find_one({"code": code})
            assert v["used_count"] == 0 and not v.get("redeemed_orders")
        finally:
            await _cleanup(db, pid, code)
    run(t)


def test_unit_cancel_crash_then_reconcile_restores_once():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            o = await orders.create_order(db, **_payload(pid, vs, code))
            with pytest.raises(Crash):
                await orders.transition_order(FaultyDB(db, 1), await db.orders.find_one({"code": o["code"]}), "cancelled")
            assert (await db.orders.find_one({"code": o["code"]}))["status"] == "cancelled"
            for _ in range(2):
                await reconcile.run(db)
            assert set((await _stock(db, pid)).values()) == {10}
            assert (await db.vouchers.find_one({"code": code}))["used_count"] == 0
            assert (await db.orders.find_one({"code": o["code"]}))["released"] is True
        finally:
            await _cleanup(db, pid, code)
    run(t)


def test_unit_paid_order_cannot_be_cancelled_without_refund_and_refund_is_stable():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            o = await orders.create_order(db, **_payload(pid, vs, code))
            await orders.record_payment(db, await db.orders.find_one({"code": o["code"]}), o["total"], ref="tx-a")
            await orders.record_payment(db, await db.orders.find_one({"code": o["code"]}), o["total"], ref="tx-a")
            cur = await db.orders.find_one({"code": o["code"]})
            assert cur["paid_amount"] == o["total"] and cur["status"] == "paid"  # idempoten per ref
            with pytest.raises(orders.InvalidTransition):
                await orders.transition_order(db, cur, "cancelled")
            calls = []
            real = mt.refund

            async def flaky(gid, amount, reason, key):
                calls.append(key)
                if len(calls) == 1:
                    raise mt.GatewayError("timeout")
                return {"status_code": "200"}
            mt.refund = flaky
            await db.payment_transactions.insert_one({"id": f"ptx_{TAG}", "order_code": o["code"], "status": "paid",
                                                      "gateway_order_id": f"{o['code']}-1", "gross_amount": o["total"],
                                                      "payment_applied": True, "created_at": "x"})
            try:
                with pytest.raises(gateway.PaymentError):
                    await gateway.refund_order(db, "adm", cur, 30000, "uji")
                await gateway.refund_order(db, "adm", await db.orders.find_one({"code": o["code"]}), 30000, "uji")
            finally:
                mt.refund = real
            assert calls[0] == calls[1]  # identitas refund stabil saat retry
            cur = await db.orders.find_one({"code": o["code"]})
            assert cur["refunded_amount"] == 30000 and await db.refunds.count_documents({"order_code": o["code"]}) == 1
        finally:
            await db.payment_transactions.delete_many({"id": f"ptx_{TAG}"})
            await db.refunds.delete_many({"order_code": {"$regex": "^CP"}, "tx_id": f"ptx_{TAG}"})
            await _cleanup(db, pid, code)
    run(t)


def test_unit_gateway_paid_not_applied_is_recovered_once():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            o = await orders.create_order(db, **_payload(pid, vs, code))
            await db.payment_transactions.insert_one({"id": f"ptx2_{TAG}", "order_code": o["code"], "status": "paid",
                                                      "gateway_order_id": f"{o['code']}-9", "gross_amount": o["total"]})
            for _ in range(2):
                await gateway.reconcile(db)
            cur = await db.orders.find_one({"code": o["code"]})
            assert cur["paid_amount"] == o["total"] and cur["status"] == "paid"
        finally:
            await db.payment_transactions.delete_many({"id": f"ptx2_{TAG}"})
            await _cleanup(db, pid, code)
    run(t)


def test_unit_parallel_pay_creates_single_attempt():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            o = await orders.create_order(db, **_payload(pid, vs, code))
            await db.orders.update_one({"code": o["code"]}, {"$set": {"payment.group": "online"}})
            doc = await db.orders.find_one({"code": o["code"]})
            res = await asyncio.gather(*[gateway.start_payment(db, doc) for _ in range(5)])
            assert len({r["gateway_order_id"] for r in res}) == 1
            assert await db.payment_transactions.count_documents({"order_code": o["code"]}) == 1
        finally:
            codes = await db.orders.distinct("code", {"items.product_id": pid})
            await db.payment_transactions.delete_many({"order_code": {"$in": codes}})
            await _cleanup(db, pid, code)
    run(t)


def test_unit_proof_processing_resumed_without_double_count():
    async def t(db):
        pid, code, vs = await _fixtures(db)
        try:
            o = await orders.create_order(db, **_payload(pid, vs, code))
            old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            await db.payment_proofs.insert_one({"id": f"pay_{TAG}", "order_code": o["code"], "amount": o["total"],
                                                "status": "processing", "verified_at": old})
            await orders.record_payment(db, await db.orders.find_one({"code": o["code"]}), o["total"], ref=f"pay_{TAG}")
            await payments.resume_processing(db)  # crash terjadi setelah uang tercatat, sebelum 'verified'
            assert (await db.payment_proofs.find_one({"id": f"pay_{TAG}"}))["status"] == "verified"
            assert (await db.orders.find_one({"code": o["code"]}))["paid_amount"] == o["total"]
        finally:
            await db.payment_proofs.delete_many({"id": f"pay_{TAG}"})
            await _cleanup(db, pid, code)
    run(t)


def test_unit_parallel_default_address_single_default():
    async def t(db):
        await account.ensure_default_index(db)
        uid = f"usr_t_{TAG}"
        try:
            a = await account.create_address(db, uid, {"name": "A", "street": "x"})
            b = await account.create_address(db, uid, {"name": "B", "street": "y"})
            for _ in range(10):
                await asyncio.gather(account.set_default_address(db, uid, a["id"]),
                                     account.set_default_address(db, uid, b["id"]))
                assert await db.addresses.count_documents({"user_id": uid, "is_default": True}) == 1
        finally:
            await db.addresses.delete_many({"user_id": uid})
    run(t)


def test_unit_backup_overwrite_failure_keeps_old_data():
    async def t(db):
        name = f"t_bk_{TAG}"
        try:
            await db[name].insert_many([{"_id": 1, "v": "lama"}, {"_id": 2, "v": "lama"}])
            rep = await backup._restore_collection(db, name, [{"_id": 9, "v": "baru"}, {"_id": 9, "v": "dup"}], "overwrite")
            assert rep["errors"] == 1 and await db[name].count_documents({"v": "lama"}) == 2
            rep = await backup._restore_collection(db, name, [{"_id": 7, "v": "baru"}], "overwrite")
            assert rep["errors"] == 0 and [d["_id"] async for d in db[name].find()] == [7]
        finally:
            await db[name].drop()
    run(t)


def test_unit_import_session_rewrite_failure_keeps_previous_rows():
    async def t(db):
        s = await sess.create(db, "adm_t", "f.csv", ["a"], [{"a": str(i)} for i in range(5)])
        try:
            with pytest.raises(Crash):
                await sess.save_rows(FaultyDB(db, 2), s["id"], "adm_t", [{"a": "baru"}])  # chunk baru tertulis, meta gagal
            rows, _ = await sess.load_rows(db, s["id"], "adm_t")
            assert [r["a"] for r in rows] == [str(i) for i in range(5)]
            await sess.save_rows(db, s["id"], "adm_t", [{"a": "baru"}])
            assert [r["a"] for r in (await sess.load_rows(db, s["id"], "adm_t"))[0]] == ["baru"]
            with pytest.raises(sess.TooManyRows):
                await sess.create(db, "adm_t", "big.csv", ["a"], [{"a": 1}] * (sess.MAX_ROWS + 1))
        finally:
            await sess.close(db, s["id"], "adm_t")
    run(t)


def test_unit_seed_rejects_default_password_in_production():
    import subprocess
    env = {**os.environ, "SEED_REQUIRE_STRONG_PASS": "1", "ADMIN_PASS": "Admin#2026", "CUST_PASS": "x" * 16,
           "DB_NAME": f"seedcheck_{TAG}"}
    r = subprocess.run(["python", "/app/scripts/seed_data.py"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode != 0 and "SEED DITOLAK" in (r.stdout + r.stderr)
    assert "Admin#2026" not in r.stdout
    run(lambda db: db.client.drop_database(f"seedcheck_{TAG}"))


def test_unit_expiry_advances_past_orders_held_by_pending_proof():
    from services import order_expiry

    async def t(db):
        pid, code, vs = await _fixtures(db)
        old_batch = order_expiry.BATCH_MAX
        order_expiry.BATCH_MAX = 1
        try:
            codes = []
            for _ in range(3):
                o = await orders.create_order(db, **{**_payload(pid, vs, None), "voucher_code": None})
                codes.append(o["code"])
            await db.orders.update_many({"code": {"$in": codes}}, {"$set": {"payment_deadline": "2000-01-01T00:00:00+00:00"}})
            await db.payment_proofs.insert_one({"id": f"pp_{TAG}", "order_code": codes[0], "status": "pending", "amount": 1})
            res = await order_expiry.expire_overdue_orders(db)
            assert set(res["expired"]) >= set(codes[1:]) and codes[0] in res["skipped"]
            assert (await db.orders.find_one({"code": codes[0]}))["status"] == "pending"
        finally:
            order_expiry.BATCH_MAX = old_batch
            await db.payment_proofs.delete_many({"id": f"pp_{TAG}"})
            await _cleanup(db, pid, code)
    run(t)


def test_http_cron_reclaims_failed_run_and_client_purchase_ignored():
    import requests
    load_dotenv("/app/frontend/.env")
    base = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
    h = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}", "X-Webhook-Id": f"run_{TAG}"}
    run(lambda db: db.cron_runs.insert_one({"run_id": f"run_{TAG}", "job": "reconcile", "status": "failed",
                                            "created_at": "2000-01-01T00:00:00+00:00"}))
    r = requests.post(f"{base}/cron/reconcile", headers=h, timeout=30)
    assert r.status_code == 202 and not r.json().get("duplicate")
    r2 = requests.post(f"{base}/cron/reconcile", headers=h, timeout=30)
    assert r2.json().get("duplicate") is True
    ev = requests.post(f"{base}/analytics/event", json={"type": "purchase", "order_code": "FAKE"}, timeout=30).json()
    assert ev.get("stored") is False
    run(lambda db: db.cron_runs.delete_many({"run_id": f"run_{TAG}"}))
