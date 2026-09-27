// components/shop/ShopFilters.js — Panel filter katalog: RAMPING + COLLAPSIBLE.
//
// Catatan arsitektur (penting):
// Komponen ini SENGAJA berada di file sendiri, bukan sebagai fungsi lokal di dalam
// ShopPage. Versi lama mendefinisikan `const FiltersPanel = () => (...)` di dalam body
// ShopPage lalu memakainya sebagai <FiltersPanel />, sehingga setiap render menciptakan
// TIPE komponen baru -> React melakukan unmount/mount penuh pada Checkbox/Slider
// (kehilangan fokus, animasi ter-reset). Sekarang identitas komponen stabil sehingga
// state internal (section mana yang terbuka) aman disimpan di sini.
//
// UX: tiap section bisa dibuka/tutup, status diingat di localStorage, section ber-filter aktif
// otomatis terbuka. Brand & Character (banyak nilai) memakai pencarian, bukan deretan tombol.
import React from 'react';
import { Check, ChevronDown, Moon, RotateCcw, SlidersHorizontal, Sun } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../ui/collapsible';
import { FacetSearch } from './FacetSearch';

const OPEN_KEY = 'cp:shop-filter-sections:v3';

// Produk "Day/Night" ikut tampil di kedua filter (disaring di server).
const MOMENTS = [
  { id: 'day', label: 'Day', hint: 'Siang hari', Icon: Sun },
  { id: 'night', label: 'Night', hint: 'Malam hari', Icon: Moon },
];

const DEFAULT_OPEN = {
  kategori: true,
  brand: true,
  character: true,
  datenight: true,
  tier: false,
  tipe: false,
  untuk: false,
};

const readStoredOpen = () => {
  try {
    const raw = window.localStorage.getItem(OPEN_KEY);
    return raw ? { ...DEFAULT_OPEN, ...JSON.parse(raw) } : { ...DEFAULT_OPEN };
  } catch (e) {
    return { ...DEFAULT_OPEN };
  }
};

const CountBadge = ({ n }) =>
  n > 0 ? (
    <span className="cp-mono text-[9px] leading-none h-[15px] min-w-[15px] px-1 inline-flex items-center justify-center rounded-full bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)]">
      {n}
    </span>
  ) : null;

const Section = ({ id, title, count, open, onOpenChange, children }) => (
  <Collapsible open={open} onOpenChange={onOpenChange}>
    <CollapsibleTrigger
      className="w-full flex items-center gap-2 py-[9px] text-left group"
      data-testid={`shop-filter-section-${id}`}
    >
      <span className="cp-mono uppercase text-[9.5px] tracking-[0.2em] text-black/60 group-hover:text-black/85 transition-colors">
        {title}
      </span>
      <CountBadge n={count} />
      <ChevronDown
        className={`ml-auto h-3.5 w-3.5 text-black/35 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      />
    </CollapsibleTrigger>
    <CollapsibleContent className="cp-collapsible">
      <div className="pb-3">{children}</div>
    </CollapsibleContent>
  </Collapsible>
);

const Chip = ({ active, onClick, testId, children }) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    data-testid={testId}
    className={`cp-mono uppercase text-[9px] leading-none tracking-[0.16em] px-2.5 py-[7px] rounded-full border transition-colors ${
      active
        ? 'bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] border-[color:var(--cp-ink)]'
        : 'border-black/12 text-black/65 hover:bg-black/5 hover:text-black/85'
    }`}
  >
    {children}
  </button>
);

const CheckRow = ({ active, onClick, testId, children }) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    data-testid={testId}
    className="w-full flex items-center gap-2 py-[5px] text-left group"
  >
    <span
      className={`h-[15px] w-[15px] shrink-0 rounded-[4px] border flex items-center justify-center transition-colors ${
        active
          ? 'bg-[color:var(--cp-ink)] border-[color:var(--cp-ink)]'
          : 'border-black/25 group-hover:border-black/45'
      }`}
    >
      {active ? <Check className="h-2.5 w-2.5 text-[color:var(--cp-paper)]" strokeWidth={3} /> : null}
    </span>
    <span className={`text-[12.5px] leading-tight truncate ${active ? 'text-black/90 font-medium' : 'text-black/70'}`}>
      {children}
    </span>
  </button>
);

export const ShopFilters = ({
  variant = 'sidebar',
  categories = [],
  characters = [],
  brandOptions = [],
  tierOptions = [],
  typeOptions = [],
  types = [],
  genderOptions = [],
  cats = [],
  brands = [],
  occ = [],
  chars = [],
  concs = [],
  genders = [],
  onToggle,
  onReset,
  onApply,
}) => {
  const counts = {
    kategori: cats.length,
    brand: brands.length,
    character: chars.length,
    datenight: occ.length,
    tier: concs.length,
    tipe: types.length,
    untuk: genders.length,
  };
  const activeTotal = Object.values(counts).reduce((a, b) => a + b, 0);

  // Initializer hanya jalan sekali: section dengan filter aktif (mis. dari URL) dibuka.
  const [open, setOpen] = React.useState(() => {
    const base = readStoredOpen();
    Object.keys(counts).forEach((k) => {
      if (counts[k] > 0) base[k] = true;
    });
    return base;
  });

  const setSection = (id) => (value) => {
    setOpen((prev) => {
      const next = { ...prev, [id]: value };
      try {
        window.localStorage.setItem(OPEN_KEY, JSON.stringify(next));
      } catch (e) {
        /* localStorage bisa diblokir — abaikan */
      }
      return next;
    });
  };

  const header = (
    <div className="flex items-center gap-2 pb-1.5">
      <SlidersHorizontal className="h-3.5 w-3.5 text-black/45" />
      <span className="cp-mono uppercase text-[9.5px] tracking-[0.22em] text-black/70">Filter</span>
      <CountBadge n={activeTotal} />
      <button
        type="button"
        onClick={onReset}
        data-testid="shop-clear-filters"
        className="ml-auto inline-flex items-center gap-1 cp-mono uppercase text-[9px] tracking-[0.18em] text-black/45 hover:text-black/85 transition-colors"
      >
        <RotateCcw className="h-3 w-3" /> Reset
      </button>
    </div>
  );

  const body = (
    <div className="divide-y divide-black/10">
      <Section
        id="kategori"
        title="Kategori Aroma"
        count={counts.kategori}
        open={open.kategori}
        onOpenChange={setSection('kategori')}
      >
        <div className="space-y-0.5">
          {categories.map((c) => (
            <CheckRow
              key={c.slug}
              active={cats.includes(c.slug)}
              onClick={() => onToggle('cat', c.slug)}
              testId={`shop-filter-cat-${c.slug}`}
            >
              {c.name}
            </CheckRow>
          ))}
        </div>
      </Section>

      <Section id="brand" title="Brand" count={counts.brand} open={open.brand} onOpenChange={setSection('brand')}>
        <FacetSearch
          options={brandOptions.map((b) => ({ value: b.name, label: b.name, count: b.count }))}
          selected={brands}
          onToggle={(v) => onToggle('brand', v)}
          placeholder="Cari brand…"
          testId="shop-filter-brand"
        />
      </Section>

      <Section id="character" title="Character" count={counts.character} open={open.character} onOpenChange={setSection('character')}>
        <FacetSearch
          options={characters.map((c) => ({ value: c.slug, label: c.name, count: c.count }))}
          selected={chars}
          onToggle={(v) => onToggle('character', v)}
          placeholder="Cari karakter aroma…"
          testId="shop-filter-character"
        />
      </Section>

      <Section id="datenight" title="Momen" count={counts.datenight} open={open.datenight} onOpenChange={setSection('datenight')}>
        <div className="grid grid-cols-2 gap-1.5">
          {MOMENTS.map(({ id, label, hint, Icon }) => {
            const on = occ.includes(id);
            return (
              <button
                key={id}
                type="button"
                onClick={() => onToggle('occasion', id)}
                aria-pressed={on}
                data-testid={`shop-filter-${id}`}
                className={`flex items-center gap-2 rounded-2xl border px-3 py-2.5 text-left transition-colors ${
                  on ? 'bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] border-[color:var(--cp-ink)]' : 'border-black/12 hover:bg-black/5'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" strokeWidth={1.6} />
                <span>
                  <span className="block text-[12.5px] font-medium">{label}</span>
                  <span className={`block text-[10px] ${on ? 'opacity-70' : 'text-black/50'}`}>{hint}</span>
                </span>
              </button>
            );
          })}
        </div>
      </Section>

      <Section id="tier" title="Tier" count={counts.tier} open={open.tier} onOpenChange={setSection('tier')}>
        <div className="flex flex-wrap gap-1.5">
          {tierOptions.map((t) => (
            <Chip key={t} active={concs.includes(t)} onClick={() => onToggle('tier', t)} testId={`shop-filter-tier-${t.toLowerCase()}`}>
              {t}
            </Chip>
          ))}
        </div>
      </Section>

      <Section id="tipe" title="Tipe" count={counts.tipe} open={open.tipe} onOpenChange={setSection('tipe')}>
        <div className="flex flex-wrap gap-1.5">
          {typeOptions.map((t) => (
            <Chip key={t} active={types.includes(t)} onClick={() => onToggle('tipe', t)} testId={`shop-filter-tipe-${t.toLowerCase()}`}>
              {t}
            </Chip>
          ))}
        </div>
      </Section>

      <Section id="untuk" title="Untuk" count={counts.untuk} open={open.untuk} onOpenChange={setSection('untuk')}>
        <div className="flex flex-wrap gap-1.5">
          {genderOptions.map((g) => (
            <Chip
              key={g}
              active={genders.includes(g)}
              onClick={() => onToggle('gender', g)}
              testId={`shop-filter-gender-${g.toLowerCase()}`}
            >
              {g}
            </Chip>
          ))}
        </div>
      </Section>

    </div>
  );

  if (variant === 'sheet') {
    // Di dalam Sheet, judul "Filter" sudah ada di SheetHeader -> jangan duplikat header.
    return (
      <div data-testid="shop-filters-sheet-panel">
        {body}
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onReset}
            className="h-11 rounded-full border border-black/15 cp-mono uppercase text-[10px] tracking-[0.2em] hover:bg-black/5"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={onApply}
            data-testid="shop-apply-filters"
            className="h-11 rounded-full cp-btn-gold cp-mono uppercase text-[10px] tracking-[0.2em]"
          >
            Terapkan
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cp-glass rounded-[18px] px-3.5 py-2.5" data-testid="shop-filters-panel">
      {header}
      {body}
    </div>
  );
};
