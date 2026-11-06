// « Ma sécurité » : état du compte, connexions récentes et conseils (GET /api/me/security/).
import { AlertTriangle, CheckCircle2, KeyRound, LogIn, MonitorSmartphone, ShieldAlert, XCircle, FlaskConical } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { Badge, ErrorBox, Field, Loader, Panel } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { fmtDate, relative } from "../lib/format";

const STATUS = {
  ok: { title: "Votre compte est protégé", text: "Aucune activité anormale récente.", icon: CheckCircle2, color: "c-green" },
  warn: { title: "Quelques points à vérifier", text: "Regardez les conseils ci-dessous.", icon: AlertTriangle, color: "c-amber" },
  high: { title: "Activité inhabituelle détectée", text: "Des essais de connexion suspects ont eu lieu sur votre compte.", icon: ShieldAlert, color: "c-orange" },
  danger: { title: "Action nécessaire", text: "Votre compte a fait l'objet d'un blocage de sécurité.", icon: XCircle, color: "c-red" },
};

const TONE_BADGE = { ok: "ok", warn: "warn", high: "high", danger: "danger" };

export default function EspaceHome() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [labPassword, setLabPassword] = useState("");
  const [labResult, setLabResult] = useState(null);
  const [labError, setLabError] = useState("");
  const [labBusy, setLabBusy] = useState(false);

  const runLab = async (scenario) => {
    setLabBusy(true);
    setLabError("");
    setLabResult(null);
    try {
      const { data: result } = await api.post("/lab/attacks/", { scenario, password: labPassword });
      setLabResult(result);
    } catch (e) {
      setLabError(errorMessage(e));
    } finally {
      setLabBusy(false);
      load();
    }
  };

  const load = useCallback(() => {
    setError(null);
    api.get("/me/security/").then(({ data: d }) => setData(d)).catch(setError);
  }, []);
  useEffect(load, [load]);

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!data) return <Loader />;

  const st = STATUS[data.status] || STATUS.ok;
  const Icon = st.icon;
  const tiles = [
    { label: "Connexions réussies (7 j)", value: data.stats.logins_7d, icon: LogIn, color: "c-teal" },
    { label: "Échecs (7 j)", value: data.stats.failures_7d, icon: KeyRound, color: "c-amber" },
    { label: "Connexions inhabituelles (7 j)", value: data.stats.unusual_7d, icon: ShieldAlert, color: "c-orange" },
    { label: "Appareils connus", value: data.stats.devices, icon: MonitorSmartphone, color: "c-violet" },
  ];

  return (
    <>
      <div className="hero">
        <span className={`ico ${st.color}`} style={{ width: 56, height: 56, borderRadius: 16, display: "grid", placeItems: "center" }}>
          <Icon size={28} />
        </span>
        <div>
          <h1>Bonjour {user?.full_name?.split(" ")[0] || ""}, {st.title.toLowerCase()}</h1>
          <p>{st.text} Profil : {data.profile_type_label.toLowerCase()}.</p>
        </div>
      </div>

      {import.meta.env.DEV && import.meta.env.VITE_DEMO_MODE === "true" && user?.email?.toLowerCase().endsWith(".test") && (
        <Panel title="Mode test de sécurité" sub="Les scénarios ciblent uniquement votre compte de démonstration et passent par le vrai endpoint de connexion.">
          <div className="filters">
            <Field label="Mot de passe du compte" className="grow">
              <input className="input" type="password" autoComplete="current-password" value={labPassword}
                     onChange={(e) => setLabPassword(e.target.value)} placeholder="Requis sauf pour la force brute" />
            </Field>
            <button className="btn" disabled={labBusy || !labPassword} onClick={() => runLab("normal")}><LogIn size={15} /> Connexion normale</button>
            <button className="btn" disabled={labBusy || !labPassword} onClick={() => runLab("new_device")}><MonitorSmartphone size={15} /> Nouvel appareil</button>
            <button className="btn" disabled={labBusy || !labPassword} onClick={() => runLab("compromised")}><ShieldAlert size={15} /> Compte compromis</button>
            <button className="btn danger" disabled={labBusy} onClick={() => runLab("brute_force")}><FlaskConical size={15} /> Force brute</button>
          </div>
          <p className="small muted">Le mode nécessite DEMO_MODE=True côté backend. La force brute effectue six échecs réels sur votre compte de test et peut verrouiller cette source pendant quelques minutes.</p>
          {labError && <div className="notice danger small" style={{ marginTop: 10 }}>{labError}</div>}
          {labResult && <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="data"><thead><tr><th>Essai</th><th>Décision HTTP</th><th>Niveau</th><th>Score</th><th>Motifs</th></tr></thead>
              <tbody>{labResult.attempts.map((a) => <tr key={a.attempt}><td>{a.attempt}</td><td>{a.http_status} · {a.decision}</td><td>{a.level || "—"}</td><td>{a.score == null ? "—" : Math.round(a.score * 100)}</td><td>{(a.reasons || []).join(" · ") || "—"}</td></tr>)}</tbody>
            </table>
          </div>}
        </Panel>
      )}

      <div className="tiles">
        {tiles.map((t) => (
          <div className="tile" key={t.label}>
            <span className={`ico ${t.color}`}><t.icon size={20} /></span>
            <div><strong>{t.value}</strong><span>{t.label}</span></div>
          </div>
        ))}
      </div>

      <div className="grid-2" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
        <Panel title="Conseils" sub="Ce que nous avons remarqué et ce que vous pouvez faire">
          <div className="notices">
            {data.notices.map((n) => (
              <div key={n.title} className={`notice ${n.tone}`}>
                <div>
                  <strong>{n.title}</strong>
                  <div className="small" style={{ marginTop: 2 }}>{n.text}</div>
                  {n.link && <Link className="small" to={`/espace/${n.link}`}>Y aller</Link>}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Connexions récentes" sub="Les dernières tentatives sur votre compte" flush
               actions={<Link className="btn sm" to="/espace/connexions-perso">Tout voir</Link>}>
          {data.recent_events.length === 0 ? (
            <p className="muted" style={{ padding: 18 }}>Aucune connexion enregistrée pour l'instant.</p>
          ) : (
            <ul className="sec-list">
              {data.recent_events.map((e) => (
                <li key={e.id}>
                  <span className={`dot ${e.tone}`} />
                  <div>
                    <Link to={`/espace/connexions/${e.id}`}><strong>{e.outcome}</strong></Link>
                    <div className="small muted">{e.place} · {e.device}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <Badge tone={TONE_BADGE[e.tone]}>{e.level_label}</Badge>
                    <div className="small muted" title={fmtDate(e.timestamp)}>{relative(e.timestamp)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
