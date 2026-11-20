import axios from "axios";
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "./authStorage";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD ? "" : "http://127.0.0.1:8000/api/v1")
).replace(/\/$/, "");

if (import.meta.env.PROD && !API_BASE_URL) {
  throw new Error(
    "VITE_API_BASE_URL must be configured for production builds.",
  );
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshingPromise = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status !== 401 || originalRequest?.__retried) {
      if (error.response?.status === 401) {
        clearAuthTokens();
        if (window.location.pathname !== "/login") window.location.assign("/login");
      }
      return Promise.reject(error);
    }
    const refreshToken = getRefreshToken();
    if (!refreshToken) return Promise.reject(error);
    try {
      refreshingPromise ||= axios.post(`${API_BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken,
      });
      const response = await refreshingPromise;
      refreshingPromise = null;
      setAccessToken(response.data.access_token);
      setRefreshToken(response.data.refresh_token);
      originalRequest.__retried = true;
      originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`;
      return api(originalRequest);
    } catch (refreshError) {
      refreshingPromise = null;
      clearAuthTokens();
      if (window.location.pathname !== "/login") window.location.assign("/login");
      return Promise.reject(refreshError);
    }
  },
);

export function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(", ");
  return error?.message || "The request could not be completed.";
}

export default api;
