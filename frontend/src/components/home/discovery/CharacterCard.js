// Kartu karakter aroma: rona warna per karakter + tilt 3D mengikuti kursor → /shop?character=
import React from 'react';
import { Link } from 'react-router-dom';
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from 'framer-motion';
import { getFacetIcon } from '../../../lib/taxonomyIcons';
import { resolveMediaUrl, handleImageError } from '../../../lib/mediaUrl';

const TINTS = [
  [/rose|floral|flower|bunga/, ['#f3dcd6', '#e7b9ae']],
  [/fresh|aqua|marine|citrus|ozon/, ['#dfe9e4', '#b9d3cb']],
  [/green|herb|aromatic|sprout/, ['#e2e6d3', '#c3cca5']],
  [/wood|oud|amber|leather|tobacco|oriental/, ['#ead9c0', '#caa574']],
  [/gourmand|vanilla|sweet|caramel/, ['#f1e0c7', '#dcb68a']],
  [/musk|powder|clean/, ['#ece6e1', '#d4c6bb']],
  [/spic|pepper/, ['#efd5c4', '#d49a78']],
];
const tintFor = (slug) => (TINTS.find(([re]) => re.test(slug || '')) || [null, ['#efe6d6', '#d6c3a3']])[1];

export const CharacterCard = ({ item }) => {
  const reduce = useReducedMotion();
  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);
  const rx = useSpring(useTransform(my, [0, 1], [7, -7]), { stiffness: 220, damping: 18 });
  const ry = useSpring(useTransform(mx, [0, 1], [-9, 9]), { stiffness: 220, damping: 18 });
  const Icon = getFacetIcon(item.icon);
  const [c1, c2] = tintFor(item.slug);
  const photo = resolveMediaUrl(item.image);
  const iconImg = resolveMediaUrl(item.icon_image);

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width);
    my.set((e.clientY - r.top) / r.height);
  };
  const reset = () => { mx.set(0.5); my.set(0.5); };

  return (
    <motion.div style={reduce ? undefined : { rotateX: rx, rotateY: ry, transformPerspective: 900 }} onMouseMove={onMove} onMouseLeave={reset}>
      <Link
        to={`/shop?character=${item.slug}`}
        data-testid="discovery-character-card"
        className="group relative block h-[300px] sm:h-[320px] rounded-[26px] overflow-hidden border border-white/70 shadow-[0_26px_50px_-22px_rgba(38,28,14,0.45)]"
        style={{ background: `radial-gradient(120% 90% at 20% 0%, ${c1} 0%, ${c2} 70%, #b89b6a 140%)` }}
      >
        {photo ? (
          <>
            <img src={photo} alt="" loading="lazy" onError={handleImageError} data-testid="discovery-character-photo"
              className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
            <span aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/25 to-transparent" />
          </>
        ) : null}
        <span aria-hidden className="absolute inset-0 cp-grain opacity-60" />
        <span aria-hidden className="absolute -bottom-16 -right-10 h-56 w-56 rounded-full bg-white/25 blur-2xl transition-transform duration-700 group-hover:scale-125" />
        <span aria-hidden className="cp-sheen" />
        <div className="relative h-full p-5 sm:p-6 flex flex-col">
          <div className="flex items-start justify-between">
            <span className="h-14 w-14 rounded-full grid place-items-center bg-white/55 backdrop-blur-md border border-white/80 text-[color:var(--cp-ink)] shadow-[inset_0_1px_0_#fff,0_10px_20px_-10px_rgba(38,28,14,0.5)] transition-transform duration-500 group-hover:-rotate-12 group-hover:scale-110">
              {iconImg ? <img src={iconImg} alt="" data-testid="discovery-character-icon-image" className="h-7 w-7 object-contain" /> : <Icon className="h-6 w-6" strokeWidth={1.5} />}
            </span>
            <span className="cp-mono text-[9px] uppercase tracking-[0.22em] rounded-full bg-white/50 px-2.5 py-1 text-black/60">
              {item.count || 0} parfum
            </span>
          </div>
          <div className="mt-auto">
            <div className={`cp-mono uppercase text-[9px] tracking-[0.24em] ${photo ? 'text-white/75' : 'text-black/50'}`}>Karakter</div>
            <div className={`cp-headline text-[34px] sm:text-[38px] mt-1 ${photo ? 'text-white' : 'text-[color:var(--cp-ink)]'}`}>{item.name}</div>
            {item.desc ? <p className={`mt-2 text-[12.5px] leading-snug line-clamp-2 ${photo ? 'text-white/80' : 'text-black/60'}`}>{item.desc}</p> : null}
          </div>
        </div>
      </Link>
    </motion.div>
  );
};
