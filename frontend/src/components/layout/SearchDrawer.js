import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search as SearchIcon, X, TrendingUp, CornerDownLeft, Loader2 } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '../ui/sheet';
import { useCatalog } from '../../store/CatalogContext';
import { formatIDR } from '../../lib/format';
import { fetchSearchSuggest } from '../../services/catalog';

const POPULAR = ['Woody', 'Floral', 'Oud', 'Vanilla', 'Citrus', 'YSL', 'Dior', 'Pria'];
const chip = 'px-3 py-1.5 rounded-full border border-black/15 text-sm hover:bg-black/5 transition-colors';
const label = 'cp-mono uppercase text-[11px] tracking-[0.22em] text-black/60 mb-3';

// Saran instan dari server (toleran typo & singkatan brand), debounce 180ms.
const useSuggest = (query) => {
  const [state, setState] = React.useState({ total: 0, products: [], terms: [], didYouMean: null, loading: false });
  React.useEffect(() => {
    const q = query.trim();
    if (!q) { setState({ total: 0, products: [], terms: [], didYouMean: null, loading: false }); return undefined; }
    let active = true;
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      fetchSearchSuggest(q, 6)
        .then((r) => { if (active) setState({ ...r, loading: false }); })
        .catch(() => { if (active) setState({ total: 0, products: [], terms: [], didYouMean: null, loading: false }); });
    }, 180);
    return () => { active = false; clearTimeout(t); };
  }, [query]);
  return state;
};

const ProductRow = ({ p, onPick, testid }) => (
  <Link to={`/parfum/${p.slug}`} onClick={onPick} data-testid={testid}
    className="flex items-center gap-3 p-2 rounded-xl hover:bg-black/5 transition-colors">
    <div className="h-14 w-14 shrink-0 rounded-lg overflow-hidden bg-[color:var(--cp-paper-fog)]">
      <img src={p.images[0]} alt={p.name} className="h-full w-full object-cover" />
    </div>
    <div className="min-w-0">
      <div className="text-sm font-medium truncate">{p.name}</div>
      <div className="cp-mono text-xs text-black/60">{p.tier ? `${p.tier} · ` : ''}{formatIDR(p.priceMin || p.price)}</div>
    </div>
  </Link>
);

const EmptyState = ({ recent, setQuery, trending, close }) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 pt-6">
    <div>
      <div className={label}>Pencarian Terbaru</div>
      {recent.length === 0 ? (
        <div className="text-sm text-black/50">Belum ada pencarian. Coba mulai dari saran di bawah.</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {recent.map((r) => <button key={r} onClick={() => setQuery(r)} className={chip}>{r}</button>)}
        </div>
      )}
      <div className={`${label} mt-6`}>Kata Kunci Populer</div>
      <div className="flex flex-wrap gap-2">
        {POPULAR.map((s) => <button key={s} onClick={() => setQuery(s)} className={chip}>{s}</button>)}
      </div>
    </div>
    <div>
      <div className={`${label} flex items-center gap-2`}><TrendingUp className="h-3.5 w-3.5" /> Trending</div>
      <div className="grid grid-cols-2 gap-3">
        {trending.map((p) => <ProductRow key={p.id} p={p} onPick={close} />)}
      </div>
    </div>
  </div>
);

export const SearchDrawer = ({ open, onOpenChange }) => {
  const { products } = useCatalog();
  const navigate = useNavigate();
  const [query, setQuery] = React.useState('');
  const [recent, setRecent] = React.useState([]);
  const s = useSuggest(query);

  React.useEffect(() => {
    try { setRecent(JSON.parse(localStorage.getItem('cp:recent-search') || '[]')); } catch (e) { setRecent([]); }
  }, [open]);

  const commit = (term) => {
    const t = String(term).trim();
    if (!t) return;
    const next = [t, ...recent.filter((r) => r !== t)].slice(0, 6);
    setRecent(next);
    localStorage.setItem('cp:recent-search', JSON.stringify(next));
  };
  const close = () => onOpenChange(false);
  const goShop = (term) => {
    const t = String(term).trim();
    if (!t) return;
    commit(t); close();
    navigate(`/shop?q=${encodeURIComponent(t)}`);
  };
  const pick = () => { commit(query); close(); };
  const trending = products.filter((p) => p.bestSeller).slice(0, 4);
  const q = query.trim();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="top" data-testid="search-drawer-panel"
        className="cp-store h-[85vh] sm:h-[560px] p-0 cp-glass-panel rounded-b-none overflow-y-auto">
        <SheetHeader className="sr-only">
          <SheetTitle>Cari Produk</SheetTitle>
          <SheetDescription>Ketik nama parfum, brand, singkatan brand, notes, atau kategori. Salah ketik tetap ditemukan.</SheetDescription>
        </SheetHeader>
        <div className="cp-container py-5">
          <div className="flex items-center gap-3 border-b border-black/15 pb-3">
            <SearchIcon className="h-5 w-5 text-black/60" />
            <input autoFocus type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') goShop(query); }}
              placeholder="Cari parfum, brand (mis. YSL), atau notes…" data-testid="search-input"
              className="flex-1 bg-transparent outline-none text-lg sm:text-xl placeholder:text-black/40 py-2" />
            {s.loading ? <Loader2 className="h-4 w-4 animate-spin text-black/40" data-testid="search-loading" /> : null}
            <button onClick={close} className="p-2 rounded-full hover:bg-black/5" aria-label="Tutup"><X className="h-5 w-5" /></button>
          </div>

          {!q ? (
            <EmptyState recent={recent} setQuery={setQuery} trending={trending} close={close} />
          ) : (
            <div className="pt-5 space-y-5">
              {s.didYouMean ? (
                <button onClick={() => setQuery(s.didYouMean)} data-testid="search-did-you-mean"
                  className="text-sm text-black/70">
                  Mungkin maksud Anda: <span className="underline underline-offset-2 font-medium">{s.didYouMean}</span>
                </button>
              ) : null}
              {s.terms.length ? (
                <div data-testid="search-term-suggestions">
                  <div className={label}>Saran</div>
                  <div className="flex flex-wrap gap-2">
                    {s.terms.map((t) => (
                      <button key={`${t.type}-${t.label}`} onClick={() => goShop(t.label)} className={`${chip} inline-flex items-center gap-2`}
                        data-testid={`search-term-${t.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                        {t.label}<span className="cp-mono text-[9px] uppercase tracking-[0.18em] text-black/45">{t.type}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div>
                <div className={`${label} flex items-center gap-3`} data-testid="search-result-count">
                  {s.loading && !s.products.length ? 'Mencari…' : `${s.total} Hasil untuk “${q}”`}
                  {s.total > 0 ? (
                    <button onClick={() => goShop(query)} className="ml-auto inline-flex items-center gap-1 underline normal-case tracking-normal text-[12px]" data-testid="search-see-all">
                      Lihat semua{s.total > s.products.length ? ` (${s.total})` : ''} <CornerDownLeft className="h-3 w-3" />
                    </button>
                  ) : null}
                </div>
                {!s.loading && s.products.length === 0 ? (
                  <div className="text-sm text-black/50" data-testid="search-empty">Tidak ada hasil. Coba kata kunci lain, nama brand, atau notes.</div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {s.products.map((p) => <ProductRow key={p.id} p={p} onPick={pick} testid="search-result-item" />)}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
};
