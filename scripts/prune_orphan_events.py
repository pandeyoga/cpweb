"""Hapus event analytics `purchase` yang menunjuk order yang sudah tidak ada (INV-G1).

Aplikasi tidak pernah menghapus order; orphan hanya muncul dari skrip uji yang membersihkan
order uji (event purchase dicatat server saat paid, SALES-14). Idempoten.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    codes = set(await db.orders.distinct("code"))
    orphan = [e["id"] async for e in db.analytics_events.find(
        {"type": "purchase", "order_code": {"$nin": list(codes)}}, {"id": 1})]
    if orphan:
        await db.analytics_events.delete_many({"id": {"$in": orphan}})
    print(f"prune_orphan_events: {len(orphan)} event purchase orphan dihapus")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
