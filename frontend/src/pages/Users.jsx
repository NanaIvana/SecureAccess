import { UserPlus } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import UserForm from "../components/UserForm";
import { Badge, Empty, ErrorBox, Field, Loader, PageHead, Pager, UserCell } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDate, fmtNum } from "../lib/format";
import { ROLES, WORK_PROFILES } from "../lib/labels";
import { useApi, useQueryState } from "../lib/useApi";

export default function Users() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useQueryState(sp, setSp);
  const [creating, setCreating] = useState(false);
  const { data, loading, error, reload } = useApi("/users/", {
    page: q.page, search: q.search, role: q.role, blocked: q.blocked, ordering: q.ordering || "-risky_count",
  });

  return (
    <>
      <PageHead title="Utilisateurs" sub="Comptes surveillés, leur profil habituel et le nombre de connexions à risque."
                actions={isAdmin && <button className="btn primary" onClick={() => setCreating(true)}><UserPlus size={15} /> Nouvel utilisateur</button>} />
      <section className="panel">
        <div className="filters">
          <Field label="Recherche" className="grow">
            <input key={q.search || ""} className="input" type="search" placeholder="E-mail, nom, ville…" defaultValue={q.search || ""}
                   onKeyDown={(e) => e.key === "Enter" && setQ({ search: e.currentTarget.value })}
                   onBlur={(e) => e.currentTarget.value !== (q.search || "") && setQ({ search: e.currentTarget.value })} />
          </Field>
          <Field label="Rôle">
            <select className="input" value={q.role || ""} onChange={(e) => setQ({ role: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="État">
            <select className="input" value={q.blocked || ""} onChange={(e) => setQ({ blocked: e.target.value })}>
              <option value="">Tous</option><option value="true">Bloqués</option>
            </select>
          </Field>
          <Field label="Tri">
            <select className="input" value={q.ordering || "-risky_count"} onChange={(e) => setQ({ ordering: e.target.value })}>
              <option value="-risky_count">Connexions à risque</option>
              <option value="-events_count">Nombre de connexions</option>
              <option value="email">E-mail</option>
              <option value="-last_login">Dernière connexion</option>
            </select>
          </Field>
        </div>
        <div style={{ padding: error ? 14 : 0 }}><ErrorBox error={error} onRetry={reload} /></div>
        {!data && loading ? <Loader /> : !data?.results.length ? <Empty title="Aucun utilisateur trouvé." /> : (
          <div className="table-wrap" style={{ opacity: loading ? 0.6 : 1 }}>
            <table className="data">
              <thead><tr><th>Utilisateur</th><th>Rôle</th><th>Ville</th><th>Profil horaire</th><th className="num">Connexions</th><th className="num">À risque</th><th>État</th><th>2FA</th><th>Dernière connexion</th></tr></thead>
              <tbody>
                {data.results.map((u) => (
                  <tr key={u.id} className="click" onClick={() => navigate(`/console/utilisateurs/${u.id}`)}>
                    <td><UserCell user={u} /></td>
                    <td>{u.role_label}</td>
                    <td>{u.home_city || "–"}</td>
                    <td>{WORK_PROFILES[u.work_profile]}</td>
                    <td className="num">{fmtNum(u.events_count)}</td>
                    <td className="num">{u.risky_count ? <strong style={{ color: "var(--danger)" }}>{fmtNum(u.risky_count)}</strong> : 0}</td>
                    <td>{u.is_blocked ? <Badge tone="danger">Bloqué</Badge> : u.is_active ? <Badge tone="ok">Actif</Badge> : <Badge>Désactivé</Badge>}</td>
                    <td>{u.two_factor?.enabled ? <Badge tone="ok" plain>Active</Badge> : u.two_factor?.required ? <Badge tone="warn" plain>À configurer</Badge> : <span className="muted">–</span>}</td>
                    <td className="nowrap">{fmtDate(u.last_login)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager data={data} page={q.page} onPage={(page) => setQ({ page }, false)} />
          </div>
        )}
      </section>
      {creating && <UserForm onClose={() => setCreating(false)} onSaved={(u) => { setCreating(false); toast(`Utilisateur ${u.email} créé.`); reload(); }} />}
    </>
  );
}
