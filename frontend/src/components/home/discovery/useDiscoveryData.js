// Data discovery dimuat MALAS per tab lalu di-cache (tab lain tak memicu request ulang).
import React from 'react';
import { fetchBrands, fetchProducts } from '../../../services/catalog';

const LOADERS = {
  brand: () => fetchBrands(),
  editor: () => fetchProducts({ sort: 'rating', limit: 10 }).then((r) => r.items),
  best: async () => {
    const r = await fetchProducts({ best_seller: 1, sort: 'best', limit: 10 });
    return r.items.length ? r.items : (await fetchProducts({ sort: 'featured', limit: 10 })).items;
  },
};

export const useDiscoveryData = (tab) => {
  const [cache, setCache] = React.useState({});
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    if (!LOADERS[tab] || cache[tab]) return undefined;
    let active = true;
    setError(null);
    LOADERS[tab]()
      .then((data) => { if (active) setCache((c) => ({ ...c, [tab]: data })); })
      .catch(() => { if (active) setError(tab); });
    return () => { active = false; };
  }, [tab, cache]);

  return { data: cache[tab], error: error === tab };
};
