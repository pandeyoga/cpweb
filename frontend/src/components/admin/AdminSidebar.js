// components/admin/AdminSidebar.js — navigasi admin: grup bisa diciutkan + badge "perlu ditindak".
import React, { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { getNavCounts } from '../../services/admin';
import { adminTestIds as T } from '../../constants/testIds/admin';
import { ACCENT, ACCENT_SOFT } from './adminUi';
import { ADMIN_NAV } from './adminNav';

export { ADMIN_NAV } from './adminNav';

const LS_KEY = 'cp:admin-nav-collapsed:v1';
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');

const useNavCounts = (pathname) => {
  const [counts, setCounts] = useState({});
  useEffect(() => {
    let alive = true;
    const load = () => getNavCounts().then((c) => alive && setCounts(c || {})).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, [pathname]);
  return counts;
};

const useCollapsed = () => {
  const [collapsed, setCollapsed] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (e) { return {}; }
  });
  const toggle = (g) => setCollapsed((c) => {
    const next = { ...c, [g]: !c[g] };
    localStorage.setItem(LS_KEY, JSON.stringify(next));
    return next;
  });
  return [collapsed, toggle];
};

const isActivePath = (pathname, it) => (it.end ? pathname === it.to : pathname === it.to || pathname.startsWith(`${it.to}/`));

const NavItem = ({ it, count, onNavigate }) => {
  const Icon = it.icon;
  return (
    <NavLink
      to={it.to}
      end={it.end}
      onClick={onNavigate}
      data-testid={T.navItem}
      className="group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors hover:bg-muted/60"
      style={({ isActive }) => ({
        backgroundColor: isActive ? ACCENT_SOFT : undefined,
        color: isActive ? ACCENT : undefined,
        fontWeight: isActive ? 600 : 500,
        boxShadow: isActive ? `inset 3px 0 0 ${ACCENT}` : 'none',
      })}
    >
      {({ isActive }) => (
        <>
          <Icon className="h-4 w-4 shrink-0" style={{ color: isActive ? ACCENT : undefined }} />
          <span className="flex-1 truncate">{it.label}</span>
          {count > 0 ? (
            <span className="min-w-[20px] rounded-full px-1.5 py-0.5 text-center text-[10px] font-semibold leading-none text-white"
              style={{ backgroundColor: ACCENT }} data-testid={`admin-nav-badge-${it.badge}`}
              aria-label={`${count} perlu ditindak`}>
              {count > 99 ? '99+' : count}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  );
};

export const AdminSidebar = ({ onNavigate }) => {
  const { pathname } = useLocation();
  const counts = useNavCounts(pathname);
  const [collapsed, toggle] = useCollapsed();
  return (
    <nav className="flex flex-col gap-4 p-4" data-testid={T.sidebar} aria-label="Navigasi admin">
      <div className="px-2 pt-1">
        <div className="font-[\'DM_Serif_Display\',serif] text-lg text-foreground">Collector</div>
        <div className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Admin Panel</div>
      </div>
      {ADMIN_NAV.map((section) => {
        const hasActive = section.items.some((it) => isActivePath(pathname, it));
        const open = hasActive || !collapsed[section.group];
        const pending = section.items.reduce((n, it) => n + (it.badge ? counts[it.badge] || 0 : 0), 0);
        const single = section.items.length === 1;
        return (
          <div key={section.group}>
            {single ? null : (
              <button type="button" onClick={() => toggle(section.group)} aria-expanded={open}
                className="mb-1 flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground hover:text-foreground"
                data-testid={`admin-nav-group-${slug(section.group)}`}>
                <span className="flex-1">{section.group}</span>
                {!open && pending > 0 ? <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: ACCENT }} /> : null}
                <ChevronDown className={`h-3 w-3 transition-transform ${open ? '' : '-rotate-90'}`} />
              </button>
            )}
            {open ? (
              <div className="flex flex-col gap-0.5">
                {section.items.map((it) => (
                  <NavItem key={it.to} it={it} count={it.badge ? counts[it.badge] : 0} onNavigate={onNavigate} />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
};
