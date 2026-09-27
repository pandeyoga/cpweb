# 05 — NAVIGATION MAP (Information Architecture)
## Collector Parfum

> SSOT navigasi. Menu di luar peta ini = **STOP & ASK** (cegah "menu liar").
> Dua surface terpisah: **storefront** (publik/customer) & **admin** (backoffice).

## A. Storefront (publik + customer)
| Path | Halaman | Akses |
|------|---------|-------|
| `/` | Home | publik |
| `/shop` | Katalog + filter/sort | publik |
| `/parfum/:slug` | Product Detail (PDP) | publik |
| `/keranjang` | Cart | publik |
| `/checkout` | Checkout Shopee-style | publik (login opsional V1) |
| `/pesanan-sukses` | Order Success | publik |
| `/wishlist` | Wishlist | publik (sinkron akun bila login) |
| `/tentang` | About | publik |
| `/kontak` | Contact | publik |
| `/akun` | Account (profil, pesanan, alamat) | customer (login) |

Komponen global: AnnouncementBar, SiteHeader, SiteFooter, MobileBottomNav,
CartDrawer, SearchDrawer, MobileMenuDrawer, QuickViewModal.

## B. Admin backoffice (role: admin) — IA v2 (2026-06)
SSOT menu + judul + breadcrumb: `frontend/src/components/admin/adminNav.js`. Grup bisa diciutkan
(tersimpan di localStorage), badge "perlu ditindak" dari `GET /api/admin/nav-counts`.
| Grup | Item | Rute |
|------|------|------|
| Ringkasan | Dashboard | `/admin` |
| Penjualan | Pesanan (badge dibayar+dikemas; detail `/admin/pesanan/:code`), Pembayaran (badge bukti menunggu), Voucher | `/admin/pesanan`, `/admin/pembayaran`, `/admin/voucher` |
| Katalog | Produk (editor `/admin/produk/:id`, `/admin/produk/baru`; Impor/Ekspor = tombol → `/admin/produk/impor`), Kategori, Occasion, Karakter | `/admin/produk`, `/admin/kategori`, `/admin/occasion`, `/admin/karakter` |
| Pelanggan | Pelanggan & Segmen (tab Segmen + Semua Akun), Ulasan Produk (badge menunggu moderasi) | `/admin/pelanggan` (`/admin/crm` → redirect), `/admin/ulasan` |
| Toko & Konten | Konten Situs, Media, Lokasi Toko (+ ulasan Google cabang) | `/admin/konten`, `/admin/media`, `/admin/lokasi` |
| Laporan | Analitik | `/admin/analitik` |
| Sistem | Pengaturan (Toko, Kurir, Pembayaran, Integrasi & SEO), Log Email, Backup & Restore | `/admin/pengaturan`, `/admin/log-email`, `/admin/backup` |

> Non-admin yang membuka `/admin/*` → form masuk admin (bila belum login) atau redirect + toast "Akses ditolak" (bila login sebagai customer).

## C. Aturan
- Tambah menu HANYA lewat konfigurasi navigasi + render shell; jangan tebar route liar.
- Active state jelas, breadcrumb bila > 2 level, empty state mengarahkan aksi.
- 1 konsep = 1 istilah (lihat glosarium koleksi kanonik di 03_DATA_MODEL.md).
