import { AlertTriangle, ChevronLeft, Globe2, Lock, Unlock } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import EventTable, { Outcome } from "../components/EventTable";
import { ErrorBox, Field, Loader, Modal, PageHead, Panel, SeverityBadge, StatusBadge } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDate, fmtDateSec } from "../lib/format";
import { STATUSES } from "../lib/labels";
import { useApi } from "../lib/useApi";
import { EvaluationPanel } from "./EventDetail";

const ACTIONS = [
  { status: "EN_COURS", label: "Prendre en charge", cls: "" },
  { status: "TRAITEE", label: "Confirmer et clôturer", cls: "ok" },
  { status: "FAUSSE_ALERTE", label: "Marquer comme fausse alerte", cls: "" },
  { status: "NOUVELLE", label: "Rouvrir", cls: "ghost" },
];

export default function AlertDetail() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data: a, setData, error, reload } = useApi(`/alerts/${id}/`);
  const userId = a?.user?.id;
  const history = useApi(userId ? "/events/" : null, { user: userId, page_size: 10 });
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [minutes, setMinutes] = useState(1440);
  const [countryBusy, setCountryBusy] = useState(false);
  const [unblockBusy, setUnblockBusy] = useState(false);

  const back = <Link className="back" to="/console/alertes"><ChevronLeft size={15} /> Alertes</Link>;
  if (error) return <>{back}<ErrorBox error={error} onRetry={reload} /></>;
  if (!a) return <Loader />;

  async function update(status) {
    setBusy(true);
    try {
      const payload = { status, ...(comment.trim() ? { comment: comment.trim() } : {}) };
      const { data } = await api.patch(`/alerts/${id}/`, payload);
      setData(data);
      setComment("");
      toast(`Alerte : ${STATUSES[status].label.toLowerCase()}.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  async function addComment() {
    await update(a.status);
  }

  async function block() {
    setBusy(true);
    try {
      await api.post(`/alerts/${id}/block-user/`, { minutes });
      setBlocking(false);
      toast(`Compte ${a.user.email} bloqué.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  async function unblockAccount() {
    setUnblockBusy(true);
    try {
      await api.post(`/users/${a.user.id}/unblock/`);
      toast(`Le compte ${a.user.email} est débloqué. Une double authentification sera demandée à sa prochaine connexion.`);
      reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setUnblockBusy(false);
    }
  }

  // Ajoute le pays observé à la liste de blocage pour les prochaines évaluations.
  // L'adresse IP brute n'est jamais disponible dans l'application : seul son hash est conservé.
  async function blockCountry() {
    if (!a.country) return;
    setCountryBusy(true);
    try {
      await api.post("/detection/lists/", {
        list_type: "BLOCAGE",
        kind: "PAYS",
        value: a.country,
        comment: `Ajout depuis l'alerte #${a.id} (${a.user.email})`,
      });
      toast(`Le pays « ${a.country} » a été ajouté à la liste de blocage.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setCountryBusy(false);
    }
  }

  return (
    <>
      <PageHead
        back={back}
        title={`Alerte n° ${a.id}`}
        sub={<>Connexion de <Link to={`/console/utilisateurs/${a.user.id}`}>{a.user.full_name || a.user.email}</Link> le {fmtDateSec(a.event_timestamp)}</>}
        actions={<><SeverityBadge severity={a.severity} /><StatusBadge status={a.status} /></>}
      />
      <div className="grid grid-main">
        <div className="stack">
          <Panel title="Pourquoi cette alerte est-elle suspecte ?">
            <div className="notice warn" style={{ marginBottom: 12 }}>
              <AlertTriangle size={17} />
              <div>
                <strong>{a.severity === "CRITIQUE" ? "Risque critique" : "Activité inhabituelle détectée"}</strong>
                <div className="small">Score de risque : {Math.round((a.score || 0) * 100)}/100. Cette évaluation est issue du moteur hybride (règles métier et modèle ML).</div>
              </div>
            </div>
            {a.reasons?.length ? (
              <ul className="reasons">{a.reasons.map((reason, index) => <li key={index}><AlertTriangle size={15} /><span>{reason}</span></li>)}</ul>
            ) : <p className="muted">Aucun motif détaillé n'a été renvoyé par le moteur pour cette alerte.</p>}
            {a.triggered_rules?.length > 0 && <div className="mt"><span className="muted small">Signaux / règles déclenchés : </span>{a.triggered_rules.join(", ")}</div>}
            <p className="small muted mt">Une alerte indique un écart au comportement observé ; elle ne prouve pas à elle seule une compromission. Vérifiez le contexte avant toute mesure irréversible.</p>
          </Panel>
          <EvaluationPanel evaluation={a.evaluation} />
          <Panel title="Dernières connexions du compte" flush
                 actions={<Link className="small" to={`/console/connexions?user=${a.user.id}`}>Tout l'historique</Link>}>
            {history.loading && !history.data ? <Loader /> : <EventTable events={history.data?.results} showUser={false} showRules={false} />}
          </Panel>
        </div>
        <div className="stack">
          {isAdmin && (
            <Panel title="Traitement">
              <div className="stack" style={{ gap: 12 }}>
                <Field label="Commentaire" hint="Ajouté à l'historique de l'alerte avec votre nom et la date.">
                  <textarea className="input" value={comment} onChange={(e) => setComment(e.target.value)}
                            placeholder="Vérification faite auprès de l'utilisateur, etc." />
                </Field>
                <div className="row">
                  {ACTIONS.filter((x) => x.status !== a.status).map((x) => (
                    <button key={x.status} className={`btn ${x.cls}`} disabled={busy} onClick={() => update(x.status)}>{x.label}</button>
                  ))}
                  {comment.trim() && <button className="btn ghost" disabled={busy} onClick={addComment}>Ajouter le commentaire</button>}
                </div>
                <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "4px 0" }} />
                <div className="row" style={{ flexWrap: "wrap" }}>
                  {a.user.is_blocked
                    ? <button className="btn primary" disabled={unblockBusy} onClick={unblockAccount}><Unlock size={15} /> {unblockBusy ? "Déblocage…" : "Débloquer le compte"}</button>
                    : <button className="btn danger" onClick={() => setBlocking(true)}><Lock size={15} /> Bloquer le compte</button>}
                  <button className="btn" disabled={!a.country || countryBusy} onClick={blockCountry}>
                    <Globe2 size={15} /> {countryBusy ? "Ajout…" : `Bloquer le pays (${a.country || "inconnu"})`}
                  </button>
                </div>
                <p className="small muted">Le blocage du compte est temporaire. Le blocage du pays s'applique aux prochaines évaluations et peut affecter d'autres comptes : utilisez-le avec discernement.</p>
              </div>
            </Panel>
          )}
          <Panel title="Suivi">
            <dl className="facts">
              <dt>Créée le</dt><dd>{fmtDateSec(a.created_at)}</dd>
              <dt>Traitée par</dt><dd>{a.handled_by ? (a.handled_by.full_name || a.handled_by.email) : "–"}</dd>
              <dt>Le</dt><dd>{fmtDate(a.handled_at)}</dd>
            </dl>
            <h3 className="mt" style={{ marginBottom: 6 }}>Historique des commentaires</h3>
            {a.comment ? <div className="comment-log">{a.comment}</div> : <p className="muted">Aucun commentaire.</p>}
          </Panel>
          <Panel title="Connexion concernée" actions={<Link className="small" to={`/console/connexions/${a.event_id}`}>Fiche complète</Link>}>
            <dl className="facts">
              <dt>Résultat</dt><dd><Outcome success={a.success} /></dd>
              <dt>Lieu</dt><dd>{[a.city, a.country].filter(Boolean).join(", ") || "–"}</dd>
              <dt>Appareil</dt><dd>{a.event?.device ? `${a.event.device.device_type} ${a.event.device.os} ${a.event.device.browser}` : "–"}</dd>
              <dt>Compte</dt><dd>{a.user.email}</dd>
            </dl>
          </Panel>
        </div>
      </div>

      {blocking && (
        <Modal title="Bloquer le compte" onClose={() => setBlocking(false)}
               footer={<><button className="btn" onClick={() => setBlocking(false)}>Annuler</button>
                 <button className="btn danger" disabled={busy} onClick={block}>Bloquer le compte</button></>}>
          <p style={{ marginBottom: 14 }}>{a.user.email} ne pourra plus se connecter pendant la durée choisie. L'action est inscrite au journal d'audit.</p>
          <Field label="Durée">
            <select className="input" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
              <option value={30}>30 minutes</option>
              <option value={240}>4 heures</option>
              <option value={1440}>24 heures</option>
              <option value={10080}>7 jours</option>
            </select>
          </Field>
        </Modal>
      )}
    </>
  );
}
