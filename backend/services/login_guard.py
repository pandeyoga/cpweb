"""services/login_guard.py — proteksi brute force login.

- 5 gagal / 15 menit per ip+email, plus 20 gagal / 15 menit per email dari IP mana pun (anti rotasi IP).
- IP klien diambil dari X-Forwarded-For dihitung dari KANAN sebanyak TRUSTED_PROXY_HOPS (proxy tepercaya);
  entri paling kiri bisa dipalsukan klien, jadi tak pernah dipakai begitu saja.
"""
import os
import time
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

MAX_FAILS = 5
MAX_FAILS_EMAIL = 20
LOCK_MINUTES = 15


def client_ip(request) -> str:
    hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "1"))
    chain = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if chain and hops > 0:
        return chain[max(0, len(chain) - hops)]
    return request.client.host if request.client else "unknown"


def identifier(request, email: str) -> str:
    return f"{client_ip(request)}:{email}"


def _email_key(ident: str) -> str:
    return "*:" + ident.split(":", 1)[-1]


async def seconds_locked(db, ident: str) -> int:
    now = time.time()
    docs = await db.login_attempts.find({"identifier": {"$in": [ident, _email_key(ident)]}},
                                        {"locked_until": 1}).to_list(2)
    left = max([float(d.get("locked_until") or 0) for d in docs] + [0]) - now
    return int(left) + 1 if left > 0 else 0


async def _bump(db, key: str, limit: int) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)
    doc = await db.login_attempts.find_one_and_update(
        {"identifier": key},
        {"$inc": {"count": 1}, "$set": {"expires_at": expires}},
        upsert=True, return_document=ReturnDocument.AFTER)
    if doc.get("count", 0) >= limit:
        await db.login_attempts.update_one(
            {"identifier": key},
            {"$set": {"count": 0, "locked_until": time.time() + LOCK_MINUTES * 60}})


async def record_failure(db, ident: str) -> None:
    await _bump(db, ident, MAX_FAILS)
    await _bump(db, _email_key(ident), MAX_FAILS_EMAIL)


async def clear(db, ident: str) -> None:
    await db.login_attempts.delete_many({"identifier": {"$in": [ident, _email_key(ident)]}})


async def ensure_indexes(db) -> None:
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
