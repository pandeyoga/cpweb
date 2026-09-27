"""services/media_core.py — inti Media Manager LOKAL (E20): konstanta, path, mirror GridFS.

SSOT penyimpanan aset media untuk seluruh aplikasi (produk, CMS, kategori, toko,
metode bayar). Desain:

1. **Disk lokal = SSOT.** File asli ditulis ke
   `<MEDIA_ROOT>/originals/<YYYY>/<MM>/<uuid>.<ext>` dan turunan (thumbnail/medium)
   ke `<MEDIA_ROOT>/derived/<uuid>_<size>.webp`.
2. **Mirror GridFS (opsional, default AKTIF).** Biner yang sama dicadangkan ke
   MongoDB lokal (`media_files.*`). Bila file hilang dari disk (container di-rebuild,
   pod berpindah replika, volume belum ter-mount) route `GET /api/media/...`
   MEMULIHKANNYA otomatis dari mirror -> TIDAK ADA broken image lagi.
   Matikan di VPS dengan `MEDIA_DB_MIRROR=false` bila volume sudah persisten.
3. **URL stabil.** URL yang disimpan ke DB selalu RELATIF (`/api/media/...`) dan
   berbasis UUID; rename/ubah alt hanya metadata sehingga link tidak pernah rusak.
4. **Folder bertingkat.** Koleksi `media_folders` (id, name, parent_id, path, depth).
   Hapus folder = isi dipindahkan ke induk (tanpa orphan) atau cascade eksplisit.
5. **Optimasi otomatis.** Pillow: auto-orient EXIF, strip metadata, batas sisi
   terpanjang 2400px, re-encode teroptimasi, turunan WebP 400px & 1000px.
   HEIC/HEIF (foto iPhone) dikonversi ke JPEG. SVG & GIF animasi disimpan apa adanya.

ENV:
  MEDIA_ROOT       (default: <backend>/media)
  MEDIA_MAX_MB     (default: 15)
  MEDIA_DB_MIRROR  (default: true)
"""
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from PIL import Image, ImageOps, ImageSequence  # noqa: F401

# ---- HEIC/HEIF (foto iPhone) -------------------------------------------------
try:  # pragma: no cover - tergantung wheel platform
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover
    HEIF_OK = False

# Guard decompression bomb (gambar raksasa yang menghabiskan RAM).
Image.MAX_IMAGE_PIXELS = 120_000_000

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BACKEND_ROOT / "media")))
ORIGINALS_DIR = MEDIA_ROOT / "originals"
DERIVED_DIR = MEDIA_ROOT / "derived"
for _d in (MEDIA_ROOT, ORIGINALS_DIR, DERIVED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

MAX_MB = int(os.environ.get("MEDIA_MAX_MB", "15") or 15)
MAX_BYTES = MAX_MB * 1024 * 1024
DB_MIRROR = str(os.environ.get("MEDIA_DB_MIRROR", "true")).lower() in ("1", "true", "yes", "on")
MIRROR_MAX_BYTES = 24 * 1024 * 1024  # jangan mirror biner absurd

MAX_DIM = 2400          # sisi terpanjang file asli setelah optimasi
THUMB_DIM = 400         # turunan grid
MEDIUM_DIM = 1000       # turunan preview / kartu produk

# MIME yang diterima -> ekstensi kanonik.
EXT_MAP = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "image/avif": "avif",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
}
ALLOWED_MIME = set(EXT_MAP.keys())
# MIME yang TIDAK diproses Pillow (disimpan apa adanya).
PASSTHROUGH_MIME = {"image/svg+xml"}
# Format Pillow -> (format simpan, ekstensi, mime keluaran)
SAVE_AS = {
    "image/jpeg": ("JPEG", "jpg", "image/jpeg"),
    "image/jpg": ("JPEG", "jpg", "image/jpeg"),
    "image/pjpeg": ("JPEG", "jpg", "image/jpeg"),
    "image/png": ("PNG", "png", "image/png"),
    "image/webp": ("WEBP", "webp", "image/webp"),
    "image/avif": ("AVIF", "avif", "image/avif"),
    "image/bmp": ("PNG", "png", "image/png"),
    "image/tiff": ("JPEG", "jpg", "image/jpeg"),
    "image/heic": ("JPEG", "jpg", "image/jpeg"),
    "image/heif": ("JPEG", "jpg", "image/jpeg"),
}
EXT_TO_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "svg": "image/svg+xml",
    "avif": "image/avif", "heic": "image/heic", "heif": "image/heif",
    "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff",
    "ico": "image/x-icon",
}
LIST_MAX = 200
ROOT_FOLDER = {"id": None, "name": "Semua Media", "parent_id": None, "path": "/", "depth": 0}


class MediaError(ValueError):
    """Kesalahan yang aman ditampilkan ke pengguna (dipetakan ke HTTP 400)."""


# ============================== util ==============================
def _bucket(db):
    return AsyncIOMotorGridFSBucket(db, bucket_name="media_files")


def _slug_name(text: str, fallback: str = "file") -> str:
    """Nama tampilan yang aman (bukan path fisik) — dipakai folder & filename."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9._&+()' -]+", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    return (t[:120] or fallback)


def _rel(path: Path) -> str:
    return str(path.relative_to(MEDIA_ROOT)).replace(os.sep, "/")


def _url_of(rel: str) -> str:
    return f"/api/media/{rel}"


def is_remote_url(url) -> bool:
    """True bila URL absolut http(s) (aset eksternal yang bisa diunduh ke lokal)."""
    return bool(re.match(r"https?://", str(url or "").strip(), re.I))


def safe_rel_path(rel: str) -> Optional[Path]:
    """Cegah path traversal. Kembalikan Path absolut di dalam MEDIA_ROOT atau None."""
    raw = (rel or "").strip().lstrip("/")
    if not raw or "\x00" in raw:
        return None
    candidate = (MEDIA_ROOT / raw).resolve()
    try:
        candidate.relative_to(MEDIA_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def guess_mime_from_name(name: str) -> str:
    ext = (name or "").rsplit(".", 1)[-1].lower()
    return EXT_TO_MIME.get(ext, "application/octet-stream")


def _norm_mime(mime: str, filename: str) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    if m in ALLOWED_MIME:
        return m
    # Browser kadang kirim application/octet-stream -> tebak dari ekstensi.
    guessed = guess_mime_from_name(filename)
    return guessed


# ============================== mirror GridFS ==============================
async def _mirror_put(db, rel: str, data: bytes, mime: str) -> None:
    if not DB_MIRROR or len(data) > MIRROR_MAX_BYTES:
        return
    try:
        bucket = _bucket(db)
        async for old in bucket.find({"filename": rel}):
            try:
                await bucket.delete(old._id)
            except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
                pass
        await bucket.upload_from_stream(rel, data, metadata={"mime": mime, "rel": rel})
    except Exception:
        # Mirror adalah jaring pengaman — kegagalannya tidak boleh menggagalkan upload.
        pass


async def _mirror_get(db, rel: str) -> Optional[bytes]:
    if not DB_MIRROR:
        return None
    try:
        bucket = _bucket(db)
        stream = await bucket.open_download_stream_by_name(rel)
        return await stream.read()
    except Exception:
        return None


async def _mirror_delete(db, rel: str) -> None:
    if not DB_MIRROR:
        return
    try:
        bucket = _bucket(db)
        async for old in bucket.find({"filename": rel}):
            try:
                await bucket.delete(old._id)
            except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
                pass
    except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
        pass


async def resolve_file(db, rel: str):
    """Kembalikan (Path, mime) untuk disajikan. Self-heal dari mirror bila perlu.

    Mengembalikan None bila benar-benar tidak ada.
    """
    fpath = safe_rel_path(rel)
    if fpath is None:
        return None
    mime = guess_mime_from_name(fpath.name)
    if fpath.exists() and fpath.is_file():
        return fpath, mime
    data = await _mirror_get(db, str(Path(rel)).replace(os.sep, "/").lstrip("/"))
    if data is None:
        return None
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, "wb") as f:
            f.write(data)
    except Exception:
        return None
    return fpath, mime


# ============================== indexes ==============================
async def ensure_indexes(db) -> None:
    try:
        await db.media_folders.create_index("id", unique=True)
        await db.media_folders.create_index("parent_id")
        await db.media_folders.create_index("path")
        await db.media_assets.create_index("id", unique=True)
        await db.media_assets.create_index("folder_id")
        await db.media_assets.create_index("uploaded_at")
        await db.media_assets.create_index("checksum")
    except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
        pass


# ============================== FOLDERS ==============================
