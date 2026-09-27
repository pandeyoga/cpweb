// Facet banyak nilai (Brand, Character): ketik → pilih. Pilihan tampil sebagai chip.
import React from 'react';
import { Search, X } from 'lucide-react';

const MAX = 8;
const norm = (s) => String(s || '').toLowerCase();

export const FacetSearch = ({ options = [], selected = [], onToggle, placeholder, testId }) => {
  const [q, setQ] = React.useState('');
  const [focus, setFocus] = React.useState(false);
  const [hi, setHi] = React.useState(0);
  const byValue = React.useMemo(() => Object.fromEntries(options.map((o) => [o.value, o])), [options]);
  const pool = options.filter((o) => !selected.includes(o.value));
  const matches = (q ? pool.filter((o) => norm(o.label).includes(norm(q))) : [...pool].sort((a, b) => (b.count || 0) - (a.count || 0))).slice(0, MAX);
  const open = focus || q;

  const pick = (v) => { onToggle(v); setQ(''); setHi(0); };
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(h + 1, matches.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
    else if (e.key === 'Enter' && matches[hi]) { e.preventDefault(); pick(matches[hi].value); }
    else if (e.key === 'Escape') { setQ(''); e.currentTarget.blur(); }
  };

  return (
    <div data-testid={testId}>
      {selected.length ? (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map((v) => (
            <button key={v} type="button" onClick={() => onToggle(v)} data-testid={`${testId}-selected`}
              className="inline-flex items-center gap-1 rounded-full bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] pl-2.5 pr-1.5 py-[5px] text-[11px]">
              {(byValue[v] || {}).label || v} <X className="h-3 w-3 opacity-70" />
            </button>
          ))}
        </div>
      ) : null}
      <label className="flex items-center gap-2 rounded-full border border-black/12 bg-white/50 px-3 h-9 focus-within:border-[color:var(--cp-brass)] focus-within:shadow-[0_0_0_3px_rgba(184,155,106,0.18)] transition-shadow">
        <Search className="h-3.5 w-3.5 text-black/40 shrink-0" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setHi(0); }}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          onKeyDown={onKey}
          placeholder={placeholder}
          data-testid={`${testId}-input`}
          className="flex-1 min-w-0 bg-transparent outline-none focus-visible:outline-none text-[12.5px] placeholder:text-black/40"
        />
      </label>
      {open ? (
        <div className="mt-1.5 rounded-2xl border border-black/10 bg-white/70 backdrop-blur-md p-1 shadow-[0_14px_30px_-16px_rgba(38,28,14,0.35)]" role="listbox" data-testid={`${testId}-options`}>
          {!q ? <div className="px-2.5 pt-1.5 pb-1 cp-mono uppercase text-[8.5px] tracking-[0.2em] text-black/40">Populer</div> : null}
          {matches.length === 0 ? (
            <div className="px-2.5 py-2 text-[12px] text-black/50">Tidak ditemukan</div>
          ) : matches.map((o, i) => (
            <button key={o.value} type="button" role="option" aria-selected={i === hi} data-active={i === hi}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(o.value)} onMouseEnter={() => setHi(i)}
              data-testid={`${testId}-option`}
              className="cp-option w-full flex items-center justify-between gap-2 rounded-xl px-2.5 py-[7px] text-left text-[12.5px]">
              <span className="truncate">{o.label}</span>
              {o.count != null ? <span className="cp-mono text-[9.5px] text-black/40">{o.count}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};
