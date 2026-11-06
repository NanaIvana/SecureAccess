import axios from "axios";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000/api").replace(/\/+$/, "");

const ACCESS = "sa_access";
const REFRESH = "sa_refresh";

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key, value) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch { /* stockage indisponible */ }
}

export const tokens = {
  get access() { return read(ACCESS); },
  get refresh() { return read(REFRESH); },
  set(access, refresh) { write(ACCESS, access); if (refresh !== undefined) write(REFRESH, refresh); },
  clear() { write(ACCESS, null); write(REFRESH, null); },
};

const api = axios.create({ baseURL: API_URL, timeout: 120000 });

api.interceptors.request.use((config) => {
  const t = tokens.access;
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

// Rafraîchissement automatique du jeton d'accès (durée de vie : 15 min côté Django)
let refreshing = null;
let onSessionExpired = () => {};
export function setSessionExpiredHandler(fn) { onSessionExpired = fn; }

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const isAuthCall = original?.url?.includes("/auth/login") || original?.url?.includes("/auth/refresh");
    if (status === 401 && !original._retry && !isAuthCall && tokens.refresh) {
      original._retry = true;
      try {
        refreshing = refreshing || axios.post(`${API_URL}/auth/refresh/`, { refresh: tokens.refresh });
        const { data } = await refreshing;
        tokens.set(data.access, data.refresh || tokens.refresh);
        original.headers.Authorization = `Bearer ${data.access}`;
        return api(original);
      } catch (e) {
        tokens.clear();
        onSessionExpired();
        return Promise.reject(e);
      } finally {
        refreshing = null;
      }
    }
    if (status === 401 && !isAuthCall) {
      tokens.clear();
      onSessionExpired();
    }
    return Promise.reject(error);
  }
);

/** Transforme une erreur axios en message lisible. */
export function errorMessage(err) {
  if (!err) return "";
  if (!err.response) return "Le serveur ne répond pas. Vérifiez que Django tourne et que l'adresse de l'API est correcte.";
  const d = err.response.data;
  if (typeof d === "string") return `Erreur ${err.response.status}`;
  if (d?.detail) return d.detail;
  if (d && typeof d === "object") {
    return Object.entries(d)
      .map(([k, v]) => `${k === "non_field_errors" ? "" : k + " : "}${Array.isArray(v) ? v.join(" ") : typeof v === "object" ? JSON.stringify(v) : v}`)
      .join(" · ");
  }
  return `Erreur ${err.response.status}`;
}

/** Supprime les paramètres vides avant l'envoi. */
export function clean(params) {
  return Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== "" && v !== null && v !== undefined));
}

export default api;

/** Télécharge un fichier protégé (CSV, PDF) avec le jeton de l'utilisateur. */
export async function download(url, params, fallbackName = "export") {
  const res = await api.get(url, { params: clean(params), responseType: "blob" });
  const disposition = res.headers["content-disposition"] || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const name = match ? match[1] : fallbackName;
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
