// components/admin/adminNav.js — SSOT arsitektur informasi backoffice (menu + judul + breadcrumb).
import {
  LayoutDashboard, Package, FolderTree, Star, ShoppingBag, Ticket, Settings, Wallet,
  BarChart3, Users, FileText, MapPin, Sparkles, DatabaseBackup, Images, Mail, Store,
} from 'lucide-react';

// `badge` = kunci dari GET /api/admin/nav-counts (jumlah yang perlu ditindak).
export const ADMIN_NAV = [
  { group: 'Ringkasan', items: [{ to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true }] },
  {
    group: 'Penjualan',
    items: [
      { to: '/admin/pesanan', label: 'Pesanan', icon: ShoppingBag, badge: 'orders_to_process' },
      { to: '/admin/pembayaran', label: 'Pembayaran', icon: Wallet, badge: 'proofs_pending' },
      { to: '/admin/voucher', label: 'Voucher', icon: Ticket },
    ],
  },
  {
    group: 'Katalog',
    items: [
      { to: '/admin/produk', label: 'Produk', icon: Package },
      { to: '/admin/kategori', label: 'Kategori', icon: FolderTree },
      { to: '/admin/karakter', label: 'Karakter', icon: Sparkles },
      { to: '/admin/brand', label: 'Brand', icon: Store },
    ],
  },
  {
    group: 'Pelanggan',
    items: [
      { to: '/admin/pelanggan', label: 'Pelanggan & Segmen', icon: Users },
      { to: '/admin/ulasan', label: 'Ulasan Produk', icon: Star, badge: 'reviews_pending' },
    ],
  },
  {
    group: 'Toko & Konten',
    items: [
      { to: '/admin/konten', label: 'Konten Situs', icon: FileText },
      { to: '/admin/media', label: 'Media', icon: Images },
      { to: '/admin/lokasi', label: 'Lokasi Toko', icon: MapPin },
    ],
  },
  { group: 'Laporan', items: [{ to: '/admin/analitik', label: 'Analitik', icon: BarChart3 }] },
  {
    group: 'Sistem',
    items: [
      { to: '/admin/pengaturan', label: 'Pengaturan', icon: Settings },
      { to: '/admin/log-email', label: 'Log Email', icon: Mail },
      { to: '/admin/backup', label: 'Backup & Restore', icon: DatabaseBackup },
    ],
  },
];

const findItem = (to) => {
  for (const s of ADMIN_NAV) {
    const it = s.items.find((i) => i.to === to);
    if (it) return { group: s.group, item: it };
  }
  return null;
};

// Sub-halaman (tidak tampil di menu) → induk + judul.
const SUBPAGES = [
  { re: /^\/admin\/produk\/impor$/, parent: '/admin/produk', title: () => 'Impor / Ekspor' },
  { re: /^\/admin\/produk\/baru$/, parent: '/admin/produk', title: () => 'Produk Baru' },
  { re: /^\/admin\/produk\/[^/]+$/, parent: '/admin/produk', title: () => 'Edit Produk' },
  { re: /^\/admin\/pesanan\/([^/]+)$/, parent: '/admin/pesanan', title: (m) => decodeURIComponent(m[1]) },
];

// → { group, title, parent?: {label, to} }
export const crumbsFor = (pathname) => {
  const path = pathname.replace(/\/+$/, '') || '/admin';
  const direct = findItem(path);
  if (direct) return { group: direct.group, title: direct.item.label };
  for (const sp of SUBPAGES) {
    const m = path.match(sp.re);
    if (m) {
      const p = findItem(sp.parent);
      return { group: p.group, title: sp.title(m), parent: { label: p.item.label, to: sp.parent } };
    }
  }
  return { group: 'Admin', title: 'Admin' };
};
