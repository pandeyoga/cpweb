"""server.py — entrypoint FastAPI Collector Parfum.

Arsitektur: routers (THIN I/O) -> services (logika) -> Motor/MongoDB.
Semua route berada di bawah prefix '/api' (Kubernetes ingress).
JANGAN mengubah MONGO_URL / DB_NAME / CORS_ORIGINS di .env dari sini.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from db import close, get_db  # noqa: E402
from routers import account as account_router  # noqa: E402
from routers import admin as admin_router  # noqa: E402
from routers import public_forms as public_forms_router  # noqa: E402
from routers import admin_categories as admin_categories_router  # noqa: E402
from routers import admin_facets as admin_facets_router  # noqa: E402
from routers import admin_brands as admin_brands_router  # noqa: E402
from routers import admin_config as admin_config_router  # noqa: E402
from routers import admin_orders as admin_orders_router  # noqa: E402
from routers import admin_products as admin_products_router  # noqa: E402
from routers import admin_product_io as admin_product_io_router  # noqa: E402
from routers import admin_reviews as admin_reviews_router  # noqa: E402
from routers import admin_vouchers as admin_vouchers_router  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import cart as cart_router  # noqa: E402
from routers import catalog as catalog_router  # noqa: E402
from routers import config as config_router  # noqa: E402
from routers import health as health_router  # noqa: E402
from routers import orders as orders_router  # noqa: E402
from routers import payments as payments_router  # noqa: E402
from routers import admin_payments as admin_payments_router  # noqa: E402
from routers import analytics as analytics_router  # noqa: E402
from routers import admin_analytics as admin_analytics_router  # noqa: E402
from routers import content as content_router  # noqa: E402
from routers import admin_content as admin_content_router  # noqa: E402
from routers import admin_media as admin_media_router  # noqa: E402
from routers import media_public as media_public_router  # noqa: E402
from routers import vouchers as vouchers_router  # noqa: E402
from routers import stores as stores_router  # noqa: E402
from routers import admin_stores as admin_stores_router  # noqa: E402
from routers import admin_backup as admin_backup_router  # noqa: E402
from routers import cron as cron_router  # noqa: E402
from routers import gateway as gateway_router  # noqa: E402
from routers import admin_gateway as admin_gateway_router  # noqa: E402
from services import gateway as gateway_svc  # noqa: E402
from services import media as media_svc  # noqa: E402
from services.order_helpers import backfill_guest_tokens  # noqa: E402
from services import product_io_session as import_sessions_svc  # noqa: E402
from services import login_guard  # noqa: E402
from services import startup as startup_svc  # noqa: E402
from services import account as account_svc  # noqa: E402
from services import reconcile as reconcile_svc  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector_parfum")

app = FastAPI(title="Collector Parfum API", version="1.0.0")

# Router utama berprefix /api. Router domain di-include ke sini.
api_router = APIRouter(prefix="/api")

# Registry router — fase berikutnya menambah router domain di sini (products, orders, ...).
ROUTERS = [
    health_router.router,
    auth_router.router,
    # Penyaji berkas media lokal (self-healing) — PUBLIK, harus sebelum router lain
    # yang bisa menangkap path /media/*.
    media_public_router.router,
    catalog_router.router,
    vouchers_router.router,
    config_router.router,
    orders_router.router,
    cart_router.router,
    account_router.router,
    payments_router.router,
    # Growth & Analytics (Epic E7) — event first-party (publik) + sitemap.
    analytics_router.router,
    # Storefront CMS (Epic E9) — konten publik.
    content_router.router,
    # Lokasi toko offline + Google Reviews (publik).
    stores_router.router,
    # Admin backoffice (Epic E5) — semua dijaga require_role('admin').
    # Media Manager (E20) didaftarkan LEBIH DULU agar path spesifik
    # /admin/media/folders|assets|upload tidak tertelan route legacy.
    admin_media_router.router,
    admin_media_router.uploads_router,
    admin_router.router,
    admin_products_router.router,
    admin_product_io_router.router,
    admin_categories_router.router,
    admin_facets_router.router,
    admin_brands_router.router,
    admin_vouchers_router.router,
    admin_orders_router.router,
    admin_reviews_router.router,
    admin_config_router.router,
    admin_payments_router.router,
    admin_analytics_router.router,
    admin_content_router.router,
    admin_stores_router.router,
    # Backup & Restore data (admin-only).
    admin_backup_router.router,
    # Cron terjadwal (Bearer WEBHOOK_CRON_SECRET) — auto-batal order lewat batas bayar.
    cron_router.router,
    # Pembayaran online Midtrans Snap (E14) — publik/owner + admin (require_role).
    gateway_router.router,
    admin_gateway_router.router,
    public_forms_router.router,
]
for r in ROUTERS:
    api_router.include_router(r)

app.include_router(api_router)

# Berkas media dilayani oleh `routers/media_public.py` (GET /api/media/{path}).
# StaticFiles lama DIHAPUS agar bisa self-heal dari mirror MongoDB saat berkas
# hilang dari disk (penyebab broken image setelah rebuild/redeploy).

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Did-You-Mean"],  # agar FE bisa membaca total untuk paginasi
)


@app.on_event("startup")
async def _startup():
    """Index + migrasi ringan. Tiap langkah terisolasi; status di GET /api/health (butir 12)."""
    db = get_db()

    async def _cod_off():
        await db.payment_methods.update_many({"group": "cod"}, {"$set": {"active": False}})  # E14: COD dihapus

    await startup_svc.run(db, [
        ("backfill guest tokens", lambda: backfill_guest_tokens(db)),
        ("sync payment methods", lambda: gateway_svc.sync_payment_methods(db)),
        ("disable cod", _cod_off),
        ("ledger flags migration", lambda: reconcile_svc.migrate_flags(db)),
        ("addresses single default", lambda: account_svc.ensure_default_index(db)),
        ("media indexes", lambda: media_svc.ensure_indexes(db)),
        ("import session indexes", lambda: import_sessions_svc.ensure_indexes(db)),
        ("login guard indexes", lambda: login_guard.ensure_indexes(db)),
        ("media legacy migration", lambda: media_svc.migrate_legacy(db)),
        ("media default folders", lambda: media_svc.ensure_default_folders(db)),
        ("day/night migration", lambda: startup_svc.migrate_day_night(db)),
    ])


@app.on_event("shutdown")
async def _shutdown():
    close()
