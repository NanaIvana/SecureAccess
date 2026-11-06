import { AlertTriangle, Check, ChevronLeft, Flag, ListPlus } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { Outcome } from "../components/EventTable";
import { Badge, ErrorBox, Field, LevelBadge, Loader, Modal, PageHead, Panel, RiskMeter, RuleTags, StatusBadge } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDateSec, fmtNum, score100 } from "../lib/format";
import { ATTACKS, GROUND_TRUTH, LIST_KINDS, LIST_TYPES, SOURCES, WORK_PROFILES } from "../lib/labels";
import { useApi } from "../lib/useApi";

const EventMap = lazy(() => import("../components/EventMap"));

function featureValue(f) {
  if (["success", "is_weekend", "hour_unusual", "new_device", "new_ip", "foreign", "new_country"].includes(f.name)) {
    return f.value ? <strong>Oui</strong> : <span className="muted">Non</span>;
  }
  if (f.name === "hour_freq") return `${Math.round(f.value * 100)} %`;
  if (f.name === "hour") return `${f.value} h UTC`;
  return fmtNum(f.value);
}

export function ReasonsList({ reasons }) {
  if (!reasons?.length) return <p className="muted">Aucun signal anormal relevé.</p>;
  return (
    <ul className="reasons">
      {reasons.map((r, i) => <li key={i}><AlertTriangle size={15} /> <span>{r}</span></li>)}
    </ul>
  );
}

export function EvaluationPanel({ evaluation, title = "Évaluation du risque" }) {
  if (!evaluation) return <Panel title={title}><p className="muted">Cette connexion n'a pas encore été évaluée.</p></Panel>;
  return (
    <Panel title={title} actions={<LevelBadge level={evaluation.level} />}>
      <RiskMeter score={evaluation.score} big />
      <div className="grid grid-2 mt">
        <dl className="facts">
          <dt>Score du modèle ML</dt><dd>{evaluation.ml_score == null ? "Pas de modèle actif" : `${score100(evaluation.ml_score)}/100`}</dd>
          <dt>Score des règles</dt><dd>{score100(evaluation.rules_score)}/100</dd>
          <dt>Version du modèle</dt><dd>{evaluation.model_version || "–"}</dd>
          <dt>Calculé le</dt><dd>{fmtDateSec(evaluation.computed_at)}</dd>
        </dl>
        <div>
          <h3 style={{ marginBottom: 8 }}>Pourquoi ce score</h3>
          <ReasonsList reasons={evaluation.reasons} />
        </div>
      </div>
      {evaluation.triggered_rules?.length > 0 && (
        <div className="mt"><span className="muted small">Règles déclenchées : </span><RuleTags rules={evaluation.triggered_rules} max={10} /></div>
      )}
    </Panel>
  );
}

export default function EventDetail() {
  const { id } = useParams();
  const { user, isSupervisor, isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { data: e, error, loading, reload } = useApi(`/events/${id}/`);
  const [reporting, setReporting] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [listing, setListing] = useState(false);
  const [entry, setEntry] = useState({ list_type: "BLOCAGE", kind: "IP", comment: "", expires_days: "" });

  const back = (
    <button className="back btn ghost sm" onClick={() => navigate(-1)}><ChevronLeft size={15} /> Retour</button>
  );
  if (error) return <>{back}<ErrorBox error={error} onRetry={reload} /></>;
  if (!e || loading) return <Loader />;

  const isOwner = e.user.id === user.id;

  async function report() {
    setBusy(true);
    try {
      const { data } = await api.post(`/events/${id}/report/`, { comment });
      toast(data.detail);
      setReporting(false);
      reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmIt() {
    try {
      const { data } = await api.post(`/events/${id}/confirm/`);
      toast(data.detail);
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  async function addToList() {
    setBusy(true);
    try {
      await api.post("/detection/lists/", {
        list_type: entry.list_type, kind: entry.kind, event: e.id, comment: entry.comment,
        ...(entry.expires_days ? { expires_days: Number(entry.expires_days) } : {}),
      });
      toast(`Ajouté à la liste de ${LIST_TYPES[entry.list_type].toLowerCase()}. Il s'applique aux prochaines connexions.`);
      setListing(false);
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        back={back}
        title={`Connexion du ${fmtDateSec(e.timestamp)}`}
        sub={<>{isSupervisor ? <Link to={`/console/utilisateurs/${e.user.id}`}>{e.user.full_name || e.user.email}</Link> : "Votre compte"}{" – "}{[e.city, e.country].filter(Boolean).join(", ") || "lieu inconnu"}</>}
        actions={
          <>
            {e.alert && isSupervisor && <Link className="btn" to={`/console/alertes/${e.alert.id}`}>Voir l'alerte <StatusBadge status={e.alert.status} /></Link>}
            {isAdmin && <button className="btn" onClick={() => setListing(true)}><ListPlus size={15} /> Ajouter à une liste</button>}
            {isOwner && e.level && e.level !== "NORMAL" && <button className="btn" onClick={confirmIt}><Check size={15} /> C'était moi</button>}
            {isOwner && <button className="btn danger" onClick={() => setReporting(true)}><Flag size={15} /> Je ne reconnais pas cette connexion</button>}
          </>
        }
      />
      <div className="grid grid-main">
        <div className="stack">
          <EvaluationPanel evaluation={e.evaluation} />
          <Panel title="Lieu de la connexion" sub={e.location_source === "IP_GEOIP" ? "Localisation estimée à partir de l'adresse IP (base GeoLite2 locale)." : e.location_source === "DEMO_SIMULATED" ? "Lieu simulé pour la démonstration." : e.location_source === "PROFILE_FALLBACK" ? "IP privée/non géolocalisable : ville de référence du compte affichée." : "Aucune donnée de localisation disponible."}>
            <Suspense fallback={<Loader />}><EventMap event={e} home={e.home} /></Suspense>
          </Panel>
          {e.features && (
            <Panel title="Caractéristiques analysées" sub="Calculées à partir de l'historique du compte avant cette connexion." flush>
              <table className="data">
                <tbody>
                  {e.features.map((f) => (
                    <tr key={f.name}><td>{f.label}</td><td className="num">{featureValue(f)}</td></tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>
        <div className="stack">
          <Panel title="Détails">
            <dl className="facts">
              <dt>Résultat</dt><dd><Outcome success={e.success} reason={e.failure_reason} /></dd>
              {!e.success && <><dt>Motif</dt><dd>{e.failure_reason.replaceAll("_", " ")}</dd></>}
              <dt>Compte</dt><dd>{e.user.email}</dd>
              <dt>Source</dt><dd>{SOURCES[e.source]}</dd>
              {e.auth_method && <><dt>Méthode</dt><dd>{e.auth_method}</dd></>}
              <dt>Ville</dt><dd>{e.city || "–"}</dd>
              <dt>Pays</dt><dd>{e.country || "–"}</dd>
              <dt>IP (pseudonymisée)</dt><dd className="code">{e.ip_hash}</dd>
              {e.home?.work_profile && <><dt>Profil horaire</dt><dd>{WORK_PROFILES[e.home.work_profile]}</dd></>}
            </dl>
          </Panel>
          <Panel title="Appareil">
            {e.device ? (
              <dl className="facts">
                <dt>Type</dt><dd>{e.device.device_type || "–"}</dd>
                <dt>Système</dt><dd>{e.device.os || "–"}</dd>
                <dt>Navigateur</dt><dd>{e.device.browser || "–"}</dd>
                <dt>Empreinte</dt><dd className="code">{e.device.fingerprint.slice(0, 16)}…</dd>
              </dl>
            ) : <p className="muted">Appareil inconnu.</p>}
          </Panel>
          {e.ground_truth && (
            <Panel title="Vérité terrain" sub="Étiquette du jeu de données synthétique, jamais utilisée pour calculer le score.">
              <dl className="facts">
                <dt>Étiquette</dt><dd>{GROUND_TRUTH[e.ground_truth.label] || e.ground_truth.label}</dd>
                <dt>Scénario</dt><dd>{ATTACKS[e.ground_truth.attack_type] || e.ground_truth.attack_type}</dd>
                <dt>Verdict</dt>
                <dd>
                  {(e.ground_truth.label === "normal") === (e.level === "NORMAL")
                    ? <Badge tone="ok" plain>Correctement classée</Badge>
                    : <Badge tone="danger" plain>{e.level === "NORMAL" ? "Attaque manquée" : "Faux positif"}</Badge>}
                </dd>
              </dl>
            </Panel>
          )}
        </div>
      </div>

      {listing && (
        <Modal title="Ajouter à une liste" onClose={() => setListing(false)}
               footer={<>
                 <button className="btn" onClick={() => setListing(false)}>Annuler</button>
                 <button className="btn primary" disabled={busy} onClick={addToList}>Ajouter à la liste</button>
               </>}>
          <p style={{ marginBottom: 14 }}>
            Une source de confiance diminue le score des prochaines connexions. Une source bloquée est refusée à la connexion
            et augmente le score des connexions qui l'utilisent.
          </p>
          <div className="form-grid">
            <Field label="Liste">
              <select className="input" value={entry.list_type} onChange={(ev) => setEntry({ ...entry, list_type: ev.target.value })}>
                {Object.entries(LIST_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Élément de cette connexion">
              <select className="input" value={entry.kind} onChange={(ev) => setEntry({ ...entry, kind: ev.target.value })}>
                {Object.entries(LIST_KINDS).map(([k, v]) => (
                  <option key={k} value={k} disabled={(k === "PAYS" && !e.country) || (k === "APPAREIL" && !e.device)}>
                    {v}{k === "PAYS" && e.country ? ` (${e.country})` : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Durée (jours)" hint="Vide : sans limite">
              <input className="input" type="number" min="1" value={entry.expires_days} onChange={(ev) => setEntry({ ...entry, expires_days: ev.target.value })} />
            </Field>
            <Field label="Commentaire" className="full">
              <input className="input" value={entry.comment} onChange={(ev) => setEntry({ ...entry, comment: ev.target.value })} placeholder="Motif de l'ajout" />
            </Field>
          </div>
        </Modal>
      )}

      {reporting && (
        <Modal title="Signaler cette connexion" onClose={() => setReporting(false)}
               footer={<>
                 <button className="btn" onClick={() => setReporting(false)}>Annuler</button>
                 <button className="btn danger" disabled={busy} onClick={report}>Signaler la connexion</button>
               </>}>
          <p style={{ marginBottom: 14 }}>
            L'équipe de sécurité recevra une alerte critique pour cette connexion. Pensez aussi à changer votre mot de passe.
          </p>
          <Field label="Commentaire (facultatif)">
            <textarea className="input" value={comment} onChange={(ev) => setComment(ev.target.value)}
                      placeholder="Par exemple : je n'étais pas connecté à cette heure-là." />
          </Field>
        </Modal>
      )}
    </>
  );
}
