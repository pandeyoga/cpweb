"""services/midtrans.py — klien REST Midtrans Snap (tanpa SDK, httpx). Epic E14.

Mode (dari env, dievaluasi tiap panggilan):
  - live : MIDTRANS_SERVER_KEY terisi → panggil API Midtrans (sandbox/production).
  - mock : key kosong + MIDTRANS_MOCK=true → SIMULASI lokal (token palsu, tanpa jaringan).
  - off  : key kosong & mock mati → pembayaran online nonaktif (503).
Server Key TIDAK PERNAH dikirim ke FE; hanya Client Key yang publik.
"""
import hashlib
import hmac
import os

import httpx

MOCK_SERVER_KEY = "mock-server-key"
_SCHEME = "https"  # host vendor tetap; mode/kunci dari env
_TRUE = ("1", "true", "yes", "on")


class GatewayError(Exception):
    """Kegagalan komunikasi / penolakan dari Midtrans."""


def _env(k):
    return (os.environ.get(k) or "").strip()


def mode():
    if _env("MIDTRANS_SERVER_KEY"):
        return "live"
    return "mock" if _env("MIDTRANS_MOCK").lower() in _TRUE else "off"


def enabled():
    return mode() != "off"


def is_production():
    return _env("MIDTRANS_IS_PRODUCTION").lower() in _TRUE


def _server_key():
    return _env("MIDTRANS_SERVER_KEY") or MOCK_SERVER_KEY


def _snap_base():
    return f"{_SCHEME}://app.midtrans.com" if is_production() else f"{_SCHEME}://app.sandbox.midtrans.com"


def _api_base():
    return f"{_SCHEME}://api.midtrans.com" if is_production() else f"{_SCHEME}://api.sandbox.midtrans.com"


def public_config():
    m = mode()
    return {"enabled": m != "off", "mode": m, "production": is_production(),
            "client_key": _env("MIDTRANS_CLIENT_KEY") or None,
            "snap_js_url": f"{_snap_base()}/snap/snap.js" if m == "live" else None}


def signature(order_id, status_code, gross_amount):
    raw = f"{order_id}{status_code}{gross_amount}{_server_key()}"
    return hashlib.sha512(raw.encode()).hexdigest()


def verify_signature(n):
    expected = signature(n.get("order_id", ""), n.get("status_code", ""), n.get("gross_amount", ""))
    return hmac.compare_digest(expected, str(n.get("signature_key", "")))


async def _call(method, url, json=None):
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.request(method, url, json=json, auth=(_server_key(), ""),
                                headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise GatewayError(f"Midtrans tidak terjangkau: {e}") from e
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        msg = data.get("error_messages") or data.get("status_message") or r.text[:200]
        raise GatewayError(f"Midtrans menolak ({r.status_code}): {msg}")
    return data


async def create_snap(payload):
    """→ {token, redirect_url}. Mock: token lokal tanpa jaringan."""
    if mode() == "mock":
        return {"token": f"mock-{payload['transaction_details']['order_id']}", "redirect_url": None}
    return await _call("POST", f"{_snap_base()}/snap/v1/transactions", payload)


async def get_status(gateway_order_id):
    """Status transaksi otoritatif dari Midtrans (None di mode mock)."""
    if mode() != "live":
        return None
    return await _call("GET", f"{_api_base()}/v2/{gateway_order_id}/status")


async def refund(gateway_order_id, amount, reason, refund_key):
    if mode() == "mock":
        return {"status_code": "200", "transaction_status": "refund", "refund_amount": amount}
    return await _call("POST", f"{_api_base()}/v2/{gateway_order_id}/refund",
                       {"refund_key": refund_key, "amount": int(amount), "reason": reason[:250]})
