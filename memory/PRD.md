# PRD — Collector Parfum (FARM Stack)

> Bahasa user: **Indonesia**. Detail arsitektur & aturan kritis ada di `memory/HANDOFF.md`.

## Problem statement asli (sesi 2026-09-21)
Lanjutkan development repo `github.com/pandekomangyogaswastika-dot/cpweb`. Aplikasi sudah
di-deploy ke VPS Hostinger (Ubuntu 24.04, IP 148.230.102.29, folder
`/home/collector/collector-parfum`, backend port 8003) tanpa domain/SSL. Pasang domain
**collectorparfum.com** + HTTPS, dengan panduan memasukkan domain.

Pilihan user: hanya `collectorparfum.com` (www opsional), record email di DNS fastcloud.id
(mail/smtp/pop/MX/SPF → 123.253.29.4) DIBIARKAN, siapkan config Nginx + Certbot + CORS di repo.

## Arsitektur
FastAPI (`backend/server.py`, routers/, services/) + React CRA (frontend/) + MongoDB.
Deploy VPS: `deploy.sh` idempoten (Supervisor `collector-parfum-backend` :8003, Nginx server
block `collector-parfum`, Certbot webroot), dokumentasi `DEPLOYMENT_VPS.md`.

## Yang dikerjakan
- **s.d. 2026-08-04**: E1–E7, E9–E13 selesai (lihat HANDOFF.md). Deploy IP-only ke VPS.
- **2026-09-26 — CMS lanjutan (E14)**:
  - Audit: semua section CMS lama berfungsi; `category_section` mati (tidak dirender) → dihapus.
    Halaman yang belum bisa diedit (Toko, Lokasi, Voucher, heading "Kunjungi Kami" di Kontak,
    SEO global) kini punya section CMS: `shop_page`, `locations_page`, `voucher_page`,
    field tambahan `contact`, `seo` (site_name, judul/deskripsi beranda, default description, OG image).
  - Fitur baru: `home_layout` (urutan drag & tampil/sembunyikan 15 section Beranda, UI baris
    ringkas), `gallery` (galeri foto multi-pilih dari Media Manager, layout masonry/grid/strip,
    caption + tautan, lightbox), tipe field backend `toggle` / `select` / `gallery` (validasi coerce).
  - Admin CMS: preview iframe berpindah ke halaman yang relevan (/shop, /lokasi, /voucher, /kontak,
    /tentang), indikator "sudah diedit" akurat (schema kini mengirim `default`), hint per section.
  - Testing agent iterasi 44: LULUS 100% (backend 6/6, semua alur frontend).
- **2026-09-21 (sesi ini)** — domain + SSL:
  - `deploy.sh`: cek DNS sebelum Certbot (exit 1 bila A record belum ke IP VPS);
    `INCLUDE_WWW=auto|yes|no` (www ikut hanya bila DNS-nya sudah ke VPS); CORS otomatis
    (https/http domain, www bila ada, IP); Nginx ditulis via fungsi `write_nginx_conf`
    (HTTP + ACME webroot → setelah sertifikat: 443 TLS1.2/1.3 http2 HSTS, 80 → 301 ke
    https://domain); `certbot certonly --webroot` + `certbot.timer`; pilihan disimpan di
    `/etc/collector-parfum.deploy.conf` agar `sudo bash deploy.sh` berikutnya tetap HTTPS.
  - `scripts/vps_diag.sh` (diagnosa read-only VPS).
  - `DEPLOYMENT_VPS.md` §5 ditulis ulang: tabel DNS fastcloud.id, firewall Hostinger,
    perintah deploy, verifikasi, opsi, troubleshooting SSL. README diperbarui.
  - Testing agent iterasi 43: LULUS (logika deploy.sh skenario a–e, render nginx `nginx -t`,
    health, login admin, smoke frontend).
  - Belum diverifikasi di VPS asli (butuh user mengubah DNS lalu menjalankan skrip).

## Backlog
- P0: user ubah A record `@` di fastcloud.id → 148.230.102.29, lalu jalankan
  `sudo DOMAIN=collectorparfum.com SETUP_SSL=yes bash deploy.sh` di VPS; ganti password admin.
- P1: E8 Hardening (forensics, N+1, aksesibilitas, release readiness).
- P2: redirect www (bila DNS www diarahkan), backup harian otomatis (mongodump cron).


## 2026-09-26 — E14: Audit alur penjualan + PLAN Midtrans
- FIXED BUG-SALES-01..05 (IDOR order tamu → access_token; cancel paralel double-restore stok; paid manual tanpa bayar; overpaid; pelanggan batal order lunas). Regresi: scripts/repro_sales_flow.py 6/6, backend/tests/test_sales_flow.py 11/11, testing agent iteration_45 100%.
- PLAN Midtrans Snap (menggantikan transfer manual + bukti) + backlog SALES-06..21 → /app/plan.md (bagian atas).
- Next: user menyiapkan key Sandbox Midtrans; putuskan COD tetap/tidak; lalu Fase 1 (prasyarat P0) → Fase 2-3 (Midtrans).

## 2026-09-26 — E14 Fase 1 (prasyarat Midtrans) SELESAI
- Auto-batal order lewat batas bayar 24 jam (cron `/api/cron/expire-orders`), kuota voucher kembali saat batal, idempotency checkout, email pembeli wajib (tamu), halaman sukses status-aware + countdown, COD dihapus, ambang gratis ongkir aktif, gate.sh hijau (refactor media).
- Env baru backend: `PAYMENT_DEADLINE_HOURS=24`, `WEBHOOK_CRON_SECRET` (deploy.sh membuat otomatis di VPS).
- Next: key Midtrans Sandbox → Fase 2 (backend Snap + webhook) & Fase 3 (FE).

## 2026-09-26 — E14 Fase 2–4 Midtrans Snap SIAP (MODE SIMULASI)
- Pembayaran online Midtrans (Snap) lengkap: /pay, webhook bertanda-tangan, status sync, refund, monitor admin, tombol Bayar Sekarang, dialog simulasi.
- Aktif otomatis saat MIDTRANS_SERVER_KEY/CLIENT_KEY diisi (MIDTRANS_MOCK=false). Transfer manual dinonaktifkan saat gateway aktif.
- Regresi: scripts/test_gateway_midtrans.py 22/22.

## 2026-06 — Fix tes flaky BUG-SALES-02 (pembatalan paralel)
- Akar masalah: isolasi tes, BUKAN backend. xdist `--dist loadscope` menjalankan kelas lain paralel pada varian yang sama → selisih stok tercemar. Backend `transition_order` sudah CAS (`status == frm`) → restore stok 1x.
- Fix: fixture `isolated_variant` (produk klon sekali-pakai, dihapus setelah tes) di `backend/tests/test_sales_flow.py`. 4x run paralel: 10 passed, 1 skipped (tes COD — COD sudah dihapus, disengaja).
- Midtrans masih MOCK; menunggu key Sandbox dari user.

## 2026-06 — E15 Email transaksional + Status Bayar Otomatis
- Email Konfirmasi Bayar: `services/notify.py` → dipanggil `transition_order` saat → paid (Midtrans ATAU verifikasi admin), sekali per order (`orders.emails_sent` CAS).
- Pengingat Batas Bayar: cron `/api/cron/payment-reminders` (15 mnt) slot 12 jam & 2 jam, idempoten.
- Status Bayar Otomatis: webhook sudah ada + cron cadangan `/api/cron/sync-payments` (10 mnt) menarik status Midtrans pending.
- `services/mailer.py` SMTP (465 SSL / 587 STARTTLS) mode live/mock/off; log `email_logs`; template `services/email_templates.py`.
- Admin /admin/pembayaran: kartu "Email ke Pembeli" (pratinjau, kirim ulang). API: GET/POST /api/admin/email-logs[/{id}[/resend]].
- Env baru: PUBLIC_SITE_URL, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_FROM_NAME, EMAIL_MOCK. deploy.sh menyimpan nilai SMTP + memasang 2 cron.d baru.
- EMAIL & MIDTRANS masih MOCK. Testing agent iteration_47: 100%.
- Backlog: user memberi SMTP fastcloud.id (host/port/username/password) + key Midtrans Sandbox.

## 2026-06 (sesi ini) — Penutupan backlog: SALES-11/12/18/19/20/21 + E8 Hardening + Backup harian
- Repo di-restore dari github.com/pandeyoga/cpweb ke /app (env preview dipertahankan). Env backend baru di preview:
  PAYMENT_DEADLINE_HOURS, WEBHOOK_CRON_SECRET, PUBLIC_SITE_URL, MIDTRANS_MOCK=true, EMAIL_MOCK=true, SMTP_FROM_EMAIL/NAME.
- **SALES-11** voucher ber-`per_user_limit` wajib login (validate & checkout). **SALES-12** validate memakai user dari sesi saja.
- **SALES-18** admin order API mengirim `allowed_transitions`; FE tidak lagi menduplikasi LEGAL_TRANSITIONS.
- **SALES-19** startup mem-backfill `access_token` order tamu lama. **SALES-20** dashboard & CRM via agregasi Mongo
  (LTV = dibayar − direfund). **SALES-21** docs 04/06/E6 diperbarui.
- **E8**: URL kurir → `external_urls.py` (gate compliance hijau), audit koreksi resi simpan dari→ke, `fa_static` WARN 0,
  aria-label input (kontak, newsletter, login/daftar), orphan data tes (event purchase / order produk klon) dibersihkan di sumbernya.
- **Backup harian otomatis**: `POST /api/cron/daily-backup` (02.00 WIB, simpan 14 terakhir) — `.emergent/crons.yml` + cron.d di `deploy.sh`.
- Bukti: `bash scripts/gate.sh` HIJAU, `run_forensics.sh` HIGH 0 / VULN 0 / INTEGRITY OK, pytest 38 passed, testing agent iteration_49 100%.

## Backlog tersisa (butuh tindakan user)
- P0: key Midtrans Sandbox → Fase 5 go-live; SMTP fastcloud.id (host/port/username/password) → EMAIL_MOCK=false.
- P0: A record domain → VPS lalu `sudo DOMAIN=collectorparfum.com SETUP_SSL=yes bash deploy.sh`; ganti password admin.
- P2: redirect www (bila DNS www diarahkan) — sudah didukung `INCLUDE_WWW=auto`.

## 2026-06 — IA Backoffice v2
- Menu admin disusun ulang (SSOT `frontend/src/components/admin/adminNav.js`): Ringkasan · Penjualan (Pesanan, Pembayaran, Voucher) ·
  Katalog (Produk, Kategori, Occasion, Karakter; Impor/Ekspor = tombol di Produk) · Pelanggan (Pelanggan & Segmen, Ulasan Produk) ·
  Toko & Konten (Konten Situs, Media, Lokasi Toko) · Laporan (Analitik) · Sistem (Pengaturan, Log Email, Backup & Restore).
- Grup sidebar bisa diciutkan (localStorage), badge "perlu ditindak" dari `GET /api/admin/nav-counts`, breadcrumb + judul topbar lengkap.
- Halaman baru `/admin/pelanggan` (tab Segmen + Semua Akun; `/admin/crm` redirect) & `/admin/log-email` (dipindah dari Pembayaran).
  Pengaturan kini 4 tab (Toko, Kurir, Pembayaran, Integrasi & SEO). Docs `05_NAVIGATION_MAP.md` diperbarui.
- gate.sh HIJAU, testing agent iteration_50 100%.

## 2026-06 — Skrip ganti katalog dari Excel (VPS)
- `imports/catalog/produk.xlsx` (versi diperbaiki dari file user: 5 characters/deskripsi rusak dikoreksi — perlu cek manual,
  SKU 9.639 varian dibuat unik, boolean dinormalisasi) + `imports/catalog/harga_matrix.csv` (36 kombinasi tier×ukuran×tipe, masih kosong).
- `scripts/replace_catalog.py`: validasi ketat → `--apply` backup otomatis → replace per slug (id lama dipertahankan) → produk lama
  dihapus (yang pernah dipesan diarsipkan) → karakter baru dibuat, occasion selain Date Night disembunyikan. Produk tanpa harga
  lengkap = archived. Pengaman: apply ditolak bila toko akan kosong (kecuali `--allow-empty-store`). Panduan: `imports/catalog/README.md`.
- Diuji di DB terpisah (catalog_test): 1.071 produk, apply 2x idempoten, API katalog & detail membaca data baru. DB preview TIDAK diubah.
- Belum dikerjakan dari PROMPT_PENYESUAIAN_CPWEB.md (23 butir): filter tier/Date Night/Tipe di toko, field tier di editor admin,
  hapus concentration dari UI, dan butir pembayaran/keamanan/robustness lainnya → backlog bertahap.

## 2026-06 — Katalog v2 (butir PROMPT 1,2,5,7,9,10,19,22) — iteration_51 100%
- tier/date_night/tipe di API+toko+editor, concentration/ingredients dihapus, quick-add hanya varian ber-stok, kontak & newsletter tersimpan,
  paginasi+cari order admin, total Rp0 ditolak, intro Lokasi tersimpan (`stores_intro`), rentang analitik, seed tak menimpa password.

## 2026-06 — E17 Hardening (sesi ini) — iteration_52 100% (pytest 59 passed/1 skip, gate.sh HIJAU)
- Repo di-restore ulang dari github.com/pandeyoga/cpweb (env preview dipertahankan + env backend E14/E15 diisi ulang).
- Konsistensi config admin: `AdminSettingsInput`/`AdminStoreConfigInput` = `extra=forbid` (field salah nama → 422, bukan hilang diam-diam);
  store-config PUT = `store_rating_avg`/`store_rating_count`/`stores_intro` (sama dengan GET); `cod_fee` dihapus.
- Bug data-loss diperbaiki: edit voucher tak lagi menghapus scope/periode/campaign; edit kategori tak menghapus seo (update parsial).
- Butir 8: `POST /api/auth/logout` mencabut sesi server; brute-force login 5x/15 mnt per ip+email (429); unduh media anti-SSRF
  (`services/net_guard.py`, cek tiap redirect + batas stream); SVG disajikan dengan CSP sandbox + nosniff.
- Butir 13: `Idempotency-Key` terikat sidik isi checkout (beda isi → 409 `idempotency_conflict`; FE buat key baru saat keranjang berubah).
- Butir 20: wishlist & keranjang ambil produk via `GET /api/products?ids=`; pencarian drawer query server + "Lihat semua" → `/shop?q=`.
- Butir 5/19: janji COD dihapus (keranjang, detail produk, FAQ); `data/products.js` hanya FAQ. Copy ukuran → 35/60/100 ml
  (default CMS; di VPS ubah via Admin › Konten Situs bila konten lama sudah tersimpan).
- Tes baru: `backend/tests/test_hardening_e17.py` (14). Dok: `docs/04_API_CONTRACT.md` §E17.

## Backlog PROMPT_PENYESUAIAN (status per 2026-06 E19: SEMUA butir P1/P2 di bawah SELESAI)
- P1: 3 (rekonsiliasi Midtrans/refund, /pay paralel), 4 & 11 (kompensasi stok/voucher resumable, shipped+resi atomik), 12 (proof processing/applied),
  13 sisa (cron expiry maju melewati proof pending, run_id requeue), 15 (sinkron server cart lintas perangkat), 23 (rollback CMS tepat snapshot).
- P2: 14 (sesi impor generasi/versi), 16 (URL media berversi), 17 (Google Reviews async, label rating manual), 18 (lint tanpa DISABLE_ESLINT_PLUGIN, CI),
  21 (audit scripts/import_user_catalog.py), restore backup overwrite yang bisa dipulihkan.
- Butuh user: key Midtrans Sandbox, SMTP fastcloud.id, DNS domain → deploy.sh SETUP_SSL.

## 2026-06 — E18 Pencarian cerdas + Pulihkan Konten CMS — iteration_53 100% (gate.sh HIJAU)
- Pencarian (`services/search.py`, rapidfuzz): toleran typo, awalan, kata sambung opsional ("aqua di gio"), angka tak di-fuzzy,
  singkatan brand otomatis (inisial nama/brand) + alias bawaan (YSL, CK, JPG, D&G, TF, MFK, PDM, …) + alias admin
  (Pengaturan › Toko › Alias Pencarian). Diuji di 1.071 produk katalog asli: 1–4 ms/kueri.
- `GET /api/search/suggest` → saran instan (produk + chip Brand/Kategori/Karakter/Notes + "Mungkin maksud Anda").
  Drawer pencarian memakai saran instan; Enter/"Lihat semua"/chip → `/shop?q=` (chip filter + did-you-mean di toko).
- Butir 23 (CMS): pemulihan revisi mengganti snapshot PERSIS (override baru dihapus), dicatat sebagai revisi baru (bisa di-undo);
  riwayat menampilkan penyunting, catatan, dan field yang berbeda; Pratinjau revisi ke draft; dialog konfirmasi sebelum memulihkan.
- Tes baru: `backend/tests/test_search_cms_e18.py` (17).

## 2026-06 — E19 Ledger idempoten & rekonsiliasi — iteration_54 100% (pytest 132 passed/1 skip + 9 e2e, gate.sh HIJAU)
- Butir 3: order lunas tak bisa dibatalkan tanpa refund; refund aman diulang (identitas stabil, `services/refunds.py`);
  /pay paralel → 1 attempt (pay_locks); tx gateway `paid` belum diterapkan dipulihkan sekali (`gateway.reconcile`).
- Butir 4/11/13: reservasi stok & kuota voucher ber-penanda (`order_holds.py`), order `reserving→pending` CAS + sweeper;
  shipped+resi atomik; cron `/api/cron/reconcile` (run_id idempoten, reclaim run gagal/macet).
- Butir 8: restore backup overwrite via staging (data lama utuh bila gagal). Butir 12: bukti bayar `processing` dilanjutkan tanpa hitung ganda.
- Butir 14: sesi impor bergenerasi. Butir 15: CartSync. Butir 16: ETag media. Butir 17: Google Reviews async + label manual.
- Butir 18: voucher checkout — validasi ulang gagal → total "belum terverifikasi", tombol `checkout-voucher-recheck`, buat pesanan diblok.
  CI GitHub Actions (`.github/workflows/ci.yml`): build FE CI=true tanpa DISABLE_ESLINT_PLUGIN, ruff F/E9, unit test ledger.
- Sesi ini: repo di-clone ulang, env backend diisi (MIDTRANS_MOCK, EMAIL_MOCK, SMTP_FROM_*, PAYMENT_DEADLINE_HOURS, PUBLIC_SITE_URL,
  WEBHOOK_CRON_SECRET); fix tes (`stock.reserve`, conftest event loop, isolasi CORS di tes deploy, default galeri), ruff bersih,
  `frontend/yarn.lock` dibuat (CI memakai --frozen-lockfile → WAJIB di-commit).

## Sisa / butuh user
- Key Midtrans Sandbox/Production (sekarang MOCK), SMTP fastcloud.id (sekarang EMAIL MOCK), DNS domain → deploy.sh SETUP_SSL.
- P2: Epic E8 lanjutan (a11y, audit N+1), notifikasi WhatsApp status pesanan, laporan penjualan.

## 2026-09 — Verifikasi AUDIT_CPWEB_DAN_DATA_IMPOR.md (sesi ini)
- Semua temuan kode dicek satu per satu → `memory/audit/STATUS_TEMUAN_AUDIT.md` (peta temuan → bukti).
- Perbaikan baru: bypass lockout login via `X-Forwarded-For` palsu (IP dihitung dari kanan, env `TRUSTED_PROXY_HOPS`, preview=3,
  VPS nginx=1) + kunci per-email 20×/15 mnt; ekspor produk CSV streaming & XLSX write-only; `stock.decrement` rollback saat exception.
- Tes: unit ledger pakai DB terpisah `<DB_NAME>_unit` + indeks startup (tanpa indeks, pay_locks tak menjamin 1 attempt — juga di CI);
  fixture berkontrak katalog v2; tes lockout lewat localhost. pytest 142 passed/1 skip.
- Masih ⛔: harga & stok katalog asli (`imports/catalog/harga_matrix.csv` kosong) — butuh data pemilik.

## 2026-09 — Redesign Discovery + filter toko + depth pass (iteration_55 100%)
- Beranda: section baru "Jelajahi Koleksi" (layout key `character_section`, konten CMS `discovery_section`) dengan tab
  Brand · Character · Editor's Picks (rating tertinggi) · Best Seller (ranking outline). "Sedang Trending" dihapus;
  "Shop by Occasion" otomatis tersembunyi bila < 2 momen.
- API: `GET /api/brands`, filter `brand=` di /api/products, `sort=rating`, `count` di /api/characters.
- Toko: hapus Kisaran Harga & Notes; Brand/Character = pencarian (FacetSearch); "Date Night" → label "Day & Night" (field tetap `date_night`).
- Depth: grain storefront, wash ambient, aksen judul emas miring, eyebrow bergaris, kartu hairline emas (`styles/depth.css`).
- Backlog teknis: `products.stock_holds` terus bertambah (penanda per order tak pernah dipangkas) → pangkas saat order final.

## 2026-09 — Gambar/SVG + CMS untuk "Jelajahi Koleksi" & kontras (iteration_56 100%)
- Admin → Katalog → Brand (`/admin/brand`): profil brand (logo SVG/PNG, foto kartu, deskripsi, urutan, sembunyikan);
  koleksi `brands` (kunci `name` = field brand produk), ikut backup. API `GET/PUT /api/admin/brands`, `DELETE /api/admin/brands/profile`.
- Karakter (& Occasion): field `image` (foto latar kartu) + `icon_image` (ikon kustom SVG/PNG).
- CMS `discovery_section`: judul + label & ikon SVG/PNG untuk 4 tab.
- Kontras: tab bar/search/kartu discovery putih solid + border & bayangan; `.cp-glass`/`.cp-glass-pill` global diberi hairline gelap (mode terang).

## 2026-09 — CMS Trust Strip / Marquee / Announcement (iteration_57 100%)
- Trust Strip: per item judul, deskripsi, ikon (19 pilihan), ikon gambar/SVG, tautan; tambah/hapus/geser (grid 1–4 kolom).
- Marquee (kata berjalan): kecepatan, gaya warna (terang/gelap/emas), pemisah teks atau gambar/SVG. Announcement: kecepatan + pemisah.

## 2026-09-27 (sesi lanjutan) — Restore repo + verifikasi CMS Trust/Marquee/Announcement
- Repo di-restore dari github.com/pandeyoga/cpweb ke /app (env preview dipertahankan; env backend diisi ulang: PAYMENT_DEADLINE_HOURS, WEBHOOK_CRON_SECRET, PUBLIC_SITE_URL, MIDTRANS_MOCK=true, EMAIL_MOCK=true, SMTP_FROM_*). seed_data.py dijalankan.
- Testing agent iteration_58: CMS Trust Strip / Marquee / Announcement diuji LEWAT UI admin (edit → Publish → beranda berubah) + 7/7 pytest; konten dikembalikan ke default.
- FIX: GET /api/reviews 500 (services.catalog.list_reviews hilang) → ditambahkan, hanya ulasan `published`.
- Backlog tetap: key Midtrans Sandbox, SMTP fastcloud.id, DNS domain (MOCK saat ini).
