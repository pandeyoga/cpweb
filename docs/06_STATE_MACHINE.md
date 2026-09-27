# 06 — STATE MACHINE (Order Lifecycle) — Collector Parfum

> SSOT transisi status pesanan. Ditegakkan `scripts/verify_state_machine.py` (grow-with-code).
> Tujuan: cegah RC-E6 (cancel tak balikin stok), RC-E7 (transisi ilegal), RC-E8 (aksi order terminal),
> RC-E4 (payment status drift). Satu fungsi transisi ber-guard — JANGAN update status di banyak tempat.

## 1. Status order (`orders.status`)
```
pending  → order dibuat, menunggu pembayaran
paid     → pembayaran terverifikasi (manual/transfer) / COD dikonfirmasi
packed   → sedang dikemas
shipped  → dikirim (ada resi)
completed→ diterima pelanggan (selesai)
cancelled→ dibatalkan (terminal)
```
Terminal: `completed`, `cancelled` (tak ada transisi keluar).

## 2. Transisi LEGAL (whitelist)
| Dari | Ke yang diizinkan | Guard/efek samping |
|------|-------------------|--------------------|
| pending | paid, cancelled | cancel → **kembalikan stok** (RC-E6) |
| paid | packed, cancelled | cancel → kembalikan stok + tandai refund bila perlu |
| packed | shipped, cancelled | cancel setelah packed = kebijakan admin |
| shipped | completed | tak bisa cancel (barang di jalan) |
| completed | — | terminal |
| cancelled | — | terminal |

Semua transisi di luar tabel → **DITOLAK 400** (RC-E7).

## 3. Aturan pembayaran (`payment_status`: belum_bayar/dp/lunas)
- Derivasi tunggal (INV-5): `paid==0 → belum_bayar`; `0<paid<total → dp`; `paid>=total → lunas`.
- `shipped`/`completed` idealnya `lunas` (kecuali COD yang dilunasi saat terima).
- **DILARANG** menandai `lunas` hanya karena status `completed` tanpa `paid_amount` memadai (RC-E4).
- Menerima pembayaran pada order `cancelled` → **DITOLAK** (RC-E8).

## 4. Efek samping stok (RC-E3/E6)
- Saat order dibuat/paid: stok varian berkurang **atomik** (`$inc` ber-filter `stock>=qty`) → tak oversell.
- Saat `cancelled`: stok **dikembalikan** sejumlah item order (kompensasi).
- Invarian: stok tak pernah negatif (INV-4).

## 5. Skenario gate (verify_state_machine.py)
- **SM1** buat order (stok berkurang) → cancel → order.status=cancelled & stok kembali.
- **SM2** `pending → shipped` (lewati paid) → 400.
- **SM3** bayar/konfirmasi order `cancelled` → 400.
- **SM4** `complete` order belum lunas → payment_status tetap jujur (bukan dipaksa lunas).

> Implementasi transisi diletakkan di `backend/services/orders.py` (`transition_order(order, to_status)`)
> dengan tabel LEGAL_TRANSITIONS sebagai SSOT yang SAMA dengan dokumen ini.

## 6. Aturan tambahan (E14–E16, berlaku sekarang)
- **Compare-and-set**: update status ber-filter `status == dari` → pembatalan paralel hanya
  mengembalikan stok SEKALI (BUG-SALES-02).
- **`pending → paid` hanya dari uang** (`record_payment` via Midtrans webhook / sync / verifikasi bukti
  lama). Admin tidak bisa menandai Dibayar manual untuk order non-COD (BUG-SALES-03). COD sudah dihapus.
- **Kedaluwarsa**: `payment_deadline` = dibuat + `PAYMENT_DEADLINE_HOURS` (24 jam). Cron
  `/api/cron/expire-orders` membatalkan order `pending` lewat batas (cek status Midtrans dulu);
  `cancel_reason="expired"`. Batal (apa pun sebabnya) → stok + kuota voucher kembali (SALES-07).
- **Pelanggan** hanya boleh membatalkan saat `pending` (BUG-SALES-05); sisanya lewat admin.
- **Batal setelah lunas** → admin memakai tombol Refund (koleksi `refunds`, `orders.refunded_amount`);
  uang bersih = `paid_amount − refunded_amount` (SALES-15/16).
- **`packed → shipped`** WAJIB kurir + nomor resi (`services/shipment.py`); email "Pesanan Dikirim"
  sekali per kombinasi kurir+resi, koreksi resi → email "Pembaruan resi".
- **FE tidak menduplikasi tabel**: respons admin order memuat `allowed_transitions` (SALES-18).
