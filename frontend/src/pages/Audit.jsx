import { Download } from "lucide-react";
import { useState } from "react";
import { download, errorMessage } from "../api/client";
import { useToast } from "../context/ToastContext";
import { useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Field, Loader, Modal, PageHead, Pager } from "../components/ui";
import { fmtDateSec } from "../lib/format";
import { AUDIT_ACTIONS } from "../lib/labels";
import { useApi, useQueryState } from "../lib/useApi";

const TONE = { ACCOUNT_LOCKED: "var(--danger)", LOGIN_REFUSED_CRITICAL: "var(--danger)", LOGIN_REFUSED_BLOCKLIST: "var(--danger)", TWO_FACTOR_FAILED: "var(--warn)", LOGIN_FAILED: "var(--warn)", LOGIN_BLOCKED: "var(--danger)", USER_BLOCKED: "var(--danger)", USER_AUTO_BLOCKED: "var(--danger)", USER_DELETED: "var(--danger)", EVENT_REPORTED: "var(--danger)" };

function summary(d) {
  const parts = [];
  if (d.new_status) parts.push(`statut : ${d.old_status ? d.old_status + " → " : ""}${d.new_status}`);
  if (d.minutes) parts.push(`${d.minutes} min`);
  if (d.risk?.level) parts.push(`risque ${d.risk.level} (${Math.round(d.risk.score * 100)})`);
  if (d.fields) parts.push(`champs : ${d.fields.join(", ")}`);
  if (d.reason) parts.push(d.reason);
  if (d.events) parts.push(`${d.events} événements`);
  if (d.f1) parts.push(`F1 ${d.f1}`);
  if (d.method) parts.push(`méthode : ${d.method}`);
  if (d.label) parts.push(d.label);
  if (d.changes) parts.push(Object.entries(d.changes).map(([k, v]) => `${k} : ${v[0]} → ${v[1]}`).join(", "));
  return parts.join(", ");
}

export default function Audit() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useQueryState(sp, setSp);
  const actions = useApi("/audit/actions/");
  const { data, loading, error, reload } = useApi("/audit/", {
    page: q.page, action: q.action, search: q.search,
    date_from: q.date_from ? `${q.date_from}T00:00:00Z` : "", date_to: q.date_to ? `${q.date_to}T23:59:59Z` : "",
  });
  const [open, setOpen] = useState(null);
  const toast = useToast();

  return (
    <>
      <PageHead title="Journal d'audit"
                sub="Qui a fait quoi et quand : connexions, traitements d'alertes et changements de comptes. Aucune entrée ne peut être modifiée ni supprimée via cette API."
                actions={<button className="btn" onClick={() => download("/audit/export/", { action: q.action, search: q.search }, "audit.csv").catch((e) => toast(errorMessage(e), "error"))}>
                  <Download size={15} /> Exporter en CSV
                </button>} />
      <section className="panel">
        <div className="filters">
          <Field label="Recherche" className="grow">
            <input key={q.search || ""} className="input" type="search" placeholder="Compte, cible…" defaultValue={q.search || ""}
                   onKeyDown={(e) => e.key === "Enter" && setQ({ search: e.currentTarget.value })}
                   onBlur={(e) => e.currentTarget.value !== (q.search || "") && setQ({ search: e.currentTarget.value })} />
          </Field>
          <Field label="Action">
            <select className="input" value={q.action || ""} onChange={(e) => setQ({ action: e.target.value })}>
              <option value="">Toutes</option>
              {(actions.data || []).map((a) => <option key={a} value={a}>{AUDIT_ACTIONS[a] || a}</option>)}
            </select>
          </Field>
          <Field label="Du"><input className="input" type="date" value={q.date_from || ""} onChange={(e) => setQ({ date_from: e.target.value })} /></Field>
          <Field label="Au"><input className="input" type="date" value={q.date_to || ""} onChange={(e) => setQ({ date_to: e.target.value })} /></Field>
        </div>
        <div style={{ padding: error ? 14 : 0 }}><ErrorBox error={error} onRetry={reload} /></div>
        {!data && loading ? <Loader /> : !data?.results.length ? <Empty title="Aucune entrée." /> : (
          <div className="table-wrap" style={{ opacity: loading ? 0.6 : 1 }}>
            <table className="data">
              <thead><tr><th>Date</th><th>Auteur</th><th>Action</th><th>Cible</th><th>Détails</th></tr></thead>
              <tbody>
                {data.results.map((l) => (
                  <tr key={l.id} className="click" onClick={() => setOpen(l)}>
                    <td className="nowrap">{fmtDateSec(l.created_at)}</td>
                    <td>{l.actor_email || (l.actor ? l.actor.email : <span className="muted">Système</span>)}</td>
                    <td style={{ color: TONE[l.action], fontWeight: 560 }}>{AUDIT_ACTIONS[l.action] || l.action}</td>
                    <td>{l.target}</td>
                    <td className="small muted">{summary(l.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager data={data} page={q.page} onPage={(page) => setQ({ page }, false)} />
          </div>
        )}
      </section>
      {open && (
        <Modal title={AUDIT_ACTIONS[open.action] || open.action} onClose={() => setOpen(null)} width={640}>
          <dl className="facts" style={{ marginBottom: 14 }}>
            <dt>Date</dt><dd>{fmtDateSec(open.created_at)}</dd>
            <dt>Auteur</dt><dd>{open.actor_email || "Système"}</dd>
            <dt>Cible</dt><dd>{open.target}</dd>
            <dt>Empreinte</dt><dd className="code">{open.entry_hash || "–"}</dd>
          </dl>
          <pre className="comment-log code">{JSON.stringify(open.details, null, 2)}</pre>
        </Modal>
      )}
    </>
  );
}
