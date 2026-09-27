// services/gateway.js — klien pembayaran online Midtrans Snap (E14). Nominal selalu dari server.
import apiClient, { API } from './apiClient';
import { normalizeOrder } from './orders';

const tp = (token) => (token ? { params: { t: token } } : undefined);
const enc = encodeURIComponent;

// GET /api/payments/config -> {enabled, mode: live|mock|off, client_key, snap_js_url}
export const fetchPaymentConfig = async () => (await apiClient.get(`${API}/payments/config`)).data;

// POST /api/orders/{code}/pay -> {token, redirect_url, gateway_order_id, mode}
export const startPayment = async (code, token) =>
  (await apiClient.post(`${API}/orders/${enc(code)}/pay`, {}, tp(token))).data;

// GET /api/orders/{code}/payment-status -> Order (disinkron dgn Midtrans)
export const fetchPaymentStatus = async (code, token) =>
  normalizeOrder((await apiClient.get(`${API}/orders/${enc(code)}/payment-status`, tp(token))).data);

// POST /api/orders/{code}/mock-pay {outcome} -> Order (HANYA mode simulasi)
export const mockPay = async (code, token, outcome) =>
  normalizeOrder((await apiClient.post(`${API}/orders/${enc(code)}/mock-pay`, { outcome }, tp(token))).data);

// Muat snap.js sekali (client key publik). Server key TIDAK pernah ke FE.
let snapPromise = null;
export const loadSnap = (cfg) => {
  if (window.snap) return Promise.resolve(window.snap);
  if (!snapPromise) {
    snapPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = cfg.snap_js_url;
      s.dataset.clientKey = cfg.client_key || '';
      s.onload = () => resolve(window.snap);
      s.onerror = () => { snapPromise = null; reject(new Error('Gagal memuat Midtrans')); };
      document.head.appendChild(s);
    });
  }
  return snapPromise;
};
