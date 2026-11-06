// Coquille de l'application : barre latérale selon l'espace (client ou console) et le rôle.
import {
  Activity, Bell, BellRing, FileText, Gauge, History, Lock, LogOut, Menu, ScrollText, ShieldCheck,
  SlidersHorizontal, UserRound, Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../lib/labels";

function Logo() {
  return (
    <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4f46e5" /><stop offset="1" stopColor="#0d9488" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#lg)" />
      <path d="M16 6l8 3v6c0 5-3.4 9-8 11-4.6-2-8-6-8-11V9l8-3z" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      <circle cx="16" cy="15" r="2.6" fill="#fcd34d" />
    </svg>
  );
}

function Item({ to, icon: Icon, color, children, end, count }) {
  return (
    <NavLink to={to} end={end}>
      <span className={`ico ${color}`}><Icon size={16} /></span>
      <span>{children}</span>
      {count > 0 && <span className="count">{count > 999 ? "999+" : count}</span>}
    </NavLink>
  );
}

export default function Layout({ space }) {
  const { user, logout, isAdmin } = useAuth();
  const [open, setOpen] = useState(false);
  const [openAlerts, setOpenAlerts] = useState(0);
  const [unread, setUnread] = useState(0);
  const location = useLocation();
  const console_ = space === "console";

  useEffect(() => setOpen(false), [location.pathname]);

  // Compteur des alertes ouvertes (administrateur), rafraîchi toutes les 30 secondes
  useEffect(() => {
    if (!isAdmin) return undefined;
    let stop = false;
    const tick = () => api.get("/alerts/counts/", { params: { open: true } })
      .then(({ data }) => !stop && setOpenAlerts(Number(data.open ?? ((data.by_status.NOUVELLE || 0) + (data.by_status.EN_COURS || 0)))))
      .catch(() => {});
    tick();
    const id = setInterval(tick, 30000);
    return () => { stop = true; clearInterval(id); };
  }, [isAdmin]);

  // Notifications personnelles (toutes les minutes, et après chaque réponse)
  useEffect(() => {
    let stop = false;
    const tick = () => api.get("/notifications/unread/").then(({ data }) => !stop && setUnread(data.unread)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    window.addEventListener("sa:notifications", tick);
    return () => { stop = true; clearInterval(id); window.removeEventListener("sa:notifications", tick); };
  }, []);

  const base = console_ ? "/console" : "/espace";

  return (
    <div className={`shell ${space}`}>
      <aside className={`side${open ? " open" : ""}`} aria-label="Navigation principale">
        <div className="brand">
          <Logo />
          <div><strong>SecureAccess</strong><small>Protection des connexions</small></div>
        </div>
        <div className="space-tag">
          {console_ ? (isAdmin ? "Console d'administration" : "Console (lecture seule)") : "Mon espace sécurité"}
        </div>
        <nav className="nav">
          {console_ ? (
            <>
              <Item to="/console" end icon={Gauge} color="c-indigo">Tableau de bord</Item>
              {isAdmin && (
                <>
                  <Item to="/console/alertes" icon={BellRing} color="c-red" count={openAlerts}>Alertes</Item>
                  <Item to="/console/connexions" icon={Activity} color="c-sky">Connexions</Item>
                  <Item to="/console/utilisateurs" icon={Users} color="c-violet">Comptes</Item>
                </>
              )}
              <Item to="/console/rapport" icon={FileText} color="c-teal">Rapport de synthèse</Item>
              {isAdmin && (
                <>
                  <div className="nav-group">Détection</div>
                  <Item to="/console/detection" icon={SlidersHorizontal} color="c-amber">Règles et modèle</Item>
                </>
              )}
              <div className="nav-group">Conformité</div>
              <Item to="/console/protection" icon={Lock} color="c-green">Mesures de protection</Item>
              {isAdmin && <Item to="/console/audit" icon={ScrollText} color="c-slate">Journal d'audit</Item>}
            </>
          ) : (
            <>
              <Item to="/espace" end icon={ShieldCheck} color="c-teal">Ma sécurité</Item>
            </>
          )}
          <div className="nav-group">Mon compte</div>
          <Item to={`${base}/connexions-perso`} icon={History} color="c-sky">Mes connexions</Item>
          <Item to={`${base}/notifications`} icon={Bell} color="c-amber" count={unread}>Notifications</Item>
          <Item to={`${base}/compte`} icon={UserRound} color="c-violet">Mon compte</Item>
        </nav>
        <div className="side-foot">
          <div className="who" title={user?.email}>{user?.full_name || user?.email}</div>
          <div className="role">{ROLES[user?.role]}{user?.profile_type_label ? `, ${user.profile_type_label.toLowerCase()}` : ""}</div>
          <button className="btn ghost sm" onClick={() => logout()}><LogOut size={15} /> Se déconnecter</button>
        </div>
      </aside>
      <div className="main">
        <div className="topbar">
          <button className="btn sm" onClick={() => setOpen(!open)} aria-label="Ouvrir le menu"><Menu size={16} /></button>
          <strong>SecureAccess</strong>
        </div>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
