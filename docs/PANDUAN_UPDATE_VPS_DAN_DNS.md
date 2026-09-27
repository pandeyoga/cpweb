# Panduan: Update VPS + Katalog Day/Night + Domain collectorparfum.com

VPS: `148.230.102.29` · Folder aplikasi: `/home/collector/collector-parfum` · Repo baru: `https://github.com/pandeyoga/cpweb`

## Perlu deploy dari awal?
**Tidak.** Cukup ganti sumber repo lalu update di tempat. Database (pesanan, pelanggan, CMS), media upload,
`backend/.env`, dan pilihan domain/SSL tetap aman. Deploy dari nol hanya perlu untuk VPS baru.

## Langkah 0 — Push kode ke GitHub (di Emergent)
Klik **Save to GitHub**, lalu pilih repo `pandeyoga/cpweb` branch `main`. Repo harus **publik**, atau VPS harus punya akses ke repo tersebut.

## Langkah 1 — Update VPS + katalog (SSH ke VPS sebagai root)
```bash
wget -O /root/vps_update_catalog.sh https://raw.githubusercontent.com/pandeyoga/cpweb/main/scripts/vps_update_catalog.sh
sudo bash /root/vps_update_catalog.sh
```
Yang dilakukan skrip:
1. Backup database lengkap (`/var/backups/collector-parfum/pre-update-*.archive.gz`).
2. Remote git diganti ke `pandeyoga/cpweb`, lalu kode terbaru diambil.
3. `deploy.sh` dijalankan: build frontend, restart backend, domain/SSL tetap.
4. Katalog `imports/catalog/produk.xlsx` dicek dulu tanpa mengubah data. Ringkasan ditampilkan, lalu Anda diminta **konfirmasi**.
   - Harga & stok lama dari VPS **dipakai** untuk produk/SKU yang sama.
   - Produk tanpa harga disimpan **archived** (tidak tampil) sampai harganya diisi.
   - Produk lama yang tidak ada di file dihapus. Yang pernah dipesan hanya diarsipkan.

Opsi: `SKIP_CATALOG=1` (hanya update kode), `SKIP_DEPLOY=1` (hanya katalog), `ASSUME_YES=1` (tanpa tanya).

Pulihkan bila perlu:
`mongorestore --uri='mongodb://localhost:27017' --gzip --archive=/var/backups/collector-parfum/pre-update-XXXX.archive.gz --drop`

## Langkah 2 — DNS domain (panel fastcloud.id → DNS collectorparfum.com)
Ubah **hanya 2 record** ini (klik ikon pensil):

| Name | Type | Value lama | Value BARU | TTL |
|------|------|-----------|-----------|-----|
| `collectorparfum.com.` (@) | A | 123.253.29.4 | **148.230.102.29** | 3600 (boleh 300 agar cepat) |
| `www` | A | 123.253.29.4 | **148.230.102.29** | 3600 |

**JANGAN diubah**, agar email @collectorparfum.com tetap berjalan di fastcloud:
`mail`, `smtp`, `pop`, `ftp` (A 123.253.29.4), `MX 10 mail.collectorparfum.com.`, `TXT v=spf1 … ip4:123.253.29.4 ~all`, dan kedua `NS`.

(Opsional, nanti bila VPS mengirim email via SMTP fastcloud: SPF tidak perlu diubah karena email tetap keluar dari server fastcloud.)

Cek propagasi dari VPS atau komputer (biasanya 5–60 menit):
```bash
dig +short collectorparfum.com @1.1.1.1      # harus 148.230.102.29
dig +short www.collectorparfum.com @1.1.1.1  # harus 148.230.102.29
```

## Langkah 3 — Pasang domain + HTTPS (setelah dig menunjukkan 148.230.102.29)
```bash
cd /home/collector/collector-parfum
sudo DOMAIN=collectorparfum.com SETUP_SSL=yes bash deploy.sh
```
Skrip mengecek DNS lebih dulu. Sertifikat Let's Encrypt (termasuk `www` bila DNS-nya sudah benar) dipasang dan
diperpanjang otomatis. Pilihan ini diingat, jadi update berikutnya cukup `sudo bash deploy.sh`.

## Setelah update
- Beranda › Jelajahi Koleksi › tab **Brand** menampilkan 12 brand dengan produk aktif terbanyak.
  Jumlah & urutannya bisa diatur di **Admin › Konten Situs › Jelajahi Koleksi (heading)**:
  `brand_limit` (0 = semua), `brand_sort` (terbanyak / manual / A–Z). Logo/foto brand diatur di **Admin › Brand**.
- Toko: filter **Momen → Day / Night**. Produk "Day/Night" muncul di keduanya.
- Editor produk: pilihan **Momen** (Day / Night / Day/Night / tidak ada).
