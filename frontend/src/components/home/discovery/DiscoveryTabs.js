// Selector segmented: pill aktif "meluncur" antar tab (framer-motion layoutId).
import React from 'react';
import { motion } from 'framer-motion';
import { resolveMediaUrl } from '../../../lib/mediaUrl';

export const DiscoveryTabs = ({ tabs, active, onChange }) => (
  <div
    role="tablist"
    aria-label="Pilih cara menjelajah"
    className="cp-noscrollbar inline-flex max-w-full overflow-x-auto rounded-full p-1 gap-1 bg-white border border-black/10 shadow-[0_14px_30px_-18px_rgba(38,28,14,0.35)]"
    data-testid="discovery-tabs"
  >
    {tabs.map((t, i) => {
      const on = t.id === active;
      const Icon = t.icon;
      return (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={on}
          onClick={() => onChange(t.id)}
          data-testid={`discovery-tab-${t.id}`}
          className={`relative shrink-0 rounded-full pl-3 pr-4 sm:pl-4 sm:pr-5 h-11 inline-flex items-center gap-2 transition-colors duration-300 ${
            on ? 'text-[color:var(--cp-paper)]' : 'text-black/70 hover:text-black hover:bg-black/[0.04]'
          }`}
        >
          {on ? (
            <motion.span
              layoutId="discovery-pill"
              className="absolute inset-0 rounded-full bg-[color:var(--cp-ink)] shadow-[0_10px_24px_-10px_rgba(20,20,20,0.55),inset_0_1px_0_rgba(255,255,255,0.12)]"
              transition={{ type: 'spring', stiffness: 420, damping: 34 }}
            />
          ) : null}
          <span className={`relative cp-mono text-[9px] tracking-[0.2em] ${on ? 'text-[color:var(--cp-champagne)]' : 'text-black/40'}`}>
            {String(i + 1).padStart(2, '0')}
          </span>
          {t.iconImage ? (
            <img src={resolveMediaUrl(t.iconImage)} alt="" data-testid={`discovery-tab-${t.id}-icon`} className="relative h-4 w-4 object-contain" />
          ) : <Icon className="relative h-3.5 w-3.5" strokeWidth={1.7} />}
          <span className="relative cp-mono uppercase text-[10px] sm:text-[10.5px] tracking-[0.18em] whitespace-nowrap">{t.label}</span>
        </button>
      );
    })}
  </div>
);
