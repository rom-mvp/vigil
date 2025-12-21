import axios from "axios";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL ?? "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("jwt");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const fetchActivity = () => api.get("/api/v1/activity/latest");
export const fetchAuditLogs = () => api.get("/api/v1/audit/logs");
export const updatePolicy = (body: unknown) => api.post("/api/v1/policies/update", body);

export default api;
