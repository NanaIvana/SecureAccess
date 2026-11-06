import { ChevronLeft, KeyRound, Lock, Pencil, Trash2, Unlock } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { errorMessage } from "../api/client";
import EventTable from "../components/EventTable";
import UserForm from "../components/UserForm";
import { Badge, ErrorBox, Field, Loader, Modal, PageHead, Pager, Panel } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useColors } from "../lib/colors";
import { fmtDate, fmtNum } from "../lib/format";
import { LEVELS, WORK_PROFILES } from "../lib/labels";
import { useApi } from "../lib/useApi";

const JUSTIFY = {
  unblock: { title: "Débloquer le compte", button: "Débloquer le compte", done: "Compte débloqué.",
    text: "Le compte redevient utilisable immédiatement. La justification est inscrite au journal d'audit." },
  unlock: { title: "Déverrouiller les sources", button: "Déverrouiller", done: "Sources déverrouillées.",
    text: "Les appareils ou réseaux verrouillés après des échecs répétés peuvent de nouveau se connecter. La justification est inscrite au journal d'audit." },
  reset_2fa: { title: "Réinitialiser la double authentification", button: "Réinitialiser", done: "Double authentification réinitialisée.",
    text: "L'utilisateur devra configurer à nouveau son application d'authentification à la prochaine connexion." },
};

export default function UserDetail() {
  const { id } = useParams();
  const { isAdmin, user: me } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const c = useColors();
  const [sp, setSp] = useSearchParams();
  const page = sp.get("page") || 1;
  const { data, error, reload } = useApi(`/users/${id}/activity/`);
  const events = useApi("/events/", { user: id, page, page_size: 20, level: sp.get("level") || "" });
  const [editing, setEditing] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [minutes, setMinutes] = useState(1440);
  const [justify, setJustify] = useState(null); // { action: "unblock" | "reset_2fa" }
  const [reason, setReason] = useState("");

  const back = <Link className="back" to="/console/utilisateurs"><ChevronLeft size={15} /> Utilisateurs</Link>;
  if (error) return <>{back}<ErrorBox error={error} onRetry={reload} /></>;
  if (!data) return <Loader />;
  const u = data.user;
  const usual = new Set(data.profile.usual_hours);

  async function act(path, body, msg) {
    try {
      await api.post(`/users/${id}/${path}/`, body);
      toast(msg);
      setBlocking(false);
      setJustify(null);
      setReason("");
      reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  async function remove() {
    try {
      await api.delete(`/users/${id}/`);
      toast(`Utilisateur ${u.email} supprimé.`);
      navigate("/console/utilisateurs");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  return (
    <>
      <PageHead
        back={back}
        title={u.full_name || u.email}
        sub={<>{u.email} – {u.role_label}{u.profile_type_label ? ` · ${u.profile_type_label}` : ""}{u.home_city ? `, réside à ${u.home_city}` : ""}</>}
        actions={isAdmin && (
          <>
            <button className="btn" onClick={() => setEditing(true)}><Pencil size={15} /> Modifier</button>
            {u.is_blocked
              ? <button className="btn" onClick={() => setJustify({ action: "unblock" })}><Unlock size={15} /> Débloquer</button>
              : <button className="btn danger" onClick={() => setBlocking(true)}><Lock size={15} /> Bloquer</button>}
            {u.locks?.length > 0 && <button className="btn" onClick={() => setJustify({ action: "unlock" })}><Unlock size={15} /> Déverrouiller</button>}
            {u.two_factor?.enabled && <button className="btn" onClick={() => setJustify({ action: "reset_2fa" })}><KeyRound size={15} /> Réinitialiser la 2FA</button>}
            {u.id !== me.id && <button className="btn ghost" onClick={() => setDeleting(true)} aria-label="Supprimer"><Trash2 size={15} /></button>}
          </>
        )}
      />
      {u.is_blocked && (
        <div className="notice danger" style={{ marginBottom: 16 }}>
          <Lock size={16} /> <span>Compte bloqué jusqu'au {fmtDate(u.blocked_until)}. Toute tentative de connexion est refusée.</span>
        </div>
      )}
      {u.locks?.length > 0 && (
        <div className="notice high" style={{ marginBottom: 16 }}>
          <Lock size={16} />
          <span>{u.locks.length} source(s) verrouillée(s) après des échecs répétés (niveau {Math.max(...u.locks.map((l) => l.level))} sur 3,
            fin au plus tard le {fmtDate(u.locks.map((l) => l.locked_until).sort().at(-1))}). Les autres appareils peuvent toujours se connecter.</span>
        </div>
      )}
      <div className="kpis">
        <div className="kpi"><div className="kpi-label">Connexions</div><div className="kpi-value">{fmtNum(data.stats.total)}</div>
          <span className="kpi-sub">depuis le {fmtDate(data.stats.first)}</span></div>
        <div className="kpi"><div className="kpi-label">Échecs</div><div className="kpi-value">{fmtNum(data.stats.failures)}</div></div>
        <div className="kpi"><div className="kpi-label">Suspectes</div><div className="kpi-value" style={{ color: "var(--warn)" }}>{fmtNum(data.stats.by_level.SUSPECT || 0)}</div></div>
        <div className="kpi"><div className="kpi-label">Haut risque</div><div className="kpi-value" style={{ color: "var(--danger)" }}>{fmtNum(data.stats.by_level.HAUT_RISQUE || 0)}</div></div>
        <div className="kpi"><div className="kpi-label">Appareils connus</div><div className="kpi-value">{fmtNum(data.devices.length)}</div>
          <span className="kpi-sub">dernière connexion {fmtDate(data.stats.last)}</span></div>
      </div>

      <div className="grid grid-main">
        <div className="stack">
          <Panel title="Horaires des connexions réussies" sub={`Profil déclaré : ${WORK_PROFILES[u.work_profile]}. Les barres foncées sont les heures habituelles du profil.`}>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.hours} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="hour" tickFormatter={(h) => `${h}h`} tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} />
                <YAxis tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} allowDecimals={false} />
                <Tooltip contentStyle={{ background: c.surface, border: `1px solid ${c.line}`, color: c.ink }}
                         labelFormatter={(h) => `${h} h UTC`} formatter={(v) => [fmtNum(v), "Connexions"]} />
                <Bar dataKey="count">
                  {data.hours.map((h) => <Cell key={h.hour} fill={usual.has(h.hour) ? c.ink2 : c.warn} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Historique des connexions" flush
                 actions={
                   <select className="input" value={sp.get("level") || ""} aria-label="Filtrer par niveau"
                           onChange={(e) => setSp(e.target.value ? { level: e.target.value } : {})}>
                     <option value="">Tous les niveaux</option>
                     {Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                   </select>
                 }>
            {events.loading && !events.data ? <Loader /> : <EventTable events={events.data?.results} showUser={false} showRules={false} />}
            <Pager data={events.data} page={page} pageSize={20}
                   onPage={(p) => setSp({ ...Object.fromEntries(sp), page: p })} />
          </Panel>
        </div>
        <div className="stack">
          <Panel title="Profil">
            <dl className="facts">
              <dt>Rôle sécurité</dt><dd>{u.role_label}</dd>
              <dt>Profil établissement</dt><dd>{u.profile_type_label || "–"}</dd>
              <dt>État</dt><dd>{u.is_blocked ? <Badge tone="danger">Bloqué</Badge> : u.is_active ? <Badge tone="ok">Actif</Badge> : <Badge>Désactivé</Badge>}</dd>
              <dt>Résidence</dt><dd>{[u.home_city, u.home_country].filter(Boolean).join(", ") || "–"}</dd>
              <dt>Profil horaire</dt><dd>{WORK_PROFILES[u.work_profile]}</dd>
              <dt>Double authentification</dt><dd>{u.two_factor?.enabled ? "Active" : u.two_factor?.required ? "Obligatoire, pas encore configurée" : "Non"}</dd>
              <dt>Pays habituels</dt><dd>{data.profile.usual_countries.join(", ") || "–"}</dd>
              <dt>Créé le</dt><dd>{fmtDate(u.created_at)}</dd>
            </dl>
          </Panel>
          <Panel title="Pays des connexions réussies">
            <div className="bar-list">
              {data.countries.map((r) => (
                <div className="bar-item" key={r.country}>
                  <span>{r.country}</span><strong>{fmtNum(r.n)}</strong>
                  <div className="bar"><i className={r.country !== u.home_country ? "danger" : ""}
                                         style={{ width: `${(r.n / data.countries[0].n) * 100}%` }} /></div>
                </div>
              ))}
              {!data.countries.length && <p className="muted">Aucune connexion réussie.</p>}
            </div>
          </Panel>
          <Panel title="Appareils" flush>
            <table className="data">
              <thead><tr><th>Appareil</th><th className="num">Réussites</th><th>Dernier usage</th></tr></thead>
              <tbody>
                {data.devices.map((d) => (
                  <tr key={d.id}>
                    <td>{d.device_type} {d.os}<div className="muted small">{d.browser}</div></td>
                    <td className="num">{d.successes ? fmtNum(d.successes) : <Badge tone="warn" plain>jamais</Badge>}</td>
                    <td className="small nowrap">{fmtDate(d.last_used)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      </div>

      {editing && <UserForm user={u} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); toast("Modifications enregistrées."); reload(); }} />}
      {blocking && (
        <Modal title="Bloquer le compte" onClose={() => setBlocking(false)}
               footer={<><button className="btn" onClick={() => setBlocking(false)}>Annuler</button>
                 <button className="btn danger" onClick={() => act("block", { minutes }, "Compte bloqué.")}>Bloquer le compte</button></>}>
          <Field label="Durée">
            <select className="input" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
              <option value={30}>30 minutes</option><option value={240}>4 heures</option>
              <option value={1440}>24 heures</option><option value={10080}>7 jours</option>
            </select>
          </Field>
        </Modal>
      )}
      {justify && (
        <Modal title={JUSTIFY[justify.action].title}
               onClose={() => setJustify(null)}
               footer={<>
                 <button className="btn" onClick={() => setJustify(null)}>Annuler</button>
                 <button className="btn primary" disabled={reason.trim().length < 5}
                         onClick={() => act(justify.action, { reason },
                           JUSTIFY[justify.action].done)}>
                   {JUSTIFY[justify.action].button}
                 </button>
               </>}>
          <p style={{ marginBottom: 14 }}>
            {JUSTIFY[justify.action].text}
          </p>
          <Field label="Justification (obligatoire)">
            <textarea className="input" value={reason} onChange={(e) => setReason(e.target.value)}
                      placeholder="Par exemple : identité vérifiée par téléphone avec l'utilisateur." />
          </Field>
        </Modal>
      )}
      {deleting && (
        <Modal title="Supprimer l'utilisateur" onClose={() => setDeleting(false)}
               footer={<><button className="btn" onClick={() => setDeleting(false)}>Annuler</button>
                 <button className="btn danger" onClick={remove}>Supprimer définitivement</button></>}>
          <p>Le compte {u.email} et tout son historique de connexions et d'alertes seront supprimés. Cette action est irréversible.</p>
        </Modal>
      )}
    </>
  );
}
