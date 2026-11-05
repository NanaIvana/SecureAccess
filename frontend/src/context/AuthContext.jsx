import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import api, { setSessionExpiredHandler, tokens } from "../api/client";
import { deviceInfo } from "../lib/device";

const AuthContext = createContext(null);
const DEFAULT_THRESHOLDS = { suspect: 0.3, high: 0.6, critical: 0.85 };
// Déconnexion après une période sans activité (US06). Doit correspondre à SESSION_IDLE_MINUTES côté Django.
const IDLE_MINUTES = Number(import.meta.env.VITE_SESSION_IDLE_MINUTES || 15);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS);
  const [lastRisk, setLastRisk] = useState(null);
  const [endReason, setEndReason] = useState("");
  const idleTimer = useRef(null);

  const isAdmin = user?.role === "ADMIN";
  const isSupervisor = isAdmin || user?.role === "RESPONSABLE";

  const loadThresholds = useCallback(async (u) => {
    if (!u || u.role === "UTILISATEUR") return;
    try {
      const { data } = await api.get("/detection/config/");
      setThresholds({ suspect: data.suspect_threshold, high: data.high_risk_threshold, critical: data.critical_threshold });
    } catch { /* valeurs par défaut */ }
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() => { setEndReason("Votre session a expiré. Reconnectez-vous."); setUser(null); });
    if (!tokens.access && !tokens.refresh) { setReady(true); return; }
    api.get("/auth/me/")
      .then(({ data }) => { setUser(data); loadThresholds(data); })
      .catch(() => tokens.clear())
      .finally(() => setReady(true));
  }, [loadThresholds]);

  const finishLogin = useCallback((data) => {
    tokens.set(data.access, data.refresh);
    setUser(data.user);
    setLastRisk(data.risk);
    setEndReason("");
    loadThresholds(data.user);
    return data;
  }, [loadThresholds]);

  /** Étape 1. Retourne soit la session ouverte, soit { two_factor } si une seconde étape est exigée. */
  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login/", { email, password, device: deviceInfo() });
    if (data.two_factor) return data;
    return finishLogin(data);
  }, [finishLogin]);

  /** Étape 2 : code TOTP ou code reçu par e-mail. */
  const verifySecondFactor = useCallback(async (challenge, code) => {
    const { data } = await api.post("/auth/2fa/verify/", { challenge, code });
    return finishLogin(data);
  }, [finishLogin]);

  const logout = useCallback(async (reason = "") => {
    try { await api.post("/auth/logout/", { refresh: tokens.refresh }); } catch { /* ignoré */ }
    tokens.clear();
    setEndReason(reason);
    setUser(null);
  }, []);

  // Minuteur d'inactivité
  useEffect(() => {
    if (!user) return undefined;
    const reset = () => {
      clearTimeout(idleTimer.current);
      idleTimer.current = setTimeout(
        () => logout(`Vous avez été déconnecté après ${IDLE_MINUTES} minutes d'inactivité.`), IDLE_MINUTES * 60000);
    };
    const events = ["mousedown", "keydown", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(idleTimer.current);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [user, logout]);

  const value = useMemo(() => ({
    user, setUser, ready, login, verifySecondFactor, logout, isAdmin, isSupervisor, thresholds, setThresholds,
    lastRisk, setLastRisk, endReason,
  }), [user, ready, login, verifySecondFactor, logout, isAdmin, isSupervisor, thresholds, lastRisk, endReason]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
