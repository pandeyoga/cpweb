import React from 'react';
import { MarqueeStrip } from '../shared/MarqueeStrip';

export const STRIP_ITEMS = ['ELEGAN', 'BERKARAKTER', 'REFILL', 'SEJAK 1970', 'MEMBEKAS', 'BANDUNG'];

const MARQUEE_BG = {
  light: 'bg-[color:var(--cp-paper-fog)]',
  dark: '',
  brass: 'bg-[color:var(--cp-champagne)]',
};

// Marquee kata berjalan Beranda (key CMS `marquee_words`) — dipakai storefront & pratinjau CMS.
export const MarqueeWords = ({ data }) => (
  <MarqueeStrip
    items={Array.isArray(data.items) && data.items.length ? data.items : STRIP_ITEMS}
    speed={data.speed || 'default'}
    dot={data.separator || '•'}
    dotImage={data.separator_image}
    dark={data.style === 'dark'}
    className={`border-y border-black/10 ${data.style in MARQUEE_BG ? MARQUEE_BG[data.style] : MARQUEE_BG.light}`}
  />
);
