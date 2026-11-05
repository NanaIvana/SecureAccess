import { Loader2, Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { Empty, ErrorBox, Field, LevelBadge, PageHead, Panel, RiskMeter } from "../components/ui";
import { fmtDateSec } from "../lib/format";
import { useApi } from "../lib/useApi";
import { EvaluationPanel } from "./EventDetail";

const PLACES = [
  ["Cameroun", "Yaoundé", 3.848, 11.502], ["Cameroun", "Douala", 4.051, 9.768], ["Cameroun", "Garoua", 9.301, 13.397],
  ["Nigeria", "Lagos", 6.524, 3.379], ["France", "Paris", 48.857, 2.352], ["États-Unis", "New York", 40.713, -74.006],
  ["Russie", "Moscou", 55.756, 37.617], ["Chine", "Pékin", 39.904, 116.407], ["Inde", "Mumbai", 19.076, 72.878],
  ["Brésil", "São Paulo", -23.55, -46.633], ["Roumanie", "Bucarest", 44.43, 26.1], ["Turquie", "Istanbul", 41.008, 28.978],
];

const BASE = { use_home: false, place: "", hour: "", new_device: false, new_ip: false, failures_before: 0, success: true, previous_home_login_minutes: "", stuffing_accounts: 0, blocked_ip: false };

const SCENARIOS = [
  { key: "normal", name: "Connexion normale", desc: "Depuis le domicile, appareil connu, en journée.", p: { use_home: true, hour: 9 } },
  { key: "force_brute", name: "Force brute", desc: "12 échecs en moins d'une minute depuis Moscou, puis succès.", p: { place: "Moscou", hour: 3, new_device: true, new_ip: true, failures_before: 12 } },
  { key: "stuffing", name: "Attaque en masse", desc: "Une IP de Lagos teste 22 autres comptes en quelques minutes, puis celui-ci.", p: { place: "Lagos", new_device: true, new_ip: true, stuffing_accounts: 22, failures_before: 1, success: false } },
  { key: "voyage", name: "Voyage impossible", desc: "Connexion au domicile, puis à Paris 60 minutes plus tard.", p: { place: "Paris", new_device: true, new_ip: true, previous_home_login_minutes: 60 } },
  { key: "heure", name: "Heure inhabituelle", desc: "Depuis le domicile et l'appareil habituel, à 3 h du matin.", p: { use_home: true, hour: 3 } },
  { key: "appareil", name: "Nouvel appareil à l'étranger", desc: "Nouvel appareil, nouvelle IP, depuis Mumbai, en journée.", p: { place: "Mumbai", hour: 10, new_device: true, new_ip: true } },
  { key: "bloquee", name: "IP à mauvaise réputation", desc: "Connexion depuis une IP de la liste de blocage (ajoutez-en une avant).", p: { use_home: true, hour: 10, blocked_ip: true } },
];

export default function Simulator() {
  const [search, setSearch] = useState("");
  const users = useApi("/users/", { search, role: "UTILISATEUR", page_size: 20, ordering: "email" });
  const [userId, setUserId] = useState("");
  const [scenario, setScenario] = useState("force_brute");
  const [f, setF] = useState({ ...BASE, ...SCENARIOS[1].p });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const pick = (s) => { setScenario(s.key); setF({ ...BASE, ...s.p }); };
  const set = (k) => (e) => { setScenario(""); setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }); };

  async function run() {
    if (!userId) { setError("Choisissez d'abord le compte à cibler."); return; }
    setBusy(true);
    setError("");
    const place = PLACES.find((p) => p[1] === f.place);
    const body = {
      user: Number(userId), use_home: f.use_home || !place,
      country: place?.[0] || "", city: place?.[1] || "", latitude: place?.[2] ?? null, longitude: place?.[3] ?? null,
      hour: f.hour === "" ? null : Number(f.hour), new_device: f.new_device, new_ip: f.new_ip,
      failures_before: Number(f.failures_before) || 0, success: f.success,
      previous_home_login_minutes: f.previous_home_login_minutes === "" ? null : Number(f.previous_home_login_minutes),
      stuffing_accounts: Number(f.stuffing_accounts) || 0, blocked_ip: f.blocked_ip,
    };
    try {
      const { data } = await api.post("/events/simulate/", body);
      setResult(data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="Simulateur d'attaques"
                sub="Crée des connexions fictives sur un compte et montre en direct le score calculé. Les connexions simulées apparaissent dans le journal avec la source « Simulateur », et l'utilisateur ciblé reçoit une notification si le niveau est suspect ou plus." />
      <div className="grid grid-2">
        <div className="stack">
          <Panel title="Compte ciblé">
            <div className="form-grid">
              <Field label="Rechercher un compte">
                <input className="input" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nom ou e-mail" />
              </Field>
              <Field label="Compte">
                <select className="input" value={userId} onChange={(e) => setUserId(e.target.value)}>
                  <option value="">Choisir…</option>
                  {(users.data?.results || []).map((u) => <option key={u.id} value={u.id}>{u.full_name} ({u.home_city || "?"})</option>)}
                </select>
              </Field>
            </div>
          </Panel>
          <Panel title="Scénario">
            <div className="scenarios">
              {SCENARIOS.map((s) => (
                <button key={s.key} type="button" className={`scenario${scenario === s.key ? " on" : ""}`} onClick={() => pick(s)} aria-pressed={scenario === s.key}>
                  <strong>{s.name}</strong><span>{s.desc}</span>
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Paramètres" sub="Modifiez librement les paramètres du scénario choisi.">
            <div className="form-grid">
              <Field label="Lieu">
                <select className="input" value={f.use_home ? "" : f.place} onChange={(e) => { setScenario(""); setF({ ...f, place: e.target.value, use_home: !e.target.value }); }}>
                  <option value="">Domicile du compte</option>
                  {PLACES.map((p) => <option key={p[1]} value={p[1]}>{p[1]}, {p[0]}</option>)}
                </select>
              </Field>
              <Field label="Heure (UTC)" hint="Vide : heure actuelle">
                <input className="input" type="number" min="0" max="23" value={f.hour} onChange={set("hour")} />
              </Field>
              <Field label="Échecs juste avant">
                <input className="input" type="number" min="0" max="60" value={f.failures_before} onChange={set("failures_before")} />
              </Field>
              <Field label="Autres comptes visés par la même IP">
                <input className="input" type="number" min="0" max="30" value={f.stuffing_accounts} onChange={set("stuffing_accounts")} />
              </Field>
              <Field label="Connexion au domicile avant (minutes)" hint="Pour simuler un voyage impossible" className="full">
                <input className="input" type="number" min="1" max="1440" value={f.previous_home_login_minutes} onChange={set("previous_home_login_minutes")} />
              </Field>
              <label className="check"><input type="checkbox" checked={f.new_device} onChange={set("new_device")} /> Nouvel appareil</label>
              <label className="check"><input type="checkbox" checked={f.new_ip} onChange={set("new_ip")} /> Nouvelle adresse IP</label>
              <label className="check"><input type="checkbox" checked={f.success} onChange={set("success")} /> Mot de passe correct</label>
              <label className="check"><input type="checkbox" checked={f.blocked_ip} onChange={set("blocked_ip")} /> IP de la liste de blocage</label>
            </div>
            <ErrorBox error={error} />
            <div className="mt">
              <button className="btn primary" disabled={busy} onClick={run}>
                {busy ? <Loader2 size={15} className="spin" /> : <Play size={15} />} Lancer la simulation
              </button>
            </div>
          </Panel>
        </div>
        <div className="stack">
          {!result ? (
            <Panel title="Résultat"><Empty title="Aucune simulation lancée.">Choisissez un compte et un scénario, puis lancez la simulation.</Empty></Panel>
          ) : (
            <>
              <EvaluationPanel evaluation={result.event.evaluation} title="Score de la dernière connexion simulée" />
              <Panel title="Connexions créées" sub={`${result.created.length} événement(s), du plus ancien au plus récent.`} flush
                     actions={<>
                       <Link className="small" to={`/console/connexions/${result.event.id}`}>Fiche de la connexion</Link>
                       {result.event.alert && <Link className="small" to={`/console/alertes/${result.event.alert.id}`}>Alerte créée</Link>}
                     </>}>
                <div className="table-wrap" style={{ maxHeight: 420 }}>
                  <table className="data">
                    <thead><tr><th>Heure</th><th>Compte</th><th>Résultat</th><th>Score</th><th>Niveau</th></tr></thead>
                    <tbody>
                      {result.created.map((e) => (
                        <tr key={e.id}>
                          <td className="nowrap">{fmtDateSec(e.timestamp)}</td>
                          <td className="small">{e.target ? <strong>{e.user}</strong> : e.user}</td>
                          <td>{e.success ? "Réussie" : "Échec"}</td>
                          <td style={{ width: 130 }}><RiskMeter score={e.score} /></td>
                          <td><LevelBadge level={e.level} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          )}
        </div>
      </div>
    </>
  );
}
