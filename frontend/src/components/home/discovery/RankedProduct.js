// Produk ber-ranking (Best Seller) & kurasi (Editor's Picks) — dibungkus di atas ProductCard.
import React from 'react';
import { Feather } from 'lucide-react';
import { ProductCard } from '../../shared/ProductCard';

export const RankedProduct = ({ product, rank, onQuickView }) => (
  <div className="relative pl-10 sm:pl-14 pt-2" data-testid="discovery-ranked-product">
    <span
      aria-hidden
      className="absolute left-0 bottom-14 cp-headline cp-outline-num text-[120px] sm:text-[150px] leading-none select-none"
    >
      {rank}
    </span>
    <div className="relative">
      <ProductCard product={product} onQuickView={onQuickView} />
    </div>
  </div>
);

const noteLine = (p) => {
  const n = p.notes || {};
  return [...(n.top || []), ...(n.heart || [])].slice(0, 3).join(' · ');
};

export const EditorPick = ({ product, index, onQuickView }) => {
  const line = noteLine(product);
  return (
    <div className="relative" data-testid="discovery-editor-pick">
      <div className="mb-2 flex items-center gap-2 px-1">
        <span className="cp-mono text-[9px] tracking-[0.22em] text-[color:var(--cp-market-blue)]">No. {String(index + 1).padStart(2, '0')}</span>
        <span className="h-px flex-1 bg-gradient-to-r from-[rgba(184,155,106,0.6)] to-transparent" />
        <Feather className="h-3 w-3 text-[color:var(--cp-brass)]" />
      </div>
      <ProductCard product={product} onQuickView={onQuickView} />
      {line ? (
        <p className="mt-2 px-1 text-[12px] italic text-black/55 truncate" style={{ fontFamily: "'DM Serif Display', serif" }}>
          “{line}”
        </p>
      ) : null}
    </div>
  );
};
