"""services/backup_auto.py — backup harian otomatis (cron `/api/cron/daily-backup`).

Semua koleksi yang boleh di-backup disimpan sebagai backup server (tampil di Admin › Backup),
lalu backup otomatis lama dipangkas agar disk tidak penuh (backup manual TIDAK disentuh).
"""
from services import backup as backup_svc

AUTO_ACTOR = "system-cron"
KEEP_AUTO = 14


async def daily_backup(db):
    names = [c["name"] for c in await backup_svc.list_collections_info(db)]
    doc = await backup_svc.create_server_backup(db, names, AUTO_ACTOR, note="Backup otomatis harian")
    old = await db.backups.find({"created_by": AUTO_ACTOR}, {"id": 1}).sort(
        [("created_at", -1)]).skip(KEEP_AUTO).to_list(1000)
    for o in old:
        await backup_svc.delete_server_backup(db, o["id"])
    return {"backup_id": doc["id"], "collections": len(names), "size": doc["size"], "pruned": len(old)}
