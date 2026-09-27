// lib/variants.js — helper VARIAN N-dimensi (frontend). Cerminan services/variants.py.
// Produk (setelah normalizeProduct) punya: options:[{name,values[]}], variants:[{sku,options,price,stock,compare_at_price}],
// priceMin/priceMax (+ compareAtMin/Max). volumes[] tetap ada (legacy) untuk fallback.

export const SIZE_HINTS = ['ukuran', 'size', 'ml', 'volume'];

export const isSizeDim = (name = '') => {
  const n = String(name).toLowerCase();
  return SIZE_HINTS.some((h) => n.includes(h));
};

export const parseMl = (val) => {
  const m = String(val ?? '').match(/\d+/);
  return m ? parseInt(m[0], 10) : 0;
};

export const sizeDimName = (options = []) => (options.find((o) => isSizeDim(o.name)) || {}).name || null;

export const compositeType = (opts = {}, options = []) =>
  options.filter((o) => !isSizeDim(o.name)).map((o) => opts[o.name]).filter(Boolean).join(' / ');

export const variantLabel = (opts = {}, options = []) =>
  options.map((o) => opts[o.name]).filter(Boolean).join(' / ');

// Cari varian yang cocok PERSIS dengan seleksi dimensi `sel`.
export const findVariant = (product, sel = {}) =>
  (product.variants || []).find((v) =>
    (product.options || []).every((o) => (v.options || {})[o.name] === sel[o.name])
  ) || null;

// Varian awal untuk seleksi (prioritas ada stok, lalu termurah, lalu pertama).
export const firstVariant = (product) => {
  const vs = product.variants || [];
  if (!vs.length) return null;
  const inStock = vs.filter((v) => (v.stock || 0) > 0);
  const pool = inStock.length ? inStock : vs;
  return pool.reduce((b, v) => (!b || (v.price || 0) < (b.price || 0) ? v : b), null);
};

// Varian termurah yang MASIH ADA STOK (null bila semua habis) — dipakai tombol cepat kartu.
export const cheapestInStock = (product) =>
  (product.variants || []).filter((v) => (v.stock || 0) > 0)
    .reduce((b, v) => (!b || (v.price || 0) < (b.price || 0) ? v : b), null);

export const productMetaLine = (product) => [product.tier, product.gender].filter(Boolean).join(' · ');

export const cheapestVariant = (product) =>
  (product.variants || []).reduce((b, v) => (!b || (v.price || 0) < (b.price || 0) ? v : b), null);

// Objek "volume" yang diterima CartContext.addItem (kompat + membawa sku/options/label).
export const toCartVolume = (product, variant) => {
  if (!variant) return null;
  const options = product.options || [];
  return {
    sku: variant.sku,
    ml: parseMl((variant.options || {})[sizeDimName(options)]),
    price: variant.price,
    stock: variant.stock,
    type: compositeType(variant.options || {}, options),
    options: variant.options || {},
    label: variantLabel(variant.options || {}, options),
    compare_at_price: variant.compare_at_price ?? null,
  };
};

// Range harga untuk kartu/PDP.
// Saat filter Tipe aktif, API mengirim type_price_min/max → harga tipe terpilih (kontrak v2).
export const priceRange = (product) => {
  const min = product.type_price_min ?? product.priceMin ?? product.price_min ?? product.price ?? 0;
  const max = product.type_price_max ?? product.priceMax ?? product.price_max ?? product.price ?? 0;
  return { min, max, hasRange: max > min };
};
