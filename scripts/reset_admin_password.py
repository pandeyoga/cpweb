#!/usr/bin/env python3
"""reset_admin_password.py — set ulang password akun (default admin) & keluarkan semua sesinya.

Usage (di VPS, dari folder aplikasi):
  sudo -u collector backend/venv/bin/python scripts/reset_admin_password.py              # password acak
  sudo -u collector backend/venv/bin/python scripts/reset_admin_password.py --password 'RahasiaKuat#2026'
  Opsi: --email admin@collectorparfum.id
"""
import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core_utils import hash_password  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="admin@collectorparfum.id")
    ap.add_argument("--password", default="")
    a = ap.parse_args()
    pw = a.password or secrets.token_urlsafe(12)
    if len(pw) < 10:
        raise SystemExit("Password minimal 10 karakter.")
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": a.email.lower()})
    if not user:
        raise SystemExit(f"Akun {a.email} tidak ditemukan di database {os.environ['DB_NAME']}.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(pw), "status": "active"}})
    await db.sessions.delete_many({"user_id": user["id"]})
    await db.login_attempts.delete_many({})
    print(f"Password {a.email} (role {user.get('role')}) di-set ulang.\nPassword baru: {pw}\nSegera simpan & ganti setelah login.")


asyncio.run(main())
