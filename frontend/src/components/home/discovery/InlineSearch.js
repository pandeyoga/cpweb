import React from 'react';
import { Search, X } from 'lucide-react';

export const InlineSearch = ({ value, onChange, placeholder, testId, total, shown }) => (
  <div className="flex flex-wrap items-center gap-3">
    <label className="rounded-full flex items-center gap-2 pl-4 pr-2 h-11 w-full sm:w-[340px] bg-white border border-black/12 shadow-[0_10px_24px_-18px_rgba(38,28,14,0.4)] focus-within:border-[color:var(--cp-brass)] focus-within:ring-2 focus-within:ring-[rgba(184,155,106,0.3)] transition-shadow">
      <Search className="h-4 w-4 text-black/50 shrink-0" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testId}
        className="relative flex-1 min-w-0 bg-transparent outline-none focus-visible:outline-none text-[13px] placeholder:text-black/45"
      />
      {value ? (
        <button type="button" onClick={() => onChange('')} aria-label="Hapus pencarian" className="relative h-7 w-7 grid place-items-center rounded-full hover:bg-black/5">
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </label>
    <span className="cp-mono uppercase text-[9px] tracking-[0.2em] text-black/55" data-testid={`${testId}-count`}>
      {shown} / {total}
    </span>
  </div>
);
