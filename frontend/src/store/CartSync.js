// store/CartSync.js — sinkron keranjang akun lintas perangkat (butir 15).
// Aturan eksplisit:
//  - Saat login: keranjang lokal + keranjang server DIGABUNG per identitas SKU (produk×SKU).
//    Baris yang ada di keduanya memakai jumlah TERBESAR (bukan dijumlah → tak dobel saat sinkron ulang).
//  - Selama login: tiap perubahan keranjang disimpan ke server (debounce 800 ms).
//  - Saat logout: keranjang lokal dikosongkan (perangkat bersama aman); salinan server tetap.
import { useEffect, useRef } from 'react';
import { useAuth } from './AuthContext';
import { useCart } from './CartContext';
import { getServerCart, saveServerCart } from '../services/cart';
import { fetchProductsByIds } from '../services/catalog';

const lineFrom = (product, ref) => {
  const v = (product.variants || []).find((x) => x.sku === ref.sku);
  const vol = (product.volumes || []).find((x) => x.sku === ref.sku);
  if (!v || !vol) return null;
  return {
    key: `${product.id}::${v.sku}`, productId: product.id, slug: product.slug, name: product.name,
    brand: product.brand, category: product.category, image: product.images[0], variantType: vol.type || '',
    variantLabel: Object.values(v.options || {}).join(' · '), options: v.options || {}, sku: v.sku,
    volumeMl: vol.ml, unitPrice: v.price, stock: Number(v.stock), quantity: ref.quantity,
  };
};

export const mergeCarts = (localItems, serverLines) => {
  const map = new Map(localItems.map((i) => [i.key, i]));
  serverLines.forEach((s) => {
    const cur = map.get(s.key);
    map.set(s.key, cur ? { ...cur, quantity: Math.max(cur.quantity, s.quantity) } : s);
  });
  return Array.from(map.values());
};

export default function CartSync() {
  const { user } = useAuth();
  const cart = useCart();
  const syncedFor = useRef(null);
  const uid = user?.id || null;

  useEffect(() => {
    if (!cart._hydrated) return;
    if (!uid) {
      if (syncedFor.current) cart.clear(); // logout → kosongkan lokal
      syncedFor.current = null;
      return;
    }
    if (syncedFor.current === uid) return;
    let active = true;
    (async () => {
      try {
        const server = await getServerCart();
        const refs = (server.items || []).filter((r) => r.sku);
        const products = refs.length ? await fetchProductsByIds(refs.map((r) => r.product_id)) : [];
        const byId = new Map(products.map((p) => [p.id, p]));
        const lines = refs.map((r) => byId.get(r.product_id) && lineFrom(byId.get(r.product_id), r)).filter(Boolean);
        if (!active) return;
        cart.replaceItems(mergeCarts(cart.items, lines));
        syncedFor.current = uid;
      } catch (e) { syncedFor.current = uid; /* offline: tetap pakai lokal */ }
    })();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid, cart._hydrated]);

  useEffect(() => {
    if (!uid || syncedFor.current !== uid) return undefined;
    const t = setTimeout(() => { saveServerCart({ items: cart.items }).catch(() => {}); }, 800);
    return () => clearTimeout(t);
  }, [uid, cart.items]);

  return null;
}
