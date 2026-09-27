// lib/stock.js — helper stok varian (SSOT tampilan storefront).
// Dipakai keranjang/drawer untuk validasi stok "live" saat menaikkan qty (UX),
// sementara server tetap otoritatif (anti-oversell 409).

// Cari stok varian (type × ml) pada sebuah produk katalog.
// Return angka stok bila ditemukan; null bila produk/varian tak diketahui.
export const variantStock = (product, variantType = '', volumeMl, sku = null) => {
  if (!product) return null;
  const bySku = sku && Array.isArray(product.variants) ? product.variants.find((x) => x.sku === sku) : null;
  if (bySku) return Number.isFinite(Number(bySku.stock)) ? Number(bySku.stock) : null;
  if (!Array.isArray(product.volumes)) return null;
  const v = product.volumes.find(
    (x) =>
      Number(x.ml) === Number(volumeMl) &&
      String(x.type || '') === String(variantType || '')
  );
  if (!v) return null;
  const s = Number(v.stock);
  return Number.isFinite(s) ? s : null;
};

// Stok maksimum efektif untuk sebuah item keranjang.
// Prioritas: stok "live" per SKU dari produk server → snapshot saat add (item.stock) → Infinity.
export const maxStockForItem = (item, liveProduct) => {
  const live = variantStock(liveProduct, item?.variantType, item?.volumeMl, item?.sku);
  if (Number.isFinite(live)) return live;
  const snap = Number(item?.stock);
  return Number.isFinite(snap) ? snap : Infinity;
};
