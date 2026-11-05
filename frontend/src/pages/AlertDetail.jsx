import { ChevronLeft, Lock } from "lucide-react";
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

  const back = <Link className="back" to="/console/alertes"><ChevronLeft size={15} /> Alertes</Link>;
  if (error) return <>{back}<ErrorBox error={error} onRetry={reload} /></>;
  if (!a) return <Loader />;

  async function update(status) {
    setBusy(true);
    try {
      const { data } = await api.patch(`/alerts/${id}/`, { status, comment });
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
      const { data } = await api.post(`/alerts/${id}/block_user/`, { minutes });
      setData(data);
      setBlocking(false);
      toast(`Compte ${a.user.email} bloqué.`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
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
                <button className="btn danger" onClick={() => setBlocking(true)}><Lock size={15} /> Bloquer le compte</button>
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
