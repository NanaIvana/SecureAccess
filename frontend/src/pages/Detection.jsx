import { Loader2, Play, RefreshCw, Save, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { errorMessage } from "../api/client";
import { Badge, Empty, ErrorBox, Field, Loader, Modal, PageHead, Pager, Panel } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useColors } from "../lib/colors";
import { fmtDate, fmtNum, fmtPct } from "../lib/format";
import { ATTACKS, GROUND_TRUTH, LEVELS, LIST_KINDS, LIST_TYPES } from "../lib/labels";
import { useApi } from "../lib/useApi";

function RescoreButton({ onDone }) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      const { data } = await api.post("/detection/rescore/");
      const l = data.levels;
      toast(`${fmtNum(data.events)} connexions réévaluées : ${fmtNum(l.SUSPECT)} suspectes, ${fmtNum(l.HAUT_RISQUE)} à risque élevé, ${fmtNum(l.CRITIQUE)} critiques.`);
      setConfirm(false);
      onDone?.();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="btn" onClick={() => setConfirm(true)}><RefreshCw size={15} /> Recalculer tous les scores</button>
      {confirm && (
        <Modal title="Recalculer tous les scores" onClose={() => !busy && setConfirm(false)}
               footer={<><button className="btn" disabled={busy} onClick={() => setConfirm(false)}>Annuler</button>
                 <button className="btn primary" disabled={busy} onClick={run}>{busy && <Loader2 size={15} className="spin" />} Recalculer</button></>}>
          <p>Toutes les connexions sont réévaluées avec les règles, les listes, les paramètres et le modèle actuels. Comptez environ une minute.</p>
          <p className="mt">Les alertes déjà traitées gardent leur statut. Les alertes nouvelles qui ne sont plus justifiées disparaissent.</p>
        </Modal>
      )}
    </>
  );
}

function RulesTab() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data, setData, error, reload } = useApi("/detection/rules/");
  const [draft, setDraft] = useState({});

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loader />;

  const edit = (id, k, v) => setDraft((d) => ({ ...d, [id]: { ...d[id], [k]: v } }));
  async function save(rule) {
    const body = { ...draft[rule.id] };
    if ("points" in body) body.points = Number(body.points);
    if ("threshold" in body) body.threshold = Number(body.threshold);
    try {
      const { data: r } = await api.patch(`/detection/rules/${rule.id}/`, body);
      setData(data.map((x) => (x.id === r.id ? r : x)));
      setDraft((d) => { const n = { ...d }; delete n[rule.id]; return n; });
      toast(`Règle « ${r.name} » enregistrée. Elle s'applique aux prochaines connexions ; recalculez les scores pour l'historique.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  return (
    <Panel title="Règles expertes"
           sub="Chaque règle déclenchée ajoute ses points au score sur 100, auxquels s'ajoutent jusqu'à 40 points du modèle ML (section 16.1)."
           actions={isAdmin && <RescoreButton />} flush>
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Active</th><th>Règle</th><th style={{ width: 110 }}>Points</th><th style={{ width: 230 }}>Seuil</th>{isAdmin && <th />}</tr></thead>
          <tbody>
            {data.map((r) => {
              const d = { ...r, ...draft[r.id] };
              const dirty = Boolean(draft[r.id]);
              return (
                <tr key={r.id}>
                  <td>
                    <input type="checkbox" checked={d.is_enabled} disabled={!isAdmin} aria-label={`Activer ${r.name}`}
                           onChange={(e) => edit(r.id, "is_enabled", e.target.checked)} />
                  </td>
                  <td>
                    <strong>{r.name}</strong> {r.is_extension && <Badge plain>Extension</Badge>}
                    <div className="muted small">{r.description}</div>
                  </td>
                  <td>
                    <input className="input" type="number" min="-100" max="100" step="1" value={d.points} disabled={!isAdmin}
                           style={{ width: 80 }} aria-label="Points" onChange={(e) => edit(r.id, "points", e.target.value)} />
                  </td>
                  <td>
                    {r.threshold === null ? <span className="muted">Sans seuil</span> : (
                      <div className="row" style={{ flexWrap: "nowrap" }}>
                        <input className="input" type="number" min="0" step="1" value={d.threshold} disabled={!isAdmin}
                               style={{ width: 80 }} aria-label="Seuil" onChange={(e) => edit(r.id, "threshold", e.target.value)} />
                        <span className="small muted">{r.threshold_label}</span>
                      </div>
                    )}
                  </td>
                  {isAdmin && <td><button className="btn sm primary" disabled={!dirty} onClick={() => save(r)}><Save size={14} /> Enregistrer</button></td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function ConfigTab() {
  const { isAdmin, setThresholds } = useAuth();
  const toast = useToast();
  const { data, error, reload } = useApi("/detection/config/");
  const [f, setF] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { if (data) setF(data); }, [data]);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!f) return <Loader />;

  const NUM = ["ml_points", "suspect_threshold", "high_risk_threshold", "critical_threshold", "auto_block_minutes",
    "lockout_failures", "lockout_window_minutes", "lockout_minutes", "log_retention_days", "sensitive_offset"];
  async function save() {
    setErr("");
    try {
      const body = Object.fromEntries(Object.entries(f).filter(([k]) => k !== "updated_at")
        .map(([k, v]) => [k, NUM.includes(k) ? Number(v) : v]));
      const { data: d } = await api.put("/detection/config/", body);
      setF(d);
      setThresholds({ suspect: d.suspect_threshold, high: d.high_risk_threshold, critical: d.critical_threshold });
      toast("Paramètres enregistrés. Recalculez les scores pour les appliquer à l'historique.");
    } catch (e) {
      setErr(errorMessage(e));
    }
  }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const pct = (k) => ({ value: Math.round(Number(f[k]) * 100), onChange: (e) => setF({ ...f, [k]: Number(e.target.value) / 100 }) });
  const dis = !isAdmin;

  return (
    <div className="stack">
      <ErrorBox error={err} />
      <Panel title="Score et niveaux de risque" actions={isAdmin && <RescoreButton />}>
        <p className="muted" style={{ marginBottom: 16, maxWidth: "80ch" }}>
          Score sur 100 = points des règles déclenchées + jusqu'à {f.ml_points} points du modèle ML.
          Les seuils séparent les quatre niveaux de la section 16.2 du backlog.
        </p>
        <div className="level-scale" style={{ marginBottom: 16 }}>
          {[["NORMAL", 0, f.suspect_threshold], ["SUSPECT", f.suspect_threshold, f.high_risk_threshold],
            ["HAUT_RISQUE", f.high_risk_threshold, f.critical_threshold], ["CRITIQUE", f.critical_threshold, 1.0001]].map(([lv, a, b]) => (
            <div key={lv} className={`b-${LEVELS[lv].tone}`}>
              <strong>{LEVELS[lv].label}</strong>
              <div>{Math.round(a * 100)} à {lv === "CRITIQUE" ? 100 : Math.round(b * 100) - 1}</div>
            </div>
          ))}
        </div>
        <div className="form-grid" style={{ maxWidth: 760 }}>
          <Field label="Points maximum du modèle ML" hint="40 dans le backlog">
            <input className="input" type="number" min="0" max="100" value={f.ml_points} onChange={set("ml_points")} disabled={dis} />
          </Field>
          <Field label="Seuil « suspect »"><input className="input" type="number" min="1" max="99" {...pct("suspect_threshold")} disabled={dis} /></Field>
          <Field label="Seuil « risque élevé »"><input className="input" type="number" min="1" max="99" {...pct("high_risk_threshold")} disabled={dis} /></Field>
          <Field label="Seuil « critique »"><input className="input" type="number" min="1" max="100" {...pct("critical_threshold")} disabled={dis} /></Field>
        </div>
      </Panel>
      <Panel title="Réactions aux connexions réelles">
        <div className="stack" style={{ gap: 12, maxWidth: 760 }}>
          <label className="check"><input type="checkbox" checked={f.notify_users} onChange={set("notify_users")} disabled={dis} />
            Suspect et au-delà : prévenir l'utilisateur, qui confirme « c'était moi » ou signale « ce n'était pas moi »</label>
          <label className="check"><input type="checkbox" checked={f.step_up_high_risk} onChange={set("step_up_high_risk")} disabled={dis} />
            Risque élevé : exiger une seconde étape (code de l'application, ou code envoyé par e-mail)</label>
          <label className="check"><input type="checkbox" checked={f.refuse_critical} onChange={set("refuse_critical")} disabled={dis} />
            Critique : refuser la connexion</label>
          <div className="row">
            <label className="check"><input type="checkbox" checked={f.auto_block_critical} onChange={set("auto_block_critical")} disabled={dis} />
              Critique : bloquer aussi le compte pendant</label>
            <input className="input" type="number" min="1" style={{ width: 90 }} value={f.auto_block_minutes} onChange={set("auto_block_minutes")} disabled={dis || !f.auto_block_critical} aria-label="Minutes de blocage" />
            <span>minutes</span>
          </div>
        </div>
      </Panel>
      <Panel title="Verrouillage progressif" sub="Par couple compte + source : seule la source qui échoue est bloquée, l'utilisateur légitime peut toujours se connecter ailleurs.">
        <div className="form-grid" style={{ maxWidth: 760 }}>
          <Field label="Nombre d'échecs" hint="0 pour désactiver"><input className="input" type="number" min="0" value={f.lockout_failures} onChange={set("lockout_failures")} disabled={dis} /></Field>
          <Field label="Sur une durée de (minutes)"><input className="input" type="number" min="1" value={f.lockout_window_minutes} onChange={set("lockout_window_minutes")} disabled={dis} /></Field>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Durées successives sur 24 heures : 5 min, puis 15 min, puis 60 min. L'administrateur peut déverrouiller depuis la fiche du compte.</p>
      </Panel>
      <Panel title="Comptes sensibles" sub="Enseignants et secrétariat : accès aux notes et aux dossiers, surveillance renforcée.">
        <Field label="Abaissement des seuils (points sur 100)" hint="Par exemple 10 : un compte sensible passe « suspect » dès 20 au lieu de 30.">
          <input className="input" type="number" min="0" max="50" style={{ width: 120 }}
                 value={Math.round((f.sensitive_offset ?? 0.1) * 100)}
                 onChange={(e) => setF({ ...f, sensitive_offset: Number(e.target.value) / 100 })} disabled={dis} />
        </Field>
      </Panel>
      <Panel title="Confidentialité">
        <div className="stack" style={{ gap: 12, maxWidth: 760 }}>
          <label className="check"><input type="checkbox" checked={f.pseudonymize_for_responsable} onChange={set("pseudonymize_for_responsable")} disabled={dis} />
            Masquer l'identité des utilisateurs pour le rôle Responsable (pseudonymes)</label>
          <Field label="Conservation des connexions (jours)" hint="Appliquée par la commande purge_old_data. Le journal d'audit n'est jamais supprimé.">
            <input className="input" type="number" min="30" style={{ maxWidth: 160 }} value={f.log_retention_days} onChange={set("log_retention_days")} disabled={dis} />
          </Field>
        </div>
      </Panel>
      {isAdmin && <div><button className="btn primary" onClick={save}><Save size={15} /> Enregistrer les paramètres</button></div>}
      <p className="muted small">Dernière modification : {fmtDate(f.updated_at)}</p>
    </div>
  );
}

function ListsTab() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [type, setType] = useState("BLOCAGE");
  const [page, setPage] = useState(1);
  const { data, error, reload } = useApi("/detection/lists/", { list_type: type, page });
  const [f, setF] = useState({ kind: "IP", ip: "", value: "", comment: "", expires_days: "" });

  async function add(e) {
    e.preventDefault();
    try {
      await api.post("/detection/lists/", {
        list_type: type, kind: f.kind, ip: f.ip, value: f.value, comment: f.comment,
        ...(f.expires_days ? { expires_days: Number(f.expires_days) } : {}),
      });
      toast("Entrée ajoutée.");
      setF({ ...f, ip: "", value: "", comment: "" });
      reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }
  async function remove(entry) {
    try {
      await api.delete(`/detection/lists/${entry.id}/`);
      toast("Entrée retirée.");
      reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  return (
    <div className="stack">
      <div className="tabs" style={{ marginBottom: 0 }} role="tablist">
        {Object.entries(LIST_TYPES).map(([k, v]) => (
          <button key={k} className={type === k ? "on" : ""} onClick={() => { setType(k); setPage(1); }}>Liste de {v.toLowerCase()}</button>
        ))}
      </div>
      <p className="muted" style={{ maxWidth: "85ch" }}>
        {type === "BLOCAGE"
          ? "Une connexion depuis une source bloquée est refusée. Dans l'historique, elle déclenche la règle « IP à mauvaise réputation »."
          : "Une source de confiance (IP du bureau, pays de mission, appareil connu) diminue le score et neutralise les règles « nouveau pays », « nouvel appareil » ou « attaque en masse » qui la concernent."}
        {" "}Les appareils s'ajoutent depuis la fiche d'une connexion.
      </p>
      {isAdmin && (
        <Panel title="Ajouter une entrée">
          <form onSubmit={add} className="row" style={{ alignItems: "flex-end" }}>
            <Field label="Type">
              <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
                <option value="IP">Adresse IP</option><option value="PAYS">Pays</option>
              </select>
            </Field>
            {f.kind === "IP"
              ? <Field label="Adresse IP" hint="Pseudonymisée avant stockage"><input className="input" required value={f.ip} onChange={(e) => setF({ ...f, ip: e.target.value })} placeholder="41.202.10.15" /></Field>
              : <Field label="Pays"><input className="input" required value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} placeholder="Nigeria" /></Field>}
            <Field label="Durée (jours)" hint="Vide : sans limite"><input className="input" type="number" min="1" style={{ width: 120 }} value={f.expires_days} onChange={(e) => setF({ ...f, expires_days: e.target.value })} /></Field>
            <Field label="Commentaire" className="grow"><input className="input" value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} /></Field>
            <button className="btn primary">Ajouter</button>
          </form>
        </Panel>
      )}
      <Panel flush>
        <ErrorBox error={error} onRetry={reload} />
        {!data ? <Loader /> : !data.results.length ? <Empty title="Cette liste est vide." /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Type</th><th>Élément</th><th>Commentaire</th><th>Expire le</th><th>Ajouté par</th><th>Le</th>{isAdmin && <th />}</tr></thead>
              <tbody>
                {data.results.map((x) => (
                  <tr key={x.id}>
                    <td>{LIST_KINDS[x.kind]}</td>
                    <td><strong>{x.label}</strong>{x.kind === "IP" && <div className="code muted small">{x.value.slice(0, 16)}…</div>}</td>
                    <td className="small">{x.comment || "–"}</td>
                    <td>{x.expires_at ? (x.is_expired ? <Badge plain>Expirée</Badge> : fmtDate(x.expires_at)) : "Jamais"}</td>
                    <td className="small">{x.created_by_email}</td>
                    <td className="nowrap">{fmtDate(x.created_at)}</td>
                    {isAdmin && <td><button className="btn ghost sm" onClick={() => remove(x)} aria-label="Retirer"><Trash2 size={14} /></button></td>}
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager data={data} page={page} onPage={setPage} />
          </div>
        )}
      </Panel>
    </div>
  );
}

function Metric({ label, value }) {
  return <div className="kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{value}</div></div>;
}

const METRIC_ROWS = [
  ["recall", "Rappel (attaques détectées)", false],
  ["precision", "Précision", false],
  ["f1", "F1-score", false],
  ["fpr", "Taux de faux positifs", true],
  ["roc_auc", "AUC-ROC", false],
  ["pr_auc", "AUC-PR", false],
  ["accuracy", "Exactitude", false],
];

function fmtMetric(k, v) {
  if (v === null || v === undefined) return "–";
  return k.includes("auc") ? v.toFixed(3).replace(".", ",") : fmtPct(v);
}

function MethodsTable({ methods, targets }) {
  if (!methods) return <p className="muted">Ce modèle a été entraîné avant l'ajout de la comparaison : entraînez une nouvelle version.</p>;
  const order = ["naive", "baseline", "ml", "final"];
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr><th>Métrique</th>{order.map((k) => <th key={k} className="num">{methods[k].label}</th>)}<th className="num">Cible (section 18)</th></tr>
        </thead>
        <tbody>
          {METRIC_ROWS.map(([k, label, lower]) => (
            <tr key={k}>
              <td>{label}</td>
              {order.map((m) => {
                const v = methods[m][k];
                const t = targets?.[k];
                const ok = t === undefined || v == null ? null : lower ? v <= t : v >= t;
                return <td key={m} className={`num${m === "final" && ok !== null ? (ok ? " target-ok" : " target-ko") : ""}`}>{fmtMetric(k, v)}</td>;
              })}
              <td className="num muted">{targets?.[k] !== undefined ? `${k === "fpr" ? "≤" : "≥"} ${fmtMetric(k, targets[k])}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelTab() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const c = useColors();
  const { data, error, reload } = useApi("/detection/models/");
  const features = useApi("/detection/features/");
  const [selectedId, setSelectedId] = useState(null);
  const [training, setTraining] = useState(false);
  const [importing, setImporting] = useState(false);
  const [params, setParams] = useState({ n_estimators: 150, max_depth: 12, activate: true });
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loader />;

  const active = data.find((m) => m.is_active);
  const model = data.find((m) => m.id === selectedId) || active || data[0];
  const labels = Object.fromEntries((features.data || []).map((f) => [f.name, f.label]));

  async function train() {
    setBusy(true);
    try {
      const { data: r } = await api.post("/detection/models/train/", { ...params, rescore: true });
      toast(params.activate ? `Modèle ${r.model.version} entraîné et activé. Scores recalculés.`
        : `Modèle ${r.model.version} entraîné. Comparez-le avec le modèle actif avant de l'activer.`);
      setTraining(false);
      setSelectedId(r.model.id);
      reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }
  async function activate(m) {
    try {
      await api.post(`/detection/models/${m.id}/activate/`);
      toast(`Modèle ${m.version} activé. Recalculez les scores pour l'appliquer à l'historique.`);
      reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  const actions = isAdmin && (
    <>
      <button className="btn" onClick={() => setImporting(true)}><Upload size={15} /> Importer des données</button>
      <button className="btn primary" onClick={() => setTraining(true)}><Play size={15} /> Entraîner un modèle</button>
    </>
  );

  const modals = (
    <>
      {training && <TrainModal {...{ params, setParams, busy, train, onClose: () => setTraining(false) }} />}
      {importing && <ImportModal onClose={() => setImporting(false)} onDone={() => { setImporting(false); setTraining(true); setParams({ ...params, activate: false }); }} />}
    </>
  );

  if (!model) {
    return (
      <Panel title="Modèle de Machine Learning" actions={actions}>
        <p className="muted">Aucun modèle entraîné. Le score repose uniquement sur les règles.</p>
        {modals}
      </Panel>
    );
  }

  const m = model.metrics;
  const imp = Object.entries(m.feature_importances || {}).map(([k, v]) => ({ name: labels[k] || k, value: v }))
    .sort((a, b) => b.value - a.value);
  const lc = m.final?.level_confusion;
  const compare = active && model.id !== active.id && model.metrics.methods && active.metrics.methods;

  return (
    <div className="stack">
      <Panel title={`Modèle ${model.version}`}
             sub={`${model.algorithm}, entraîné le ${fmtDate(model.trained_at)}. ${m.split || ""} : ${fmtNum(m.n_train)} pour l'apprentissage, ${fmtNum(m.n_test)} pour le test.`}
             actions={<>{model.is_active ? <Badge tone="ok">Actif</Badge> : isAdmin && <button className="btn" onClick={() => activate(model)}>Activer ce modèle</button>}{actions}</>}>
        <h3 style={{ marginBottom: 8 }}>Score hybride utilisé en production</h3>
        <div className="kpis">
          <Metric label="Rappel" value={fmtPct(m.final.recall)} />
          <Metric label="Précision" value={fmtPct(m.final.precision)} />
          <Metric label="F1" value={fmtPct(m.final.f1)} />
          <Metric label="Faux positifs" value={fmtPct(m.final.fpr)} />
          <Metric label="AUC-PR" value={m.final.pr_auc == null ? "–" : m.final.pr_auc.toFixed(3).replace(".", ",")} />
        </div>
        <div className="notice info small">
          <span>
            Le jeu de données est synthétique : les scénarios d'attaque suivent des règles connues du générateur,
            ce qui explique des scores très élevés. Sur des données réelles, attendez-vous à des performances plus basses.
            En sécurité, le rappel est prioritaire (section 18).
          </span>
        </div>
      </Panel>

      <Panel title="Comparaison avec des méthodes de référence (US13)"
             sub="Même jeu de test pour toutes les méthodes. La référence naïve montre pourquoi l'exactitude est trompeuse sur des données déséquilibrées.">
        <MethodsTable methods={m.methods} targets={m.targets} />
      </Panel>

      {compare && (
        <Panel title={`Comparaison avec le modèle actif ${active.version} (US23)`}
               sub="Score hybride de chaque version, sur son propre jeu de test." flush>
          <table className="data">
            <thead><tr><th>Métrique</th><th className="num">{active.version} (actif)</th><th className="num">{model.version}</th><th className="num">Écart</th></tr></thead>
            <tbody>
              {METRIC_ROWS.filter(([k]) => k !== "accuracy").map(([k, label, lower]) => {
                const a = active.metrics.methods.final[k];
                const b = model.metrics.methods.final[k];
                const d = a != null && b != null ? b - a : null;
                const better = d === null || d === 0 ? null : lower ? d < 0 : d > 0;
                return (
                  <tr key={k}>
                    <td>{label}</td><td className="num">{fmtMetric(k, a)}</td><td className="num">{fmtMetric(k, b)}</td>
                    <td className={`num${better === null ? "" : better ? " target-ok" : " target-ko"}`}>{d === null ? "–" : `${d > 0 ? "+" : ""}${(d * 100).toFixed(1).replace(".", ",")} pts`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      )}

      <div className="grid grid-2">
        <Panel title="Matrice de confusion du score final" sub="Lignes : vérité terrain (3 étiquettes). Colonnes : niveau attribué (4 niveaux).">
          {lc && (
            <div className="table-wrap">
              <table className="matrix">
                <thead><tr><th />{lc.levels.map((l) => <th key={l}>{LEVELS[l]?.label || l}</th>)}</tr></thead>
                <tbody>
                  {lc.matrix.map((row, i) => (
                    <tr key={i}>
                      <th>{GROUND_TRUTH[lc.labels[i]]}</th>
                      {row.map((v, j) => <td key={j} className={(i === 0 && j === 0) || (i > 0 && j > 0) ? "diag" : ""}>{fmtNum(v)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small mt">En vert : connexions normales classées normales, attaques signalées à un niveau suspect ou plus.</p>
            </div>
          )}
        </Panel>
        <Panel title="Détection par type d'attaque" flush>
          <table className="data">
            <thead><tr><th>Scénario</th><th className="num">Connexions</th><th className="num">Signalées</th><th className="num">Taux</th></tr></thead>
            <tbody>
              {Object.entries(m.final.by_attack).sort((a, b) => b[1].total - a[1].total).map(([k, v]) => (
                <tr key={k}>
                  <td>{ATTACKS[k] || k}</td>
                  <td className="num">{fmtNum(v.total)}</td>
                  <td className="num">{fmtNum(v.detected)}</td>
                  <td className="num">{k === "aucune"
                    ? <span title="Faux positifs">{fmtPct(v.rate)}</span>
                    : <strong style={{ color: v.rate >= 0.85 ? "var(--ok)" : "var(--warn)" }}>{fmtPct(v.rate)}</strong>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small" style={{ padding: "10px 12px" }}>Pour « Aucune », le taux correspond aux faux positifs.</p>
        </Panel>
      </div>

      <Panel title="Importance des caractéristiques" sub="Contribution de chaque caractéristique aux décisions de la forêt aléatoire.">
        <ResponsiveContainer width="100%" height={Math.max(220, imp.length * 26)}>
          <BarChart data={imp} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={c.line} horizontal={false} />
            <XAxis type="number" tickFormatter={(v) => `${Math.round(v * 100)} %`} tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} />
            <YAxis type="category" dataKey="name" width={260} tick={{ fill: c.ink2, fontSize: 12.5 }} stroke={c.line} />
            <Tooltip contentStyle={{ background: c.surface, border: `1px solid ${c.line}`, color: c.ink }} formatter={(v) => [fmtPct(v), "Importance"]} />
            <Bar dataKey="value" fill={c.ink2} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Versions entraînées" sub="Cliquez sur une version pour voir ses métriques et la comparer au modèle actif." flush>
        <table className="data">
          <thead><tr><th>Version</th><th>Entraîné le</th><th className="num">Rappel</th><th className="num">Précision</th><th className="num">Faux positifs</th><th>État</th></tr></thead>
          <tbody>
            {data.map((x) => (
              <tr key={x.id} className={`click${x.id === model.id ? " sel" : ""}`} onClick={() => setSelectedId(x.id)}>
                <td>{x.version}</td>
                <td>{fmtDate(x.trained_at)}</td>
                <td className="num">{fmtPct(x.metrics.final?.recall)}</td>
                <td className="num">{fmtPct(x.metrics.final?.precision)}</td>
                <td className="num">{fmtPct(x.metrics.final?.fpr)}</td>
                <td>{x.is_active ? <Badge tone="ok">Actif</Badge> : <span className="muted">Inactif</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      {modals}
    </div>
  );
}

function TrainModal({ params, setParams, busy, train, onClose }) {
  return (
    <Modal title="Entraîner un nouveau modèle" onClose={() => !busy && onClose()}
           footer={<><button className="btn" disabled={busy} onClick={onClose}>Annuler</button>
             <button className="btn primary" disabled={busy} onClick={train}>{busy && <Loader2 size={15} className="spin" />} {busy ? "Entraînement en cours…" : "Entraîner"}</button></>}>
      <p style={{ marginBottom: 14 }}>
        Forêt aléatoire entraînée sur les connexions étiquetées. Comptez une à deux minutes.
      </p>
      <div className="form-grid">
        <Field label="Nombre d'arbres" hint="Entre 10 et 500">
          <input className="input" type="number" min="10" max="500" value={params.n_estimators}
                 onChange={(e) => setParams({ ...params, n_estimators: Number(e.target.value) })} />
        </Field>
        <Field label="Profondeur maximale" hint="Entre 2 et 40">
          <input className="input" type="number" min="2" max="40" value={params.max_depth}
                 onChange={(e) => setParams({ ...params, max_depth: Number(e.target.value) })} />
        </Field>
        <label className="check full">
          <input type="checkbox" checked={params.activate} onChange={(e) => setParams({ ...params, activate: e.target.checked })} />
          Activer immédiatement et recalculer les scores
        </label>
        {!params.activate && <p className="small muted full">Le modèle sera enregistré sans être mis en service : vous pourrez le comparer au modèle actif, puis l'activer.</p>}
      </div>
    </Modal>
  );
}

function ImportModal({ onClose, onDone }) {
  const toast = useToast();
  const info = useApi("/detection/import/");
  const file = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function send() {
    if (!file.current?.files?.[0]) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file.current.files[0]);
    try {
      const { data } = await api.post("/detection/import/", form);
      setResult(data);
      toast(`${fmtNum(data.imported)} connexions importées.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Importer un jeu de données" onClose={() => !busy && onClose()} width={640}
           footer={result
             ? <><button className="btn" onClick={onClose}>Fermer</button><button className="btn primary" onClick={onDone}>Entraîner un modèle à comparer</button></>
             : <><button className="btn" disabled={busy} onClick={onClose}>Annuler</button>
               <button className="btn primary" disabled={busy} onClick={send}>{busy && <Loader2 size={15} className="spin" />} Importer</button></>}>
      {result ? (
        <div className="stack" style={{ gap: 10 }}>
          <div className="notice ok">{fmtNum(result.imported)} connexions importées, dont {fmtNum(result.labelled)} étiquetées. {fmtNum(result.created_users)} comptes créés.</div>
          {result.error_count > 0 && <div className="notice warn small">{result.error_count} lignes rejetées. {result.errors.slice(0, 5).join(" ")}</div>}
        </div>
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          <p>Fichier CSV (séparateur virgule ou point-virgule, UTF-8). Colonnes obligatoires : <span className="code">email</span>, <span className="code">timestamp</span>.</p>
          {info.data && <p className="small muted">Colonnes reconnues : {info.data.columns.join(", ")}. Valeurs de <span className="code">label</span> : {info.data.label_values.join(", ")}.</p>}
          <input ref={file} type="file" accept=".csv,text/csv" />
        </div>
      )}
    </Modal>
  );
}

const TABS = [
  { key: "regles", label: "Règles", el: <RulesTab /> },
  { key: "score", label: "Paramètres", el: <ConfigTab /> },
  { key: "listes", label: "Listes de confiance et de blocage", el: <ListsTab /> },
  { key: "modele", label: "Modèle de Machine Learning", el: <ModelTab /> },
];

export default function Detection() {
  const [sp, setSp] = useSearchParams();
  const tab = TABS.find((t) => t.key === sp.get("tab")) || TABS[0];
  return (
    <>
      <PageHead title="Règles et modèle"
                sub="Le score de risque de chaque connexion combine des règles expertes, des listes et un modèle de Machine Learning." />
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={t.key === tab.key} className={t.key === tab.key ? "on" : ""}
                  onClick={() => setSp({ tab: t.key })}>{t.label}</button>
        ))}
      </div>
      {tab.el}
    </>
  );
}
