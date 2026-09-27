"""services/media_ingest.py — Masuknya aset: unggah, unduh URL, registrasi eksternal, ganti berkas. (dipecah dari services/media.py; API publik via services.media)."""
import hashlib
import os
import re
from typing import Optional

from core_utils import new_id, now_iso
from services.audit import log_action
from services.media_core import (
    ALLOWED_MIME,
    DERIVED_DIR,
    EXT_TO_MIME,
    HEIF_OK,
    MAX_BYTES,
    MAX_MB,
    MEDIUM_DIM,
    THUMB_DIM,
    MediaError,
    _mirror_put,
    _norm_mime,
    _rel,
    _slug_name,
    _url_of,
    guess_mime_from_name,
    safe_rel_path,
)
from services.media_folders import _folder_or_error
from services.media_images import _write_files, process_image, public_asset


async def save_upload(db, file_bytes: bytes, filename: str, mime: str, actor_id: str,
                      folder_id: Optional[str] = None, alt: Optional[str] = None,
                      title: Optional[str] = None, dedupe: bool = True):
    """Simpan satu berkas upload ke disk lokal (+ mirror) & catat metadata."""
    if not file_bytes:
        raise MediaError("Berkas kosong")
    if len(file_bytes) > MAX_BYTES:
        raise MediaError(f"Ukuran berkas melebihi batas {MAX_MB} MB")
    norm = _norm_mime(mime, filename)
    if norm not in ALLOWED_MIME:
        raise MediaError(
            f"Tipe berkas '{mime or norm}' tidak didukung. "
            "Gunakan JPG, PNG, WebP, GIF, SVG, AVIF, atau HEIC."
        )
    if norm in ("image/heic", "image/heif") and not HEIF_OK:
        raise MediaError("Dukungan HEIC belum aktif di server")
    await _folder_or_error(db, folder_id)

    checksum = hashlib.sha256(file_bytes).hexdigest()
    if dedupe:
        existing = await db.media_assets.find_one({"checksum": checksum}, {"_id": 0})
        if existing and existing.get("stored_path"):
            # Berkas identik sudah ada -> pakai ulang (hemat disk, cegah duplikat).
            patch = {"updated_at": now_iso()}
            if folder_id and existing.get("folder_id") != folder_id:
                patch["folder_id"] = folder_id
            # Alt/title yang DIKIRIM EKSPLISIT selalu menang (harapan pengguna).
            if alt:
                patch["alt"] = str(alt)[:300]
            if title:
                patch["title"] = str(title)[:200]
            await db.media_assets.update_one({"id": existing["id"]}, {"$set": patch})
            existing.update(patch)
            out = public_asset(existing)
            out["deduped"] = True
            return out

    proc = process_image(file_bytes, norm)
    base_uuid = new_id("f").replace("f_", "")
    stored_rel, thumb_rel, medium_rel = await _write_files(db, base_uuid, proc)

    display = _slug_name(filename or "", "") or f"gambar.{proc['ext']}"
    doc = {
        "id": new_id("med"),
        "folder_id": folder_id or None,
        "filename": display,
        "original_name": (filename or "")[:200],
        "stored_path": stored_rel,
        "url": _url_of(stored_rel),
        "thumb_url": _url_of(thumb_rel) if thumb_rel else _url_of(stored_rel),
        "medium_url": _url_of(medium_rel) if medium_rel else _url_of(stored_rel),
        "kind": "image",
        "mime": proc["mime"],
        "size": len(proc["data"]),
        "width": proc["width"],
        "height": proc["height"],
        "alt": (alt or "")[:300] or None,
        "title": (title or "")[:200] or None,
        "tags": [],
        "checksum": checksum,
        "source": "upload",
        "animated": proc["animated"],
        "uploaded_by": actor_id,
        "uploaded_at": now_iso(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.media_assets.insert_one(dict(doc))
    await log_action(actor_id, "create", "media_assets", doc["id"],
                     {"filename": display, "size": doc["size"]})
    doc.pop("_id", None)
    return public_asset(doc)


async def ingest_url(db, url: str, actor_id: str, folder_id: Optional[str] = None,
                     alt: Optional[str] = None, title: Optional[str] = None):
    """Unduh gambar dari URL eksternal lalu simpan LOKAL (anti broken image)."""
    from services.net_guard import UnsafeUrl, fetch_public

    raw = (url or "").strip()
    if not raw:
        raise MediaError("URL wajib diisi")
    if raw.startswith("/api/media/"):
        raise MediaError("URL ini sudah berasal dari media lokal")
    if not re.match(r"^https?://", raw, re.I):
        raise MediaError("URL harus dimulai dengan http:// atau https://")
    try:
        status, ctype, data = await fetch_public(raw, MAX_BYTES, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CollectorParfumBot/1.0)",
            "Accept": "image/*,*/*;q=0.8",
        })
    except UnsafeUrl as e:
        raise MediaError(str(e))
    except ValueError:
        raise MediaError(f"Gambar dari URL melebihi batas {MAX_MB} MB")
    except Exception as e:
        raise MediaError(f"Gagal mengunduh gambar: {type(e).__name__}")
    if status >= 400:
        raise MediaError(f"Sumber menolak permintaan (HTTP {status})")
    if not data:
        raise MediaError("Sumber tidak mengembalikan data gambar")
    name = raw.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "gambar"
    if ctype not in ALLOWED_MIME:
        ctype = guess_mime_from_name(name)
    if ctype not in ALLOWED_MIME:
        raise MediaError("URL bukan berkas gambar yang didukung")
    out = await save_upload(db, data, name, ctype, actor_id, folder_id=folder_id,
                            alt=alt, title=title)
    await db.media_assets.update_one({"id": out["id"]},
                                     {"$set": {"source": "url", "source_url": raw[:1200]}})
    out["source"] = "url"
    return out


async def register_external(db, actor_id: str, url: str, alt=None, kind="image",
                           width=None, height=None, folder_id=None):
    """Catat URL eksternal TANPA mengunduh (kompatibilitas legacy POST /admin/media)."""
    raw = (url or "").strip()[:1200]
    if not raw:
        raise MediaError("URL wajib diisi")
    doc = {
        "id": new_id("med"),
        "folder_id": folder_id or None,
        "filename": _slug_name(raw.split("?")[0].rsplit("/", 1)[-1], "gambar"),
        "url": raw,
        "thumb_url": raw,
        "medium_url": raw,
        "kind": kind or "image",
        "mime": guess_mime_from_name(raw),
        "size": 0,
        "width": int(width) if width else None,
        "height": int(height) if height else None,
        "alt": (str(alt)[:300] if alt else None),
        "title": None,
        "tags": [],
        "source": "external",
        "owner_admin_id": actor_id,
        "uploaded_by": actor_id,
        "uploaded_at": now_iso(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.media_assets.insert_one(dict(doc))
    await log_action(actor_id, "create", "media_assets", doc["id"], {"external": True})
    doc.pop("_id", None)
    return public_asset(doc)


def _atomic_write(path, data: bytes):
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


async def replace_asset(db, actor_id: str, aid: str, file_bytes: bytes, filename: str, mime: str):
    """Ganti biner berkas TANPA mengubah URL (link di produk/CMS tetap hidup)."""
    doc = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    if not doc:
        return None
    stored = doc.get("stored_path")
    if not stored:
        raise MediaError("Aset ini bukan berkas lokal sehingga tidak bisa diganti")
    if len(file_bytes) > MAX_BYTES:
        raise MediaError(f"Ukuran berkas melebihi batas {MAX_MB} MB")
    norm = _norm_mime(mime, filename)
    if norm not in ALLOWED_MIME:
        raise MediaError("Tipe berkas tidak didukung")
    target_ext = stored.rsplit(".", 1)[-1].lower()
    target_mime = EXT_TO_MIME.get(target_ext, doc.get("mime") or "image/jpeg")
    if target_mime == "image/svg+xml" and norm != "image/svg+xml":
        raise MediaError("Aset SVG hanya bisa diganti dengan berkas SVG")
    if norm == "image/svg+xml" and target_mime != "image/svg+xml":
        raise MediaError("Berkas SVG tidak bisa mengganti aset raster")
    # Paksa keluaran ke format yang sama agar URL (ekstensi) tidak berubah.
    proc = process_image(file_bytes, norm)
    if proc["ext"] != target_ext and target_mime != "image/svg+xml":
        proc = process_image(file_bytes, target_mime)
        if proc["ext"] != target_ext:
            raise MediaError("Format tidak kompatibel untuk penggantian berkas")
    fpath = safe_rel_path(stored)
    if fpath is None:
        raise MediaError("Lokasi berkas tidak valid")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    # Butir 16: mirror dulu (sumber pemulihan), lalu file ditulis ATOMIK (tmp + os.replace) —
    # pembeli tak pernah menerima berkas setengah tertulis; gagal di tengah → berkas lama utuh.
    await _mirror_put(db, stored, proc["data"], proc["mime"])
    _atomic_write(fpath, proc["data"])
    base_uuid = fpath.stem
    for key, dim in (("thumb", THUMB_DIM), ("medium", MEDIUM_DIM)):
        if proc.get(key):
            dp = DERIVED_DIR / f"{base_uuid}_{dim}.webp"
            await _mirror_put(db, _rel(dp), proc[key], "image/webp")
            _atomic_write(dp, proc[key])
    upd = {
        "size": len(proc["data"]), "width": proc["width"], "height": proc["height"],
        "checksum": hashlib.sha256(file_bytes).hexdigest(),
        "original_name": (filename or "")[:200],
        "updated_at": now_iso(),
        "cache_bust": now_iso(),
    }
    await db.media_assets.update_one({"id": aid}, {"$set": upd})
    await log_action(actor_id, "update", "media_assets", aid, {"replaced": True})
    fresh = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    return public_asset(fresh)
