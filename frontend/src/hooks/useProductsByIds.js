// hooks/useProductsByIds.js — ambil produk tepat berdasarkan id dari server (bukan cache 100 pertama).
import { useEffect, useMemo, useState } from 'react';
import { fetchProductsByIds } from '../services/catalog';

export const useProductsByIds = (ids) => {
  const key = useMemo(() => Array.from(new Set((ids || []).filter(Boolean))).sort().join(','), [ids]);
  const [state, setState] = useState({ key: '', items: [], loading: false });

  useEffect(() => {
    if (!key) { setState({ key: '', items: [], loading: false }); return undefined; }
    let active = true;
    setState((s) => ({ ...s, loading: true }));
    fetchProductsByIds(key.split(','))
      .then((items) => { if (active) setState({ key, items, loading: false }); })
      .catch(() => { if (active) setState((s) => ({ ...s, loading: false })); });
    return () => { active = false; };
  }, [key]);

  const byId = useMemo(() => new Map(state.items.map((p) => [p.id, p])), [state.items]);
  return { items: state.items, byId, getById: (id) => byId.get(id) || null, loading: state.loading || state.key !== key };
};
