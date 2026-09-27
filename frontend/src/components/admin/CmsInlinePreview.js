// Pratinjau langsung di editor CMS — merender komponen storefront asli dengan draft (belum dipublish).
import React from 'react';
import { Eye } from 'lucide-react';
import { AnnouncementView, TrustStripView } from '../layout/AnnouncementBar';
import { MarqueeWords } from '../home/MarqueeWords';

const RENDERERS = {
  trust: (d) => <TrustStripView data={d} testId="cms-inline-preview-trust" wide />,
  marquee_words: (d) => <div data-testid="cms-inline-preview-marquee"><MarqueeWords data={d} /></div>,
  announcement: (d) => (
    <div style={{ '--announcement-h': '36px' }}>
      <AnnouncementView data={d} testId="cms-inline-preview-announcement" />
    </div>
  ),
};

export const CmsInlinePreview = ({ sectionKey, draft, dirty }) => {
  const render = RENDERERS[sectionKey];
  if (!render) return null;
  return (
    <div className="mb-4 rounded-lg border border-border/70 overflow-hidden min-w-0 max-w-full" data-testid="cms-inline-preview">
      <div className="flex items-center justify-between px-3 py-1.5 bg-muted/60 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5 uppercase tracking-[0.14em]"><Eye className="h-3.5 w-3.5" /> Pratinjau langsung</span>
        <span data-testid="cms-inline-preview-status">{dirty ? 'Draft — belum dipublish' : 'Sesuai versi tayang'}</span>
      </div>
      <div className="bg-[color:var(--cp-paper,#f6f2ea)] text-[color:var(--cp-ink)] overflow-x-auto">
        <div className={sectionKey === 'trust' ? 'min-w-[720px]' : ''}>{render(draft)}</div>
      </div>
    </div>
  );
};
