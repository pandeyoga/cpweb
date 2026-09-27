// services/auth.js — SSOT klien auth (fondasi + E3).
// Token 'sess_' dipasang global via apiClient.setAuthToken (persist localStorage).
import apiClient, { API, setAuthToken, getStoredToken } from './apiClient';

// POST /api/auth/login -> {token, user}
export const login = async (email, password) => {
  const res = await apiClient.post(`${API}/auth/login`, { email, password });
  if (res.data?.token) setAuthToken(res.data.token);
  return res.data.user;
};

// POST /api/auth/register -> {token, user}
export const register = async ({ name, email, password, phone = null }) => {
  const res = await apiClient.post(`${API}/auth/register`, { name, email, password, phone });
  if (res.data?.token) setAuthToken(res.data.token);
  return res.data.user;
};

// GET /api/auth/me -> user (butuh Bearer)
export const fetchMe = async () => {
  const res = await apiClient.get(`${API}/auth/me`);
  return res.data;
};

// POST /api/auth/logout — cabut sesi di server (best-effort), lalu hapus token lokal.
export const logout = () => {
  const token = getStoredToken();
  if (token) {
    apiClient.post(`${API}/auth/logout`, null, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
  }
  setAuthToken(null);
};
