# Katalog produk — ganti seluruh data produk dari Excel

Folder ini adalah **sumber data katalog**. Edit file di sini lalu jalankan skrip di VPS.

| File | Isi |
|------|-----|
| `produk.xlsx` | Sheet **Produk**: 1 baris = 1 varian. 1.071 produk × 9 varian (Ukuran 35/60/100ml × Tipe Basic/Refine/Intense). Kolom `tier` (CP01/CP02/CP03/EXCLUSIVE), `day_night` (Day / Night / Day/Night / kosong), `characters` (keluarga aroma, pisah koma). |
| `harga_matrix.csv` | Harga, harga coret, dan stok per **tier × ukuran × tipe** (36 baris). Kosong = belum ada harga. |
| `laporan_terakhir.json` | Hasil validasi/eksekusi terakhir (dibuat otomatis). |

Harga/stok per baris di `produk.xlsx` (kolom `variant_price`, `variant_stock`) bila diisi > 0 **menang** atas matriks.

## Menjalankan di VPS

```bash
cd /home/collector/collector-parfum            # folder aplikasi
sudo -u collector git pull                      # bila file diperbarui lewat GitHub
sudo -u collector backend/venv/bin/python scripts/replace_catalog.py           # 1) CEK saja (aman)
sudo -u collector backend/venv/bin/python scripts/replace_catalog.py --apply   # 2) backup + ganti
```
(sesuaikan path python venv bila berbeda; skrip membaca `MONGO_URL`/`DB_NAME` dari `backend/.env`).

Yang terjadi saat `--apply`:
1. **Backup otomatis** (produk, karakter, occasion, wishlist, keranjang) → bisa dipulihkan di Admin › Backup & Restore.
2. Produk dengan slug yang sama **diganti** (id lama dipertahankan → riwayat pesanan tetap valid).
3. Produk baru ditambahkan.
4. Produk lama yang tidak ada di file **dihapus**; yang pernah dipesan hanya **diarsipkan** agar pesanan lama tidak rusak.
5. Karakter aroma yang belum ada dibuat otomatis; occasion lama disembunyikan (facet momen kini = kolom `day_night`).
6. **Harga & stok lama dipertahankan**: varian dengan SKU sama (atau slug + Ukuran + Tipe sama) yang sudah punya harga di database memakai harga/stok itu bila kolom Excel kosong/0 (`--no-keep-prices` untuk mematikan).

Cara termudah di VPS: `sudo bash scripts/vps_update_catalog.sh` (backup → ganti repo → deploy → cek → konfirmasi → terapkan).

## Aturan publikasi
- Produk hanya **aktif (tampil di toko)** bila **semua 9 varian punya harga > 0**. Saat ini seluruh harga di file = 0,
  sehingga semua produk tersimpan **archived** sampai `harga_matrix.csv` diisi — tidak ada harga karangan.
- Stok 0 tetap tampil sebagai "habis" kecuali memakai `--archive-out-of-stock`.
- Pengaman: `--apply` DITOLAK bila tidak ada satu pun produk yang akan aktif (toko jadi kosong). Pakai
  `--allow-empty-store` hanya bila memang ingin mengganti data sekarang dan mengisi harga belakangan.
- Validasi gagal (slug/kategori/tier/ukuran/tipe salah, SKU duplikat, kolom produk berbeda antar baris) → database **tidak diubah**.

## Koreksi yang sudah diterapkan pada file ini (dari file asli pengguna)
- 5 produk dengan `characters` hasil scraping rusak (`bold-and-sensual`, `excellent-choice-to-present-the-new`, `new`)
  diganti keluarga aroma dari notes-nya dan kalimat deskripsi rusak dihapus — **perlu cek manual**:
  burberry-her-elixir-w → floral-fruity-gourmand, hugo-boss-element-m → aromatic-aquatic,
  victoria-s-secret-pink-fruity-w → gourmand, tiziana-terenzi-kirke-overdose-u → floral-fruity-gourmand,
  parfums-de-marly-valaya-exclusif-w → floral-woody-musk.
- `variant_sku` diisi otomatis (`SLUG-TIPE-UKURAN`, unik untuk 9.639 varian).
- `best_seller`/`is_new` teks "true/false" dibaca sebagai boolean.
- 2026-09: file diganti versi DAY/NIGHT dari klien (kolom `day_night`; tidak ada lagi Date Night).
