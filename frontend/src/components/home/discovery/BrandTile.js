// Kartu brand: monogram + kipas 3 botol yang melebar saat hover → /shop?brand=
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import { bottleImage } from '../../../lib/bottleArt';
import { resolveMediaUrl, handleImageError } from '../../../lib/mediaUrl';

const FAN = [
  'group-hover:-translate-x-[58%] group-hover:-rotate-[14deg] -translate-x-[34%] -rotate-[8deg]',
  'group-hover:-translate-y-3 z-[2]',
  'group-hover:translate-x-[58%] group-hover:rotate-[14deg] translate-x-[34%] rotate-[8deg]',
];

const imagesFor = (b) => {
  const real = (b.images || []).map(resolveMediaUrl).filter(Boolean);
  const names = b.sample && b.sample.length ? b.sample : [b.name];
  const out = [...real];
  for (let i = 0; out.length < 3; i += 1) out.push(bottleImage({ name: names[i % names.length], variant: i }));
  return out.slice(0, 3);
};

const Fan = ({ brand }) => (
  <>
    <span aria-hidden className="absolute bottom-3 h-6 w-2/3 rounded-[50%] bg-black/15 blur-xl" />
    {imagesFor(brand).map((src, i) => (
      <img
        key={i}
        src={src}
        alt=""
        loading="lazy"
        onError={handleImageError}
        className={`absolute bottom-2 h-[82%] aspect-[4/5] object-cover rounded-2xl border border-white/70 shadow-[0_18px_34px_-14px_rgba(38,28,14,0.45)] transition-transform duration-500 ease-out ${FAN[i]}`}
      />
    ))}
  </>
);

export const BrandTile = ({ brand }) => {
  const cover = resolveMediaUrl(brand.image);
  const logo = resolveMediaUrl(brand.logo);
  return (
    <Link
      to={`/shop?brand=${encodeURIComponent(brand.name)}`}
      data-testid="discovery-brand-tile"
      className="group relative block cp-card-solid rounded-[26px] p-4 sm:p-5 overflow-hidden"
    >
      {!logo ? (
        <span aria-hidden style={{ color: 'rgba(184,155,106,0.18)' }} className="absolute right-5 top-2 cp-headline text-[110px] leading-none select-none transition-transform duration-700 group-hover:-translate-x-2">
          {brand.name.trim()[0]}
        </span>
      ) : null}
      <div className={`relative h-[190px] sm:h-[210px] flex items-end justify-center ${cover ? 'rounded-[18px] overflow-hidden' : ''}`}>
        {cover ? (
          <img src={cover} alt={brand.name} loading="lazy" onError={handleImageError} data-testid="discovery-brand-cover"
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
        ) : <Fan brand={brand} />}
        {logo ? (
          <span className="absolute left-3 top-3 h-14 min-w-14 max-w-[60%] px-3 rounded-2xl bg-white/90 backdrop-blur-md border border-black/[0.06] shadow-[0_10px_24px_-12px_rgba(38,28,14,0.45)] grid place-items-center">
            <img src={logo} alt={`${brand.name} logo`} loading="lazy" onError={handleImageError} data-testid="discovery-brand-logo" className="max-h-9 max-w-full object-contain" />
          </span>
        ) : null}
      </div>
      <div className="relative mt-4 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="cp-mono uppercase text-[9px] tracking-[0.22em] text-black/45">{brand.count} parfum</div>
          <div className="cp-headline text-[24px] sm:text-[26px] mt-1 truncate">{brand.name}</div>
          {brand.desc ? <p className="text-[12px] text-black/55 truncate">{brand.desc}</p> : null}
        </div>
        <span className="shrink-0 h-9 w-9 rounded-full bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] grid place-items-center transition-transform duration-300 group-hover:rotate-45">
          <ArrowUpRight className="h-4 w-4" />
        </span>
      </div>
    </Link>
  );
};
