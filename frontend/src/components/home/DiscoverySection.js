// components/home/DiscoverySection.js — "Jelajahi Koleksi": satu section, 4 cara menjelajah
// (Brand · Character · Editor's Picks · Best Seller). Menggantikan "Temukan karaktermu" + "Sedang Trending".
import React from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, Award, Crown, Sparkles, Store } from 'lucide-react';
import { useCatalog } from '../../store/CatalogContext';
import { useContent } from '../../store/ContentContext';
import { useQuickView } from '../../store/QuickViewContext';
import { AutoCarousel } from '../shared/AutoCarousel';
import { ProductRowSkeleton } from '../shared/Skeletons';
import { Reveal } from '../shared/Reveal';
import { DiscoveryTabs } from './discovery/DiscoveryTabs';
import { BrandTile } from './discovery/BrandTile';
import { CharacterCard } from './discovery/CharacterCard';
import { RankedProduct, EditorPick } from './discovery/RankedProduct';
import { InlineSearch } from './discovery/InlineSearch';
import { useDiscoveryData } from './discovery/useDiscoveryData';

const TABS = [
  { id: 'brand', label: 'Brand', icon: Store, word: 'Brand', to: '/shop' },
  { id: 'character', label: 'Character', icon: Sparkles, word: 'Character', to: '/shop' },
  { id: 'editor', label: "Editor's Picks", icon: Award, word: 'Editor', to: '/shop?sort=rating' },
  { id: 'best', label: 'Best Seller', icon: Crown, word: 'No. 1', to: '/shop?bestSeller=1' },
];
const DEFAULTS = {
  eyebrow: "The Collector's Edit", title: 'Jelajahi dengan', title_accent: 'caramu.',
  subtitle: 'Mulai dari brand favorit, karakter aroma, pilihan editor, atau yang paling dicari minggu ini.',
};
const norm = (s) => String(s || '').toLowerCase();

// Urutan tab Brand (CMS discovery_section.brand_sort); API sudah urut manual→terbanyak.
const BRAND_SORTS = {
  count: (a, b) => (b.count || 0) - (a.count || 0) || a.name.localeCompare(b.name),
  manual: null,
  name: (a, b) => a.name.localeCompare(b.name),
};

// Tanpa pencarian: tampil `limit` teratas (0 = semua); pencarian selalu menelusuri SEMUA item.
const Searchable = ({ items, keyOf, render, placeholder, testId, slideClass, limit = 0, sortFn = null }) => {
  const [q, setQ] = React.useState('');
  const sorted = sortFn ? [...items].sort(sortFn) : items;
  const list = q ? sorted.filter((x) => norm(keyOf(x)).includes(norm(q))) : (limit > 0 ? sorted.slice(0, limit) : sorted);
  return (
    <div className="space-y-5">
      <InlineSearch value={q} onChange={setQ} placeholder={placeholder} testId={testId} total={items.length} shown={list.length} />
      {list.length === 0 ? (
        <div className="py-16 text-center text-sm text-black/55" data-testid={`${testId}-empty`}>Tidak ada yang cocok dengan “{q}”.</div>
      ) : (
        <AutoCarousel key={q} speed={0.5} slideClass={slideClass} testId={`${testId}-carousel`} ariaLabel={placeholder}>
          {list.map(render)}
        </AutoCarousel>
      )}
    </div>
  );
};

const TabBody = ({ tab, brandLimit, brandSort }) => {
  const { characters } = useCatalog();
  const { openQuickView } = useQuickView();
  const { data, error } = useDiscoveryData(tab);
  if (tab === 'character') {
    const items = [...characters].sort((a, b) => (b.count || 0) - (a.count || 0));
    return (
      <Searchable items={items} keyOf={(c) => c.name} placeholder="Cari karakter aroma — mis. woody, fresh…" testId="discovery-character-search"
        slideClass="w-[72%] sm:w-[40%] lg:w-[25%] xl:w-[20%]" render={(c) => <CharacterCard key={c.slug} item={c} />} />
    );
  }
  if (error) return <div className="py-16 text-center text-sm text-black/55" data-testid="discovery-error">Gagal memuat. Coba muat ulang halaman.</div>;
  if (!data) return <ProductRowSkeleton count={5} testId="discovery-loading" />;
  if (tab === 'brand') {
    return (
      <Searchable items={data} limit={brandLimit} sortFn={BRAND_SORTS[brandSort] || BRAND_SORTS.count} keyOf={(b) => b.name} placeholder="Cari brand — mis. Dior, Bvlgari…" testId="discovery-brand-search"
        slideClass="w-[78%] sm:w-[44%] lg:w-[29%] xl:w-[23%]" render={(b) => <BrandTile key={b.name} brand={b} />} />
    );
  }
  const Card = tab === 'best' ? RankedProduct : EditorPick;
  return (
    <AutoCarousel speed={0.55} slideClass="w-[80%] sm:w-[46%] lg:w-[30%] xl:w-[24%]" testId={`discovery-${tab}-carousel`} ariaLabel={tab}>
      {data.map((p, i) => <Card key={p.id} product={p} rank={i + 1} index={i} onQuickView={openQuickView} />)}
    </AutoCarousel>
  );
};

export const DiscoverySection = () => {
  const c = useContent('discovery_section', DEFAULTS);
  const [tab, setTab] = React.useState('brand');
  const reduce = useReducedMotion();
  const tabs = TABS.map((t) => ({ ...t, label: c[`${t.id}_label`] || t.label, iconImage: c[`${t.id}_icon`] || '' }));
  const cur = tabs.find((t) => t.id === tab);
  const motionProps = reduce ? {} : {
    initial: { opacity: 0, y: 18, filter: 'blur(6px)' }, animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
    exit: { opacity: 0, y: -10, filter: 'blur(4px)' }, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  };
  return (
    <section className="relative cp-section-md cp-ambient overflow-hidden" data-testid="home-discovery-section">
      <AnimatePresence mode="wait">
        <motion.span key={cur.word} aria-hidden initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-none absolute right-[-2vw] top-6 cp-headline cp-outline-text text-[22vw] lg:text-[15vw] leading-none whitespace-nowrap select-none">
          {cur.word}
        </motion.span>
      </AnimatePresence>
      <div className="cp-container-wide relative">
        <div className="grid lg:grid-cols-[1fr_auto] gap-6 items-end mb-8 md:mb-10">
          <Reveal>
            <div className="cp-eyebrow cp-eyebrow-line">{c.eyebrow}</div>
            <h2 className="cp-headline mt-3 text-4xl sm:text-5xl lg:text-6xl">
              {c.title} <em className="cp-accent">{c.title_accent}</em>
            </h2>
            <p className="mt-3 max-w-md text-sm text-black/60">{c.subtitle}</p>
          </Reveal>
          <Link to={cur.to} data-testid="discovery-view-all"
            className="group inline-flex items-center gap-2 self-end cp-mono uppercase text-[10px] tracking-[0.22em] rounded-full bg-white border border-black/15 shadow-[0_10px_24px_-18px_rgba(38,28,14,0.4)] px-4 py-2.5 hover:bg-[color:var(--cp-ink)] hover:text-[color:var(--cp-paper)] transition-colors">
            Lihat semua <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
          </Link>
        </div>
        <DiscoveryTabs tabs={tabs} active={tab} onChange={setTab} />
        <div className="mt-7 min-h-[380px]" role="tabpanel" data-testid={`discovery-panel-${tab}`}>
          <AnimatePresence mode="wait">
            <motion.div key={tab} {...motionProps}>
              <TabBody tab={tab} brandLimit={parseInt(c.brand_limit ?? '12', 10) || 0} brandSort={c.brand_sort || 'count'} />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
};
