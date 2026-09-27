# 📌 E14 — PLAN Aktivasi MIDTRANS + Audit Alur Penjualan (2026-09-26)

> Status: **Fase 0–4 ✅ (2026-09-26)** — Midtrans SIAP, berjalan di **MODE SIMULASI** sampai key diisi. Fase 5 (go-live) menunggu key.
> Keputusan user: **COD DIHAPUS**, batas bayar **24 jam**.
> Perbaikan bug kritis alur penjualan **SUDAH DIKERJAKAN** di sesi ini (lihat §2A).
> Keputusan user: transfer manual + unggah bukti **DIGANTI SEPENUHNYA** oleh Midtrans.

---

## 1) Snap vs Core API — perbedaan fungsional

| Aspek | **Snap** (rekomendasi) | **Core API** |
|---|---|---|
| UI pembayaran | Disediakan Midtrans (popup/redirect, responsif, bahasa ID) | Dibangun sendiri penuh (tampilan VA, QRIS, deeplink GoPay, form kartu) |
| Integrasi | 1 endpoint backend (buat `snap_token`) + `snap.js` di FE | 1 endpoint `/v2/charge` **per metode** + UI & alur tiap metode |
| Metode bayar | Semua channel aktif di dashboard otomatis muncul (VA BCA/BNI/BRI/Mandiri/Permata, QRIS, GoPay, ShopeePay, kartu, Indomaret/Alfamart, Akulaku/Kredivo) | Harus ditambah satu per satu di kode |
| Kartu kredit & 3DS | Tokenisasi + 3DS diurus Midtrans (beban PCI-DSS minimal) | Wajib tokenisasi `card_token` + 3DS sendiri |
| Waktu kerja | ± 2–3 hari (backend + FE + webhook + uji) | ± 1–2 minggu |
| Kontrol UX | Terbatas (tema warna/logo) | Penuh (pembayaran di dalam halaman sendiri) |
| Webhook & status | **Sama** — notifikasi HTTP + cek status API | **Sama** |

**Rekomendasi: Snap.** Fungsionalitas pembayaran & rekonsiliasi identik, tapi jauh lebih cepat,
lebih aman (kartu tidak menyentuh server kita), dan channel baru cukup diaktifkan di dashboard.
Core API hanya layak bila pembayaran wajib tampil “native” di halaman sendiri.

---

## 2) Audit alur penjualan (Cart → Checkout → Order → Bayar → Proses → Selesai/Batal)

### 2A. Bug KRITIS — **FIXED sesi ini** (regresi: `python scripts/repro_sales_flow.py` → 6/6 PASS)

| ID | Temuan | Dampak | Perbaikan |
|---|---|---|---|
| BUG-SALES-01 | `GET /api/orders/{code}` order **tamu** bisa dibaca siapa pun hanya dengan kode berurutan (`CP00000001`…) | Bocor PII (nama, HP, alamat) — IDOR enumerasi | Order baru punya `access_token` acak; order tamu wajib `?t=`; FE simpan token (URL + `localStorage cp:lastOrderToken`). Bukti bayar order tamu tak bisa diklaim akun lain |
| BUG-SALES-02 | `transition_order` update tanpa guard status → cancel paralel (admin + pelanggan / klik ganda) **mengembalikan stok berkali-kali** (repro: 5 paralel → stok +6, bukan +2) | Stok “palsu”, oversell | Compare-and-set `{code, status: frm}`; stok direstore hanya bila update menang |
| BUG-SALES-03 | Admin bisa set `pending → paid` tanpa uang masuk → `status=paid` tapi `payment_status=belum_bayar` | Pesanan dikirim tanpa bayar; SSOT status vs uang pecah | Non-COD: `paid` hanya bila `lunas` (dari pembayaran terverifikasi). UI admin menyembunyikan opsi itu |
| BUG-SALES-04 | Bukti bayar & verifikasi tak dibatasi sisa tagihan (bukti 10× total diterima; 2 bukti penuh → paid 2×) | Overpaid, laporan uang rusak | `record_payment` `$inc` ber-guard `paid + amt <= total` (atomik) + validasi saat submit bukti |
| BUG-SALES-05 | Pelanggan bisa membatalkan pesanan yang **sudah lunas/dikemas** | Stok kembali, uang tertahan tanpa jejak refund | Pelanggan hanya boleh batal saat `pending`; sisanya via admin |

Berkas diubah: `backend/services/orders.py`, `services/payments.py`, `routers/orders.py`,
`routers/payments.py`, `routers/admin_payments.py`, FE `services/orders.js`, `CheckoutPage.js`,
`OrderSuccessPage.js`, `components/shared/PaymentPanel.js`, `pages/admin/AdminOrderDetailPage.js`,
`scripts/test_e5_core.py` (ekspektasi pending→paid manual kini 400).

### 2B. Temuan BELUM diperbaiki — masuk plan (P0 = wajib sebelum/bersama Midtrans)

| ID | Prio | Temuan | Rencana |
|---|---|---|---|
| ✅ SALES-06 | **P0** | Order `pending` **tak pernah kedaluwarsa** → stok terkunci selamanya bila tak dibayar | `payment_deadline` di order; batal otomatis via webhook `expire` + sweeper terjadwal (cek status Midtrans dulu) |
| ✅ SALES-07 | **P0** | Batal/kedaluwarsa **tidak mengembalikan kuota voucher** (`used_count`, per-user) | Rilis voucher saat `pending → cancelled` (belum bayar); update invarian CE1 (`used_count == #order aktif pakai voucher`) |
| ✅ SALES-10 | **P0** | `POST /api/orders` tanpa idempotency key → retry jaringan/klik ganda = order ganda (stok & voucher terpotong 2×) | Header `Idempotency-Key` (UUID dari FE per sesi checkout) + unique index |
| ✅ SALES-13 | **P0** | Checkout tidak mengumpulkan **email** (tamu) → Midtrans `customer_details` & notifikasi | Field email (wajib untuk tamu, prefill untuk login) di `CreateAddress`/order |
| ✅ SALES-17 | **P0** | Halaman sukses selalu “Terima kasih! … Total Dibayar” walau belum bayar | Halaman status-aware: *Menunggu Pembayaran* (tombol **Bayar Sekarang** + hitung mundur) / *Lunas* / *Kedaluwarsa* |
| ✅ SALES-08 | P1 | **SSOT ganda biaya COD**: `settings.cod_fee` (Admin › Pengaturan, doc E6) vs `payment_methods[cod].fee` (yang dipakai order) + teks hardcoded “Biaya tambahan Rp 4.000” | Satu sumber (`payment_methods[cod].fee`), hapus field di Pengaturan, teks dari angka. *(Hilang sendiri bila COD dihapus)* |
| ✅ SALES-09 | P1 | `free_shipping_threshold` di Pengaturan **tidak dipakai** di pricing/checkout (setting mati) | Terapkan di `services/pricing.py` (SSOT) + tampilkan di checkout, atau hapus fieldnya |
| ✅ SALES-11 | P1 | Tamu **mem-bypass `per_user_limit` voucher** (limit hanya untuk user login) | Voucher ber-limit per-user wajib login, atau kunci limit ke email/HP |
| ✅ SALES-12 | P2 | Pratinjau voucher di checkout tidak mengirim `user_id` → alasan “batas per-user” baru muncul saat submit | Kirim konteks user saat validate |
| ✅ SALES-14 | P1 | Event analytics `purchase` dipicu saat order dibuat (belum bayar) & **terulang** tiap halaman sukses dibuka ulang | Catat `purchase` di server saat `paid` (webhook), dedupe per `order_code` |
| ✅ SALES-15 | P1 | Definisi revenue tidak seragam: dashboard `paid_revenue` ikut menjumlah order **cancelled**; CRM LTV fallback ke `total` | Satu modul `services/revenue.py` (SSOT) dipakai dashboard, CRM, analytics |
| ✅ SALES-16 | **P0** | Admin batalkan order lunas → **tak ada catatan refund** (`paid_amount` tetap); gate integritas `INV-P2` (tak boleh ada pembayaran verified pada order cancelled) langsung MERAH bila ini terjadi | Status/record `refund` + Midtrans Refund API (kartu/GoPay/ShopeePay/QRIS); VA → refund manual tercatat. Sementara: admin sebaiknya tidak membatalkan order lunas |
| ✅ SALES-18 | P2 | `LEGAL_TRANSITIONS` diduplikasi manual di FE (`components/admin/adminUi.js`) | Backend kirim `allowed_transitions` di respons order admin |
| ✅ SALES-19 | P2 | Order tamu lama (sebelum fix) tak punya `access_token` → link lama tak bisa dibuka | Diterima (admin tetap bisa); opsional backfill + kirim ulang link |
| ✅ SALES-20 | P2 | `admin_stats`/`crm` memuat semua order ke memori | Agregasi Mongo pipeline (bagian E8) |
| ✅ SALES-21 | P2 | Dokumen `docs/roadmap/E6_PAYMENTS.md`, `docs/06_STATE_MACHINE.md`, `04_API_CONTRACT.md` belum mencerminkan fix di atas | Perbarui bersamaan fase Midtrans |

---

## 3) Arsitektur target — Midtrans Snap

**Env (backend/.env, JANGAN hardcode):** `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY`,
`MIDTRANS_IS_PRODUCTION=false`, `MIDTRANS_EXPIRY_MINUTES` (usul 1440 = 24 jam).
Client key dikirim ke FE lewat `GET /api/settings` publik (bukan di-bundle). Tambah juga ke
`deploy.sh` + `backend/requirements-prod.txt` bila ada paket baru (REST cukup pakai `httpx` yang sudah ada).

**Data model baru `payment_transactions`** (SSOT jejak gateway; uang tetap SSOT `orders.paid_amount`):
`{id:"ptx_…", order_code, provider:"midtrans", gateway_order_id:"CP00000012-1" (unique), snap_token,
redirect_url, gross_amount, status, payment_type, va_numbers, fraud_status, last_notification,
expires_at, created_at, updated_at}`. Order: `payment:{group:"online", provider:"midtrans"}`,
`payment_deadline`, `email`.

**Endpoint:**
| Endpoint | Fungsi |
|---|---|
| `POST /api/orders/{code}/pay` | Pemilik / tamu ber-token. Buat atau pakai ulang `snap_token` (reuse bila masih pending & belum expired; attempt baru → suffix `-2`). `gross_amount` = `order.total` dari server; `item_details` (item + ongkir + diskon negatif) HARUS berjumlah persis sama |
| `POST /api/payments/midtrans/notification` | Webhook publik. Verifikasi `signature_key = SHA512(order_id+status_code+gross_amount+SERVER_KEY)` → cek ulang `GET /v2/{order_id}/status` → proses idempoten |
| `GET /api/orders/{code}/payment-status` | Polling FE setelah callback Snap (callback FE **tidak dipercaya**) |
| `GET /api/admin/payment-transactions` | Monitor transaksi (ganti halaman verifikasi bukti) |
| `POST /api/admin/orders/{code}/refund` | Fase 4 |

**Pemetaan status Midtrans → domain (lewat SSOT `record_payment` / `transition_order`):**
| Midtrans | Aksi |
|---|---|
| `capture` (+`fraud_status=accept`), `settlement` | `record_payment(total, source="midtrans")` → `pending→paid`, `lunas` |
| `pending` | simpan VA/QR; tidak ada perubahan order |
| `expire`, `cancel`, `deny`, `failure` | bila order masih `pending` & tak ada attempt lain yang aktif → `cancelled` (stok + voucher kembali) |
| `refund`, `partial_refund` | catat refund (Fase 4) |

Idempotensi: unique `gateway_order_id`; status transaksi hanya boleh maju; guard anti-overpay di
`record_payment` (sudah ada) membuat notifikasi `settlement` ganda aman.

**Frontend:** Checkout → satu opsi **“Bayar Online (VA, QRIS, e-wallet, kartu)”** (+COD bila dipertahankan).
Setelah order dibuat → `POST /pay` → `window.snap.pay(token)` (muat `snap.js` sandbox/production
sesuai env). Halaman sukses & riwayat akun: tombol **Bayar Sekarang**, hitung mundur `payment_deadline`,
polling status. Hapus form unggah bukti (`PaymentPanel`), admin “Pembayaran” jadi monitor transaksi.

**Migrasi:** order transfer manual yang masih `pending` diselesaikan admin lewat alur lama (endpoint
verifikasi dibiarkan read-only sampai habis), lalu seed `bca/bni/mandiri/shopeepay/ovo/gopay/dana`
dinonaktifkan dan kode bukti bayar dihapus.

---

## 4) Fase implementasi

| Fase | Isi | Kriteria selesai |
|---|---|---|
| **0 ✅** | Fix kritis BUG-SALES-01..05 | `repro_sales_flow.py` 6/6, `test_e3/e6_core`, `verify_state_machine` hijau |
| **1 ✅** | Prasyarat: SALES-06, 07, 10, 13, 17 + 08/09 + COD dihapus + gate hijau | Order tak dibayar batal otomatis & stok/voucher kembali; order ganda mustahil; email tersimpan |
| **2** | Backend Midtrans Sandbox: env, `payment_transactions`, `/pay`, webhook + signature + status check, sweeper kedaluwarsa (cron platform / systemd timer di VPS) | Simulator sandbox: settlement → `paid/lunas`; expire → `cancelled` + stok kembali; notifikasi ganda tak double-count; signature palsu → 403 |
| **3** | Frontend: opsi bayar online, Snap popup, halaman status-aware, tombol Bayar Sekarang, hapus unggah bukti | E2E: checkout tamu & login → bayar di simulator → status Lunas tampil tanpa refresh manual |
| **4** | Admin: monitor transaksi, refund (API + manual), revenue SSOT (SALES-15), analytics purchase server-side (SALES-14) | Laporan dashboard = Σ transaksi settlement − refund |
| **5** | Go-live: key production, Notification URL `https://collectorparfum.com/api/payments/midtrans/notification`, Finish/Unfinish/Error redirect URL, aktivasi channel di dashboard, HTTPS, update `deploy.sh`/docs | Transaksi nyata kecil (Rp 10.000) sukses & ter-rekonsiliasi |

> ✅ **Selesai di Fase 1** — `gate.sh` HIJAU lagi. Catatan lama: (sudah merah SEBELUM sesi ini, warisan fase Media Manager E20):**
> `validate_compliance` (AdminMediaPage.js 895 baris, AdminProductEditorPage.js 655, services/media.py 1146,
> URL hardcode di routers/admin_media.py:268 & services/media.py:1118) dan `verify_api_contract`
> (FE memanggil `/api/admin/uploads` yang tak punya route). Dibereskan di Fase 1 agar `gate.sh` hijau lagi.

### Hasil Fase 1 (2026-09-26) — regresi `python scripts/test_fase1_sales.py` 14/14, testing agent iteration_46 100%
- **SALES-06** `orders.payment_deadline` (+24 jam, env `PAYMENT_DEADLINE_HOURS`), `services/order_expiry.py`,
  `POST /api/cron/expire-orders` (Bearer `WEBHOOK_CRON_SECRET`, 202 + background, idempoten per `X-Webhook-Id`).
  Jadwal: `.emergent/crons.yml` tiap 15 menit + `/etc/cron.d/collector-parfum-expire-orders` di VPS (`deploy.sh`).
  Order dgn bukti bayar `pending` tidak dibatalkan (transfer manual masih berlaku sampai Midtrans).
- **SALES-07** batal (manual/kedaluwarsa) → `used_count`−1, redemption dihapus, slot per-user kembali (flag `voucher_released`; CE1 menyesuaikan).
- **SALES-10** header `Idempotency-Key` (FE: 1 UUID per sesi checkout) + unique partial index `orders.idempotency_key`.
- **SALES-13** `email` pembeli wajib utk tamu (fallback email akun) — tersimpan `orders.email`.
- **SALES-17** halaman sukses status-aware (menunggu/lunas/batal·kedaluwarsa) + hitung mundur; riwayat akun menampilkan batas bayar.
- **SALES-08 / COD** COD dihapus: checkout tanpa tab COD, API menolak `group=cod`, metode COD dinonaktifkan saat startup, field “Biaya COD” dihapus.
- **SALES-09** `free_shipping_threshold` kini berlaku (SSOT `pricing.effective_shipping`) + catatan di checkout.
- **Gate**: `services/media.py` dipecah (fasad + `media_core/folders/images/ingest/assets/maint`), `AdminMediaPage` → `MediaPageView`,
  `AdminProductEditorPage` → `ProductMediaTab`, endpoint FE mati `/api/admin/uploads` dihapus → `bash scripts/gate.sh` **HIJAU**.

### Hasil Fase 2–4 (2026-09-26) — regresi `python scripts/test_gateway_midtrans.py` 22/22
- **Mode otomatis dari env** (`services/midtrans.py`): `MIDTRANS_SERVER_KEY` terisi → **live** (sandbox/production via
  `MIDTRANS_IS_PRODUCTION`); kosong + `MIDTRANS_MOCK=true` → **SIMULASI** (preview sekarang); kosong + mock off → nonaktif (503).
- **Backend** `services/gateway.py` + `routers/gateway.py`: `POST /api/orders/{code}/pay` (reuse token / attempt `CODE-n`,
  item_details = total persis, expiry = sisa batas bayar), webhook `POST /api/payments/midtrans/notification`
  (SHA512 signature + cek ulang status API di mode live, cek nominal, idempoten), `GET /api/orders/{code}/payment-status`,
  simulasi `POST /api/orders/{code}/mock-pay`, admin `GET /api/admin/payment-transactions` + `POST /api/admin/orders/{code}/refund`.
- Pemetaan: settlement/capture(accept) → `record_payment` → paid/lunas · deny/cancel → gagal (order tetap bisa dibayar ulang) ·
  expire → order batal (stok+voucher kembali) · dibayar setelah batal → `needs_refund` (tombol refund di admin).
- **Metode bayar**: saat startup & seed, “Bayar Online” (group `online`) aktif dan transfer/e-wallet manual nonaktif bila gateway aktif.
  Alur bukti transfer tetap ada utk order lama; order online menolak unggah bukti.
- **Frontend**: checkout “Bayar Online” → halaman pesanan membuka Snap otomatis (`?pay=1`), tombol **Bayar Sekarang** di
  halaman pesanan & riwayat akun, dialog **Mode Simulasi** (Berhasil/Ditolak/Kedaluwarsa) saat key belum ada.
- **Admin**: halaman Pembayaran → tabel “Transaksi Online (Midtrans)”; detail pesanan → tombol Refund + info refund/alasan batal.
- **SALES-14** event `purchase` dicatat server saat order paid (1×/order), bukan saat halaman dibuka. **SALES-15/16** dashboard
  `paid_revenue` = dibayar − direfund; refund tercatat di koleksi `refunds` + `orders.refunded_amount`.
- Sweeper kedaluwarsa mengecek status Midtrans dulu (webhook terlewat tidak membatalkan order yang sebenarnya sudah dibayar).

### Fase 5 — Go-live (butuh tindakan user)
1. Isi `backend/.env`: `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY` (sandbox dulu), `MIDTRANS_MOCK=false` → restart backend.
   VPS: `sudo MIDTRANS_SERVER_KEY=... MIDTRANS_CLIENT_KEY=... bash deploy.sh` (key tersimpan & dipertahankan saat redeploy).
2. Dashboard Midtrans › Settings › Configuration: **Payment Notification URL** = `https://collectorparfum.com/api/payments/midtrans/notification`;
   Finish/Unfinish/Error redirect = `https://collectorparfum.com/akun`.
3. Uji di sandbox simulator (https://simulator.sandbox.midtrans.com), lalu key production + `MIDTRANS_IS_PRODUCTION=true`, transaksi Rp 10.000.

## 5) Yang dibutuhkan dari user
1. Daftar akun **Midtrans Sandbox** (https://dashboard.sandbox.midtrans.com) → Settings › Access Keys → **Server Key & Client Key**.
2. ~~COD~~ → **dihapus** (diputuskan).
3. ~~Batas bayar~~ → **24 jam** (diputuskan). Channel yang diaktifkan (VA, QRIS, GoPay/ShopeePay, kartu, gerai retail).
4. Kebijakan refund (siapa yang boleh, penuh/sebagian).

---

# Development Plan — Media Upload + Media Manager (Collector Parfum)

## 1) Objectives
- Enable **reliable image upload** (JPG/PNG/WebP/GIF/SVG/AVIF/HEIC) with **15MB limit**.
- Build a **premium admin Media Manager** with **nested folders**, search/filter/sort, grid+list, bulk ops.
- Provide a **unified Media Picker** usable across: Product Editor, CMS Konten, Kategori, Lokasi Toko, Pengaturan pembayaran.
- Fix broken images by making storage **local disk SSOT** (VPS) with optional **MongoDB GridFS mirror + self-heal** (toggle via env).
- Preserve backward compatibility for legacy endpoints/records and existing `/api/media/*` URLs.

## 2) Implementation Steps

### Phase 1 — Core POC (must pass before UI work)
**Goal:** Prove end-to-end core: folders + upload + derivatives + serve + self-heal + product attachment.
1. **Web research (best practices)**: confirm recommended Pillow pipeline (EXIF transpose, WebP derivatives, GIF/SVG handling), HEIC/AVIF decoding options, and FastAPI streaming FileResponse caching headers.
2. Backend minimal core additions (only what POC needs):
   - `media_folders` model + CRUD functions (nested tree).
   - Extend `media_assets` schema to include: `folder_id`, `checksum`, `width/height`, `alt/title`, `thumb_url`, `medium_url`, `stored_path`, timestamps.
   - Upload pipeline: 15MB cap; Pillow optimize; generate `_400.webp` + `_1000.webp` (skip SVG; GIF: keep original, no WebP); EXIF auto-orient.
   - Storage layout: `MEDIA_ROOT/originals/YYYY/MM/<uuid>.<ext>` and `MEDIA_ROOT/derived/<uuid>_{400|1000}.webp`.
   - GridFS mirror (AsyncIOMotorGridFSBucket) gated by `MEDIA_DB_MIRROR=true`.
   - Replace static mount with **GET `/api/media/{path:path}`** handler: serve from disk; if missing and mirror enabled → restore from GridFS → serve.
3. Unify API surface (POC subset):
   - `POST /api/admin/media/folders`, `GET /api/admin/media/folders/tree`, `PATCH /api/admin/media/folders/{id}`.
   - `POST /api/admin/media/upload` (multi-file), `POST /api/admin/media/from-url`.
   - `GET /api/admin/media/assets` (q/folder_id/sort/page/limit + `X-Total-Count`).
   - `PATCH /api/admin/media/assets/{id}` (rename, alt/title, move).
   - `POST /api/admin/media/assets/bulk-move`, `POST /api/admin/media/assets/bulk-delete`.
   - Keep aliases: `/api/admin/uploads` and legacy `/api/admin/media` working.
4. Write **one script**: `scripts/test_media_core.py` executing the 14 checks in the spec (upload multi-MB, thumbs, serve 200, self-heal after deleting disk, from-url ingest, move/rename/alt, search/sort/pagination, bulk ops, folder delete guard, attach to product + verify in public catalog, invalid mime & >15MB reject, legacy compatibility).
5. Iterate until **100% PASS** with no 5xx.

**Phase 1 user stories**
1. As an admin, I can create nested folders (Produk > Banner > 2026) and see them as a tree.
2. As an admin, I can upload multiple images up to 15MB and get stable `/api/media/...` URLs.
3. As an admin, I get thumbnails/medium images automatically for fast browsing.
4. As an admin, if the original file disappears from disk, the same URL still works (self-heal).
5. As an admin, I can ingest an external URL and it becomes a locally-served image.

### Phase 2 — V1 App Development (Media Manager + Picker)
1. Backend hardening & consolidation:
   - Move all media endpoints into `routers/admin_media.py` under `/api/admin/media/*` (registered before legacy routes).
   - Finalize indexes: folders (parent_id, path), assets (folder_id, uploaded_at, checksum, text index on filename/title/alt).
   - Ensure legacy seed images in `backend/media/*.png` still served.
   - Document env: `MEDIA_ROOT`, `MEDIA_MAX_MB=15`, `MEDIA_DB_MIRROR`.
2. Frontend: new `src/services/media.js` (SSOT client for media endpoints).
3. Build **AdminMediaPage** at `/admin/media`:
   - Nested folder tree (collapse), breadcrumb, counts.
   - Upload dropzone + file picker; per-file progress.
   - Grid/list toggle; search; type filter; sort; pagination.
   - Bulk select bar: delete/move.
   - Details drawer: preview, copy URL, rename, alt/title, move, replace, delete.
4. Build reusable **`<MediaPickerDialog>`**:
   - Tabs: Library (folders), Upload, From URL.
   - Single & multi select.
5. Integrate picker everywhere (replace raw URL-only flows):
   - Product Editor media tab: add upload + picker, drag reorder, set primary.
   - CMS ContentForm ImageField uses picker (keep upload).
   - Categories, Stores, Settings payment/logo images use picker.
6. Add `resolveMediaUrl()` + `<SmartImage>` to avoid broken-image icon and normalize relative URLs.
7. Add sidebar nav entry “Media” under group “Konten”.
8. Run 1 full E2E pass (testing agent) + fix regressions.

**Phase 2 user stories**
1. As an admin, I can manage media in one place (/admin/media) with folders, search, and bulk actions.
2. As an admin, I can upload from the Media Manager and see thumbnails immediately.
3. As an admin, I can pick images for a product from the Media Picker without leaving the editor.
4. As an admin, I can paste an external image URL and the system stores it locally.
5. As an admin, I can use the same picker for CMS sections, category image, store location image, and payment QR/logo.

### Phase 3 — Quality, Migration, and Guardrails
1. Data migration script (idempotent):
   - Normalize existing `media_assets` docs (uploaded_at vs created_at) into unified fields.
   - Default folders seeded (Produk/Banner/Konten/Logo) and assign unfiled assets.
2. Update docs: `docs/03_DATA_MODEL.md`, `docs/04_API_CONTRACT.md`, `DEPLOYMENT_VPS.md` (persistent volume for MEDIA_ROOT, nginx `client_max_body_size 20m`).
3. Update memory: `memory/BUG_REGISTRY.md` (BUG-MEDIA-01..05 fixed), `memory/HANDOFF.md`, `memory/test_credentials.md`.
4. Add/extend gate checks:
   - Backend: ensure no 5xx on adversarial upload, and self-heal path covered.
   - Minimal FE smoke checks for picker open/close and asset list render.
5. Run `scripts/gate.sh` + forensics; run testing agent again.

**Phase 3 user stories**
1. As an admin, my previously uploaded/seeded images still appear and are searchable after migration.
2. As an admin, deleting a folder with content is handled safely (blocked or controlled cascade).
3. As an admin, media URLs remain stable and backward compatible.
4. As an admin, I can see storage stats and quickly find assets by search.
5. As an admin, after restart/redeploy, images still work without manual re-upload.

## 3) Next Actions
1. Implement `scripts/test_media_core.py` scaffold (login + folder CRUD + upload + fetch + self-heal asserts).
2. Add minimal backend endpoints + folder collection + unified asset schema + Pillow derivative generation.
3. Implement `/api/media/{path:path}` self-healing route + GridFS mirror toggle.
4. Run POC script repeatedly until 100% pass; only then start UI.

## 4) Success Criteria
- `python scripts/test_media_core.py` passes **all checks** (including self-heal, from-url ingest, >5MB uploads, invalid payload rejects with 400).
- Admin can upload images from Product Editor and Media Manager; images never break after restart/redeploy.
- Nested folder manager supports create/rename/delete, move assets, bulk operations, search/filter/sort, grid/list.
- Same Media Picker works in Product Editor + CMS Konten + Kategori + Lokasi + Pengaturan pembayaran.
- Legacy `/api/admin/uploads` and existing `/api/media/...` links continue working.
---

# 📌 STATUS PENGERJAAN (E20 — Media Manager Lokal)

## Fase 1 — POC Inti ✅ SELESAI
`scripts/test_media_core.py` → **117/117 PASS** (0 gagal).
Cakupan: login RBAC · folder bertingkat 3 level (create/rename/move/guard siklus/duplikat) ·
upload multi-berkas (JPEG 8.8MB, PNG transparan, SVG, GIF animasi, HEIC iPhone, AVIF) ·
optimasi Pillow (EXIF auto-orient, batas 2400px, turunan WebP 400/1000) · de-dup sha256 ·
penyajian HTTP 200 + content-type + cache + ETag 304 · **SELF-HEAL** (berkas dihapus dari
disk → GET tetap 200 & berkas pulih dari mirror MongoDB) · from-url (unduh ke lokal) ·
patch metadata tanpa mengubah URL · replace berkas (URL tetap) · cari/filter/sort/paginasi
+ X-Total-Count · bulk move/delete (berkas fisik & mirror ikut) · hapus folder aman
(isi dipindah ke induk) + cascade · pasang media ke produk → tampil di katalog PUBLIK ·
penolakan mime/ukuran/traversal tanpa 5xx · RBAC 401/403 · kompatibilitas legacy
(`/admin/uploads`, `/admin/media`, berkas datar lama) · **lokalisasi URL eksternal +
penulisan ulang referensi** (produk, kategori, CMS, toko, pembayaran) & idempotensi.

## Fase 2 — Aplikasi ✅ SELESAI (menunggu verifikasi testing agent)

### Backend
- `backend/services/media.py` (baru, ±1.150 baris): SSOT penyimpanan lokal.
  Layout `media/originals/YYYY/MM/<uuid>.<ext>` + `media/derived/<uuid>_{400,1000}.webp`.
  Mirror GridFS `media_files` (env `MEDIA_DB_MIRROR`, default aktif) + self-heal.
  Batas `MEDIA_MAX_MB=15`. Format: JPG/PNG/WebP/GIF/SVG/AVIF/HEIC(→JPEG)/BMP/TIFF.
- `backend/routers/media_public.py` (baru): `GET|HEAD /api/media/{path}` — pengganti
  `StaticFiles`, self-healing + Cache-Control + ETag + anti path-traversal.
- `backend/routers/admin_media.py` (ditulis ulang): SSOT endpoint media.
  Folders (`/folders`, `/folders/tree`, PATCH, DELETE?cascade), Assets (`/assets`,
  `/upload`, `/from-url`, `/assets/{id}` GET/PATCH/DELETE, `/assets/{id}/replace`,
  `/assets/bulk-delete`, `/assets/bulk-move`), `/stats`,
  `/maintenance/migrate`, `/maintenance/localize`. Alias legacy dipertahankan.
- `backend/media_schemas.py` (baru): kontrak Pydantic media.
- `backend/routers/admin.py`: endpoint media DIPINDAH keluar (hindari tabrakan route).
- `backend/server.py`: mount StaticFiles dihapus, router media didaftarkan lebih dulu,
  indeks media, migrasi + folder standar idempotent saat startup.
- `backend/routers/payments.py`: `POST /api/orders/{code}/payment-proof/upload` —
  pelanggan bisa UNGGAH FOTO bukti bayar (bukan lagi tempel URL). Owner-scoped.
- Skema baru: `payment_methods.logo`, `payment_methods.qr_image`, `store_locations.photo`.

### Frontend
- `src/lib/mediaUrl.js` — resolveMediaUrl (RELATIF di DB → absolut saat render),
  formatBytes, badge tipe, checkerboard, `handleImageError`, placeholder SVG inline.
- `src/components/shared/SmartImage.js` — skeleton → fade-in → placeholder+retry.
  TIDAK PERNAH menampilkan ikon broken-image browser.
- `src/services/media.js` — klien SSOT + `mediaErrorMessage` jujur.
- `src/pages/admin/AdminMediaPage.js` — Media Manager 3 kolom (rail folder / kanvas /
  inspektur), statistik penyimpanan, peringatan + tombol perbaiki gambar hotlink,
  overlay drag&drop global, antrean upload berprogres, bilah aksi massal,
  Sheet untuk mobile.
- `src/components/admin/media/` — FolderTree (flat-render, aman untuk Babel dev),
  MediaToolbar, AssetGrid/AssetList/AssetTile, AssetDetailsPanel, Dropzone,
  UploadQueuePanel, useMediaUpload, MediaDialogs, **MediaPickerDialog**, **MediaField**.
- Integrasi picker: Editor Produk (tab Media: pilih/upload/URL + set utama + urutkan),
  CMS ContentForm (semua field gambar), Kategori (image), Lokasi Toko (photo),
  Pengaturan (OG image + logo & QR metode bayar).
- Ketahanan storefront: ProductCard, ProductDetailPage (carousel/mosaik/sticky),
  QuickViewModal, ImageLightbox, CategoryGrid, StoreLocationsPage, ProductPreview admin,
  PaymentPanel — semua resolve URL + fallback placeholder.
- `src/App.js` rute `/admin/media`, sidebar grup "Konten" → **Media**.
- `src/constants/testIds/admin.js` — ±90 testId media baru.

## Fase 3 — Verifikasi E2E & polish ✅ SELESAI (sesi lanjutan)
- App dipulihkan dari GitHub (kaananabana/cp) ke /app, deps di-install, DB di-seed ulang.
- **Frontend E2E media manager: 100%** (testing_agent_v3 iteration_42): upload, folder
  bertingkat, detail/rename/alt, bulk, cari/filter/sort, hotlink localize, picker di
  editor produk + kategori + lokasi + pembayaran + CMS, add-from-URL lokal.
- Audit gambar (scroll penuh): **HOME 0 broken, SHOP 0 broken**; "9 broken" laporan awal
  adalah FALSE POSITIVE dari lazy-load (belum ter-scroll). PDP hanya placeholder SVG
  prosedural (bukan broken).
- **Perbaikan UI (permintaan user, terverifikasi 100%):**
  1. Manifesto (BigScrollingWord): parallax dibuat non-negatif + font `clamp()` →
     tipografi TIDAK terpotong lagi di tepi kiri/kanan (1920 & 1440).
  2. Margin samping section beranda ditambah via `[data-testid="home-page"] .cp-container-wide`
     (scoped — Shop/PDP sengaja dibiarkan immersive sesuai permintaan).
- Bersih-bersih pasca-test: gambar uji di prd_greenbasillime dihapus (kembali placeholder
  bersih), "Test Folder E2E" + 7 aset uji dihapus → media manager pristine (4 folder default,
  0 aset, 0 hotlink).

### Sisa pekerjaan (opsional, jika user minta)
1. (done) Verifikasi end-to-end oleh `testing_agent_v3` (backend + frontend) & perbaiki temuan.
2. Perbarui `docs/03_DATA_MODEL.md`, `docs/04_API_CONTRACT.md`, `DEPLOYMENT_VPS.md`
   (volume persisten `MEDIA_ROOT`, `client_max_body_size 20m`, `MEDIA_DB_MIRROR`),
   `memory/BUG_REGISTRY.md` (BUG-MEDIA-01..05), `memory/HANDOFF.md`,
   `memory/test_credentials.md`.
3. Opsional lanjutan: crop/rotate di browser, tag & koleksi, laporan aset tak terpakai.
