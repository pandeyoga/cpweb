# Status temuan AUDIT_CPWEB_DAN_DATA_IMPOR.md (dicek terhadap kode, 27 Sep 2026)

Legenda: ✅ sudah diperbaiki & ada bukti di kode/tes · 🟡 keputusan desain (sengaja) · ⛔ butuh data/keputusan pemilik

## Data & impor
| # | Temuan | Status | Bukti |
|---|---|---|---|
| D1 P0 | 9.639 baris harga 0 & stok 0 | ⛔ | Kode menolak harga 0 & tak mengarang harga; `imports/catalog/harga_matrix.csv` (36 kombinasi tier×ukuran×tipe) MASIH KOSONG — isi harga/stok dari pemilik, lalu `scripts/replace_catalog.py --apply` |
| D2 P0 | tier/date_night tak ada di kontrak | ✅ | Katalog v2: field produk + impor/ekspor + filter (`tests/test_catalog_v2.py`) |
| D3 P1 | concentration jadi EDP diam-diam | ✅ | Impor tak lagi mengisi concentration; API publik tanpa concentration/ingredients |
| D3b | occasions lama bertahan saat upsert tanpa kolom | 🟡 | Sengaja (anti data-loss: file tanpa kolom facet tak menghapus facet). Occasion selain Date Night disembunyikan oleh `replace_catalog.py` |
| D4 P1 | 405 produk tanpa karakter yang cocok | ✅ | `replace_catalog.py` membuat slug karakter baru otomatis |
| D5 P1 | filter concentration/occasion; tier/date_night/tipe belum ada | ✅ | Katalog v2 (toko + API) |
| D6 P2 | gambar & SKU kosong | ✅/⛔ | SKU dibuat sistem; gambar harus disiapkan pemilik |

## Transaksi & pesanan
| # | Temuan | Status | Bukti |
|---|---|---|---|
| T1 P0 | webhook `paid` sebelum record_payment | ✅ | `gateway.py` flag `payment_applied` + `gateway.reconcile`; tes `test_unit_gateway_paid_not_applied_is_recovered_once` |
| T2 P0 | order dibuat setelah stok/voucher dikurangi | ✅ | `order_create.py` status `reserving` → CAS `pending` + `sweep_stale_reserving`; tes crash di tiap langkah tulis (9 titik) |
| T3 P1 | refund retry ganda / parsial yatim | ✅ | `refunds.py` identitas refund stabil; `needs_refund` hanya false bila sisa 0 |
| T4 P1 | /pay paralel | ✅ | `pay_locks` unik; tes 5× paralel → 1 attempt |
| T5 P1 | admin batal order lunas tanpa refund | ✅ | `InvalidTransition` bila paid−refunded>0 |
| T6 P1 | admin order 500 / dashboard 50.000 | ✅ | paginasi + cari (`X-Total-Count`); dashboard agregasi `$group` |
| T7 P1 | ongkir Rp0 di detail; shipped tanpa resi | ✅ | `order.shipping.price`; shipped+resi satu update CAS |
| T8 P2 | tamu tak bisa kirim bukti | ✅ | access token order untuk tamu |
| T9 P2 | janji COD | ✅ | teks COD dihapus |

## Keamanan & ketahanan
| # | Temuan | Status | Bukti |
|---|---|---|---|
| S1 P0 | password admin bawaan / seed menimpa hash | ✅ | `deploy.sh` password acak (file root 600, tak dicetak), `SEED_REQUIRE_STRONG_PASS`, seed tak menimpa hash; tes `test_unit_seed_rejects_default_password_in_production` |
| A1 P1 | SVG XSS | ✅ | SVG disajikan CSP sandbox + nosniff |
| A2 P1 | restore overwrite hapus dulu | ✅ | staging collection; tes `test_unit_backup_overwrite_failure_keeps_old_data` |
| A3 P1 | order total Rp0 | ✅ | ditolak di `order_create.py` |
| A4 P1 | form kontak/newsletter palsu | ✅ | `routers/public_forms.py` |
| A5 P1 | `emails_sent` sebelum SMTP | ✅ | `notify.py` retry via rekonsiliasi |
| A6 P2 | analitik range & purchase publik | ✅ | filter waktu; purchase hanya dari server |
| A7 P2 | CRM LTV/limit/ekspor | ✅ | LTV = paid − refunded via agregasi (tanpa batas order), berhalaman, ekspor CSV lengkap dari server (batas aman 50.000 akun pelanggan) |
| A8 P2 | logout & brute force | ✅ | logout cabut sesi; lockout. **Sesi ini:** celah bypass via `X-Forwarded-For` palsu DITUTUP (`TRUSTED_PROXY_HOPS`) + kunci per-email 20×/15 mnt; tes baru |
| A9 P2 | SSRF unduh media | ✅ | `services/net_guard.py` |
| B1 P0 | `stock.decrement` tanpa rollback saat exception | ✅ | Checkout memakai `stock.reserve` ber-penanda; **sesi ini** `decrement` juga rollback saat write melempar |
| B2 P0 | batal: status dulu, stok/voucher belakangan | ✅ | `order_holds.release_order` idempoten + rekonsiliasi; tes crash-cancel |
| B3 P1 | bukti `verified` sebelum record_payment | ✅ | status `processing` + `payments.resume_processing`; tes |
| B4 P1 | startup satu `try` | ✅ | `services/startup.py` langkah terisolasi, `/api/health` ready/init_errors |
| B5 P1 | cron expiry 500 macet | ✅ | batch maju melewati order ber-bukti pending; tes |
| B6 P1 | cron run_id tak bisa diulang | ✅ | `_reclaim` untuk failed/macet |
| B7 P1 | Idempotency-Key tanpa sidik isi | ✅ | 409 `idempotency_conflict` |
| B8 P2 | dua alamat default | ✅ | indeks unik parsial; tes paralel |
| B9 P2 | ekspor produk memuat semua ke memori | ✅ | **Sesi ini:** CSV streaming dari cursor, XLSX write-only |

## Impor, fitur terhubung, build
| # | Temuan | Status | Bukti |
|---|---|---|---|
| C1 P1 | sesi impor hapus chunk dulu; potong >30.000 diam-diam | ✅ | generasi chunk; `TooManyRows` eksplisit; tes |
| C2 P1 | field produk beda antarbaris slug sama diabaikan | ✅ | error "Kolom tingkat produk berbeda dari baris pertama" |
| C3 P2 | server cart tak dipakai | ✅ | `store/CartSync.js` |
| C4 P2 | cache media 1 tahun / urutan tulis-hapus | ✅ | ETag revalidasi; tulis atomik; metadata dihapus dulu |
| C5 P2 | rating manual & Google sync | ✅ | label "manual"; `httpx.AsyncClient` |
| C6 P2 | build lint & lockfile | ✅ | CI `yarn build` CI=true tanpa DISABLE_ESLINT_PLUGIN lulus; `frontend/yarn.lock` dibuat (WAJIB di-commit) |
| C7 P2 | voucher gagal jaringan tetap tampil diskon lama | ✅ | "Validasi ulang" + blok buat pesanan (iteration_54) |
| C8 P2 | quick-add tanpa cek stok | ✅ | hanya varian ber-stok |
| C9 P1 | cache katalog 100 produk | ✅ | wishlist/keranjang via `GET /api/products?ids=`, pencarian server |
| C10 P2 | riwayat pesanan 100 | ✅ | berhalaman |
| C11 P1 | `import_user_catalog.py` harga Rp1.000 / exit 0 | ✅ | tanpa harga karangan, kredensial dari env, exit 1 + `--resume` |
| C12 P2 | intro Lokasi tak tersimpan | ✅ | `stores_intro` |
| C13 P1 | upload bukti dibaca penuh | ✅ | batas saat streaming |
| C14 P2 | revert CMS merge | ✅ | replace snapshot persis (E18) |

## Temuan tambahan sesi ini (di luar audit)
- Bypass lockout login dengan `X-Forwarded-For` palsu → ✅ diperbaiki (lihat A8).
- `tests/test_iter49_features.py` menghapus `voucher_redemptions` milik order NYATA saat setup → invarian CE1 (gate) merah.
  ✅ Tes kini memakai akun baru; data preview dipulihkan. `gate.sh` HIJAU.
- Tes unit ledger berjalan tanpa indeks unik di DB kosong (CI) → jaminan `/pay` 1 attempt tak teruji benar. ✅ indeks startup dipasang di tes.

## Rekomendasi non-bug (belum dikerjakan, butuh keputusan)
Ongkir nyata per alamat/API kurir & AWB, retur/RMA, invoice, laporan settlement/refund, uji Midtrans Sandbox end-to-end (butuh key).
