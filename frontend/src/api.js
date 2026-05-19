import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api`;
export const PUBLIC_BASE = `${BACKEND_URL}/api/public`;

export const api = axios.create({
  baseURL: API_BASE,
});

export function setAuthHeader(token) {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    localStorage.setItem("db_token", token);
  } else {
    delete api.defaults.headers.common["Authorization"];
    localStorage.removeItem("db_token");
  }
}

const saved = typeof window !== "undefined" ? localStorage.getItem("db_token") : null;
if (saved) {
  api.defaults.headers.common["Authorization"] = `Bearer ${saved}`;
}

export function formatErr(detail) {
  if (detail == null) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
