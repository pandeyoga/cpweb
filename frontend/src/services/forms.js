// services/forms.js — formulir publik yang benar-benar tersimpan di server (kontak & newsletter).
import apiClient, { API } from './apiClient';

export const submitContact = async (payload) => (await apiClient.post(`${API}/contact`, payload)).data;
export const subscribeNewsletter = async (email) => (await apiClient.post(`${API}/newsletter`, { email })).data;
export const listContactMessages = async () => (await apiClient.get(`${API}/admin/contact-messages`)).data;
