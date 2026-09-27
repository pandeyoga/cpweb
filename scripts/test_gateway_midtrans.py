"""Regresi Midtrans Snap (E14 Fase 2-4) — mode SIMULASI + unit mode/signature.
Jalankan: python scripts/test_gateway_midtrans.py
"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
load_dotenv(os.path.join(ROOT, "backend", ".env"))
from services import midtrans as mt  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001") + "/api"
RES = []


def check(name, ok, info=""):
    RES.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f" — {info}" if info else ""))


def unit_mode_signature():
    saved = {k: os.environ.get(k) for k in ("MIDTRANS_SERVER_KEY", "MIDTRANS_MOCK", "MIDTRANS_IS_PRODUCTION")}
    try:
        os.environ.update({"MIDTRANS_SERVER_KEY": "", "MIDTRANS_MOCK": "false"})
        check("unit: key kosong + mock off → off", mt.mode() == "off" and not mt.public_config()["enabled"])
        os.environ.update({"MIDTRANS_SERVER_KEY": "SB-Mid-server-x", "MIDTRANS_IS_PRODUCTION": "false"})
        cfg = mt.public_config()
        check("unit: key ada → live + snap.js sandbox", mt.mode() == "live" and "sandbox" in cfg["snap_js_url"])
        os.environ["MIDTRANS_IS_PRODUCTION"] = "true"
        check("unit: production → app.midtrans.com", mt.public_config()["snap_js_url"] == "https://app.midtrans.com/snap/snap.js")
        n = {"order_id": "CP1-1", "status_code": "200", "gross_amount": "10000.00"}
        n["signature_key"] = mt.signature(n["order_id"], n["status_code"], n["gross_amount"])
        check("unit: signature valid diterima", mt.verify_signature(n))
        check("unit: gross_amount diubah → ditolak", not mt.verify_signature({**n, "gross_amount": "1.00"}))
        check("unit: server key TIDAK ada di config publik", "SB-Mid-server-x" not in str(mt.public_config()))
    finally:
        for k, v in saved.items():
            os.environ[k] = v or ""


def body(pid, sku, qty=1):
    return {"items": [{"product_id": pid, "sku": sku, "quantity": qty}], "email": "tamu@example.com",
            "address": {"name": "Tamu", "phone": "0812", "street": "Jl A", "city": "Bandung", "province": "Jabar"},
            "shipping_id": "jne-reg", "payment": {"group": "online", "method_id": "midtrans"}}


async def main():
    unit_mode_signature()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    p = await db.products.find_one({"status": "active", "variants.0": {"$exists": True}})
    pid, sku = p["id"], p["variants"][0]["sku"]
    await db.products.update_one({"id": pid, "variants.sku": sku}, {"$set": {"variants.$.stock": 50}})
    stock = lambda d: next(v["stock"] for v in d["variants"] if v["sku"] == sku)  # noqa: E731
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}/auth/login", json={"email": "admin@collectorparfum.id", "password": "Admin#2026"})
        adm = {"Authorization": f"Bearer {r.json()['token']}"}
        cfg = (await c.get(f"{API}/payments/config")).json()
        check("config mode mock, tanpa server key", cfg["mode"] == "mock" and cfg["client_key"] is None, str(cfg))
        pms = (await c.get(f"{API}/payment-methods")).json()
        check("hanya 'Bayar Online' aktif", [m["id"] for m in pms] == ["midtrans"], str([m["id"] for m in pms]))

        o = (await c.post(f"{API}/orders", json=body(pid, sku))).json()
        t = {"t": o["access_token"]}
        r = await c.post(f"{API}/orders/{o['code']}/pay")
        check("pay tanpa token tamu → 404", r.status_code == 404, f"{r.status_code}")
        tx1 = (await c.post(f"{API}/orders/{o['code']}/pay", params=t)).json()
        tx2 = (await c.post(f"{API}/orders/{o['code']}/pay", params=t)).json()
        check("snap token dibuat & dipakai ulang", tx1.get("token", "").startswith("mock-") and tx1 == tx2, str(tx1))
        r = await c.post(f"{API}/orders/{o['code']}/payment-proof", json={"amount": 1000}, headers=adm)
        bad = {"order_id": tx1["gateway_order_id"], "status_code": "200", "gross_amount": f"{o['total']}.00",
               "transaction_status": "settlement", "signature_key": "palsu"}
        r = await c.post(f"{API}/payments/midtrans/notification", json=bad)
        check("webhook signature palsu → 403", r.status_code == 403, f"{r.status_code}")
        wrong = {**bad, "gross_amount": "1000.00"}
        wrong["signature_key"] = mt.signature(wrong["order_id"], "200", "1000.00")
        r = await c.post(f"{API}/payments/midtrans/notification", json=wrong)
        check("nominal beda → amount_mismatch, tak dibayar", r.json().get("state") == "amount_mismatch", r.text)
        od = (await c.post(f"{API}/orders/{o['code']}/mock-pay", params=t, json={"outcome": "settlement"})).json()
        check("settlement → paid + lunas", od["status"] == "paid" and od["payment_status"] == "lunas", od["status"])
        good = {**bad, "signature_key": mt.signature(bad["order_id"], "200", bad["gross_amount"])}
        await c.post(f"{API}/payments/midtrans/notification", json=good)
        d = await db.orders.find_one({"code": o["code"]})
        check("notifikasi settlement ganda tak double-count", d["paid_amount"] == d["total"], f"{d['paid_amount']}")
        r = await c.post(f"{API}/admin/orders/{o['code']}/refund", json={"reason": "uji"}, headers=adm)
        rd = r.json()
        check("refund penuh → cancelled/refunded + refunded_amount",
              r.status_code == 200 and rd["status"] == "cancelled" and rd.get("refunded_amount") == d["total"], r.text[:150])
        r = await c.post(f"{API}/admin/orders/{o['code']}/refund", json={}, headers=adm)
        check("refund kedua → 400", r.status_code == 400, f"{r.status_code}")

        o2 = (await c.post(f"{API}/orders", json=body(pid, sku, 2))).json()
        t2 = {"t": o2["access_token"]}
        await c.post(f"{API}/orders/{o2['code']}/pay", params=t2)
        s0 = stock(await db.products.find_one({"id": pid}))
        od = (await c.post(f"{API}/orders/{o2['code']}/mock-pay", params=t2, json={"outcome": "deny"})).json()
        check("deny → order tetap pending (bisa coba lagi)", od["status"] == "pending", od["status"])
        tx3 = (await c.post(f"{API}/orders/{o2['code']}/pay", params=t2)).json()
        check("attempt baru → ID -2", tx3["gateway_order_id"].endswith("-2"), tx3.get("gateway_order_id"))
        od = (await c.post(f"{API}/orders/{o2['code']}/mock-pay", params=t2, json={"outcome": "expire"})).json()
        s1 = stock(await db.products.find_one({"id": pid}))
        check("expire → cancelled/expired + stok kembali",
              od["status"] == "cancelled" and od.get("cancel_reason") == "expired" and s1 - s0 == 2, f"{od['status']} {s1 - s0}")
        late = {"order_id": tx3["gateway_order_id"], "status_code": "200", "gross_amount": f"{o2['total']}.00",
                "transaction_status": "settlement", "fraud_status": "accept"}
        late["signature_key"] = mt.signature(late["order_id"], "200", late["gross_amount"])
        await c.post(f"{API}/payments/midtrans/notification", json=late)
        txd = await db.payment_transactions.find_one({"gateway_order_id": tx3["gateway_order_id"]})
        check("bayar setelah batal → ditandai needs_refund", txd.get("needs_refund") is True, str(txd.get("status")))
        r = await c.post(f"{API}/admin/orders/{o2['code']}/refund", json={}, headers=adm)
        txd = await db.payment_transactions.find_one({"gateway_order_id": tx3["gateway_order_id"]})
        check("refund transaksi 'dibayar setelah batal'", r.status_code == 200 and txd["status"] == "refund", r.text[:120])
        rows = (await c.get(f"{API}/admin/payment-transactions", headers=adm)).json()
        check("admin monitor transaksi", any(x["order_code"] == o2["code"] for x in rows), str(len(rows)))
    print(f"\n{sum(RES)}/{len(RES)} PASS")
    sys.exit(0 if all(RES) else 1)


asyncio.run(main())
