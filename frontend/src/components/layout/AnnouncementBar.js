import React from 'react';
import { Link } from 'react-router-dom';
import { MarqueeStrip } from '../shared/MarqueeStrip';
import { useContent } from '../../store/ContentContext';
import { getFacetIcon } from '../../lib/taxonomyIcons';
import { resolveMediaUrl } from '../../lib/mediaUrl';

const ANNOUNCE_DEFAULT = {
  items: [
    'Refill Perfume Distributor Since 1970',
    '3 Cabang di Bandung — Paledang · Pasir Kaliki · Gatot Subroto',
    'Tersedia Ukuran 35 ml · 60 ml · 100 ml',
    'Kirim ke Seluruh Indonesia, Brunei & Malaysia',
    'Same-day Bandung — pembayaran sebelum 10.00 WIB',
  ],
};

export const AnnouncementBar = () => {
  const c = useContent('announcement', ANNOUNCE_DEFAULT);
  const items = (Array.isArray(c.items) && c.items.length ? c.items : ANNOUNCE_DEFAULT.items);
  return (
    <div
      data-testid="announcement-bar"
      className="bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] cp-mono uppercase text-[10px] sm:text-[11px] tracking-[0.2em]"
      style={{ height: 'var(--announcement-h)' }}
    >
      <div className="h-full flex items-center">
        <MarqueeStrip className="w-full" dark speed={c.speed || 'default'} dot={c.separator || '•'} items={items} />
      </div>
    </div>
  );
};

// Sama dengan default content_registry (trust) — tampil sebelum konten CMS termuat.
const TRUST_DEFAULT = {
  items: [
    { title: 'Sejak 1970', desc: 'Pelopor usaha refill parfum di Indonesia.', icon: 'award', to: '/tentang' },
    { title: 'Biang Impor Pilihan', desc: 'Diseleksi teliti sebelum masuk ke rak.', icon: 'shield-check', to: '' },
    { title: '3 Cabang di Bandung', desc: 'Paledang · Pasir Kaliki · Gatot Subroto.', icon: 'map-pin', to: '/lokasi' },
  ],
};
const FALLBACK_ICONS = ['award', 'shield-check', 'map-pin'];

const TrustItem = ({ item, i }) => {
  const Icon = getFacetIcon(item.icon || FALLBACK_ICONS[i % 3]);
  const body = (
    <>
      <span className="h-11 w-11 shrink-0 rounded-full grid place-items-center bg-white border border-black/10 shadow-[0_8px_18px_-12px_rgba(38,28,14,0.45)] text-[color:var(--cp-brass)] transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-105">
        {item.icon_image
          ? <img src={resolveMediaUrl(item.icon_image)} alt="" className="h-5 w-5 object-contain" data-testid="trust-icon-image" />
          : <Icon className="h-5 w-5" strokeWidth={1.6} />}
      </span>
      <div>
        <div className="cp-mono uppercase text-[11px] tracking-[0.22em]">{item.title}</div>
        <div className="text-xs text-black/60">{item.desc}</div>
      </div>
    </>
  );
  const cls = 'group flex items-center gap-4 px-5 sm:px-8 py-5 border-b sm:border-b-0 sm:border-r border-black/10 last:border-r-0';
  return item.to
    ? <Link to={item.to} className={`${cls} hover:bg-white/60 transition-colors`} data-testid={`trust-item-${i}`}>{body}</Link>
    : <div className={cls} data-testid={`trust-item-${i}`}>{body}</div>;
};

export const TrustStrip = () => {
  const c = useContent('trust', TRUST_DEFAULT);
  const items = (Array.isArray(c.items) && c.items.length ? c.items : TRUST_DEFAULT.items);
  const cols = { 1: 'sm:grid-cols-1', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3' }[items.length] || 'sm:grid-cols-2 lg:grid-cols-4';
  return (
    <div className={`grid grid-cols-1 ${cols} border-y border-black/10`} data-testid="trust-strip">
      {items.map((it, i) => <TrustItem key={i} item={it} i={i} />)}
    </div>
  );
};
