"""Regresi Fase 1 (E14 prasyarat Midtrans). Jalankan: python scripts/test_fase1_sales.py

SALES-06 auto-batal lewat batas bayar (cron) · SALES-07 kuota voucher kembali saat batal ·
SALES-10 idempotency key · SALES-13 email wajib tamu · COD dihapus · SALES-09 gratis ongkir.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
load_dotenv(os.path.join(ROOT, "backend", ".env"))
API = os.environ.get("API_BASE", "http://localhost:8001") + "/api"
RES, CREATED = [], []


def check(name, ok, info=""):
    RES.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f" — {info}" if info else ""))


async def login(c, email, pw):
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def stock_of(db, pid, sku):
    p = await db.products.find_one({"id": pid})
    return next(v["stock"] for v in p["variants"] if v["sku"] == sku)


def body(pid, sku, qty=1, email="tamu@example.com", voucher=None, group="transfer", method="bca"):
    b = {"items": [{"product_id": pid, "sku": sku, "quantity": qty}],
         "address": {"name": "Tamu", "phone": "0812", "street": "Jl A", "city": "Bandung", "province": "Jabar"},
         "shipping_id": "jne-reg", "payment": {"group": group, "method_id": method}}
    if email:
        b["email"] = email
    if voucher:
        b["voucher_code"] = voucher
    return b


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.payment_methods.update_one({"id": "bca"}, {"$set": {"active": True}})  # uji alur bukti manual (legacy)
    p = await db.products.find_one({"status": "active", "variants.0": {"$exists": True}})
    pid, sku = p["id"], p["variants"][0]["sku"]
    await db.products.update_one({"id": pid, "variants.sku": sku}, {"$set": {"variants.$.stock": 50}})
    async with httpx.AsyncClient(timeout=30) as c:
        cus = await login(c, "customer@collectorparfum.id", "Customer#2026")

        # SALES-13 email
        r = await c.post(f"{API}/orders", json=body(pid, sku, email=None))
        check("tamu tanpa email → 400", r.status_code == 400, f"{r.status_code}")
        r = await c.post(f"{API}/orders", json=body(pid, sku, email=None), headers=cus)
        o = r.json()
        CREATED.append(o.get("code"))
        check("login tanpa email → pakai email akun", o.get("email") == "customer@collectorparfum.id", o.get("email"))
        dl = datetime.fromisoformat(o["payment_deadline"]) - datetime.now(timezone.utc)
        check("payment_deadline ≈ 24 jam", timedelta(hours=23, minutes=58) < dl <= timedelta(hours=24), str(dl))

        # COD dihapus
        r = await c.post(f"{API}/orders", json=body(pid, sku, group="cod", method="cod"), headers=cus)
        check("checkout COD → 400", r.status_code == 400, f"{r.status_code}")

        # SALES-10 idempotency (berurutan + paralel)
        before = await stock_of(db, pid, sku)
        key = str(uuid.uuid4())
        rs = await asyncio.gather(*[c.post(f"{API}/orders", json=body(pid, sku), headers={**cus, "Idempotency-Key": key})
                                    for _ in range(5)])
        codes = {x.json().get("code") for x in rs if x.status_code == 200}
        r2 = await c.post(f"{API}/orders", json=body(pid, sku), headers={**cus, "Idempotency-Key": key})
        codes.add(r2.json().get("code"))
        CREATED.extend(codes)
        after = await stock_of(db, pid, sku)
        check("idempotency: 6 request → 1 order, stok turun 1×", len(codes) == 1 and before - after == 1,
              f"codes={codes} delta={before - after}")
        r3 = await c.post(f"{API}/orders", json=body(pid, sku), headers={"Idempotency-Key": key})
        check("key milik user lain dipakai tamu → 400", r3.status_code == 400, f"{r3.status_code}")

        # SALES-07 voucher per-user dikembalikan saat batal
        await db.voucher_redemptions.delete_many({"voucher_code": "WELCOME10"})
        await db.voucher_user_usage.delete_many({"voucher_code": "WELCOME10"})
        v0 = (await db.vouchers.find_one({"code": "WELCOME10"}))["used_count"]
        r = await c.post(f"{API}/orders", json=body(pid, sku, voucher="WELCOME10"), headers=cus)
        vo = r.json()
        CREATED.append(vo.get("code"))
        await c.post(f"{API}/orders/{vo['code']}/cancel", headers=cus)
        v1 = (await db.vouchers.find_one({"code": "WELCOME10"}))["used_count"]
        red = await db.voucher_redemptions.count_documents({"order_code": vo["code"]})
        check("batal → used_count kembali & redemption dihapus", v1 == v0 and red == 0, f"{v0}->{v1} red={red}")
        r = await c.post(f"{API}/orders", json=body(pid, sku, voucher="WELCOME10"), headers=cus)
        CREATED.append(r.json().get("code"))
        check("voucher per_user_limit=1 bisa dipakai lagi setelah batal", r.status_code == 200, f"{r.status_code}")
        await c.post(f"{API}/orders/{r.json()['code']}/cancel", headers=cus)

        # SALES-06 cron auto-batal
        r = await c.post(f"{API}/orders", json=body(pid, sku, qty=2), headers=cus)
        eo = r.json()
        r = await c.post(f"{API}/orders", json=body(pid, sku), headers=cus)
        po = r.json()
        CREATED.extend([eo["code"], po["code"]])
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await db.orders.update_many({"code": {"$in": [eo["code"], po["code"]]}}, {"$set": {"payment_deadline": past}})
        await c.post(f"{API}/orders/{po['code']}/payment-proof", json={"amount": po["total"]}, headers=cus)
        s0 = await stock_of(db, pid, sku)
        r = await c.post(f"{API}/cron/expire-orders", headers={"Authorization": "Bearer salah"})
        check("cron secret salah → 401", r.status_code == 401, f"{r.status_code}")
        secret = os.environ["WEBHOOK_CRON_SECRET"]
        rid = str(uuid.uuid4())
        r = await c.post(f"{API}/cron/expire-orders",
                         headers={"Authorization": f"Bearer {secret}", "X-Webhook-Id": rid}, json={})
        check("cron secret benar → 202", r.status_code == 202, f"{r.status_code}")
        r = await c.post(f"{API}/cron/expire-orders",
                         headers={"Authorization": f"Bearer {secret}", "X-Webhook-Id": rid}, json={})
        check("run_id sama → duplicate ack", r.json().get("duplicate") is True, r.text)
        await asyncio.sleep(1.5)
        e_doc = await db.orders.find_one({"code": eo["code"]})
        p_doc = await db.orders.find_one({"code": po["code"]})
        s1 = await stock_of(db, pid, sku)
        check("order lewat batas → cancelled/expired + stok kembali",
              e_doc["status"] == "cancelled" and e_doc.get("cancel_reason") == "expired" and s1 - s0 == 2,
              f"{e_doc['status']}/{e_doc.get('cancel_reason')} delta={s1 - s0}")
        check("order dgn bukti pending tidak dibatalkan", p_doc["status"] == "pending", p_doc["status"])
        await db.payment_proofs.delete_many({"order_code": po["code"]})
        await c.post(f"{API}/orders/{po['code']}/cancel", headers=cus)

        # SALES-09 gratis ongkir
        await db.settings.update_one({"id": "store"}, {"$set": {"free_shipping_threshold": 1}})
        r = await c.post(f"{API}/orders", json=body(pid, sku), headers=cus)
        fo = r.json()
        CREATED.append(fo["code"])
        await db.settings.update_one({"id": "store"}, {"$set": {"free_shipping_threshold": 0}})
        check("ambang gratis ongkir → shipping.price 0 & total konsisten",
              fo["shipping"]["price"] == 0 and fo["total"] == fo["subtotal"] - fo["discount"],
              f"ship={fo['shipping']['price']} total={fo['total']}")
        await c.post(f"{API}/orders/{fo['code']}/cancel", headers=cus)

        for code in set(filter(None, CREATED)):
            d = await db.orders.find_one({"code": code})
            if d and d["status"] == "pending":
                await c.post(f"{API}/orders/{code}/cancel", headers=cus)

    from services.gateway import sync_payment_methods
    await sync_payment_methods(db)
    print(f"\n{sum(RES)}/{len(RES)} PASS")
    sys.exit(0 if all(RES) else 1)


asyncio.run(main())
