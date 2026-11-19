import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("anvexa_access_token");
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
        localStorage.removeItem("anvexa_access_token");
        localStorage.removeItem("anvexa_refresh_token");
        if (window.location.pathname !== "/login") window.location.assign("/login");
      }
      return Promise.reject(error);
    }
    const refreshToken = localStorage.getItem("anvexa_refresh_token");
    if (!refreshToken) return Promise.reject(error);
    try {
      refreshingPromise ||= axios.post(`${API_BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken,
      });
      const response = await refreshingPromise;
      refreshingPromise = null;
      localStorage.setItem("anvexa_access_token", response.data.access_token);
      localStorage.setItem("anvexa_refresh_token", response.data.refresh_token);
      originalRequest.__retried = true;
      originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`;
      return api(originalRequest);
    } catch (refreshError) {
      refreshingPromise = null;
      localStorage.removeItem("anvexa_access_token");
      localStorage.removeItem("anvexa_refresh_token");
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
