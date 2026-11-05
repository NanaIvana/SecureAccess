import { useCallback, useEffect, useRef, useState } from "react";
import api, { clean, errorMessage } from "../api/client";

/** Charge une ressource GET et la recharge quand l'URL ou les paramètres changent. */
export function useApi(url, params) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(url));
  const [error, setError] = useState("");
  const key = JSON.stringify(clean(params));
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!url) return;
    const n = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const res = await api.get(url, { params: JSON.parse(key) });
      if (n === seq.current) setData(res.data);
    } catch (e) {
      if (n === seq.current) setError(errorMessage(e));
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [url, key]);

  useEffect(() => { load(); }, [load]);
  return { data, setData, loading, error, reload: load };
}

/** Garde les filtres d'une liste dans l'URL (?status=...&page=2). */
export function useQueryState(searchParams, setSearchParams, defaults = {}) {
  const state = { ...defaults, ...Object.fromEntries(searchParams.entries()) };
  const update = (patch, resetPage = true) => {
    const next = { ...state, ...patch };
    if (resetPage && !("page" in patch)) delete next.page;
    setSearchParams(clean(next), { replace: true });
  };
  return [state, update];
}
