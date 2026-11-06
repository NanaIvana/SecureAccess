import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Download } from "lucide-react";
import api, { download, errorMessage } from "../api/client";
import {
  Empty, ErrorBox, Field, Loader, PageHead, Pager, RiskMeter, RuleTags, SeverityBadge, StatusBadge, UserCell,
} from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDateSec, fmtNum } from "../lib/format";
import { RULES, SEVERITIES, STATUSES } from "../lib/labels";
import { useApi, useQueryState } from "../lib/useApi";

const TABS = [
  { key: "open", label: "À traiter", params: { open: true } },
  { key: "NOUVELLE", label: "Nouvelles", params: { status: "NOUVELLE" } },
  { key: "EN_COURS", label: "En cours", params: { status: "EN_COURS" } },
  { key: "TRAITEE", label: "Traitées", params: { status: "TRAITEE" } },
  { key: "FAUSSE_ALERTE", label: "Fausses alertes", params: { status: "FAUSSE_ALERTE" } },
  { key: "all", label: "Toutes", params: {} },
];

export default function Alerts() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useQueryState(sp, setSp);
  const tabKey = q.tab || "open";
  const tab = TABS.find((t) => t.key === tabKey) || TABS[0];
  const filters = {
    severity: q.severity, rule: q.rule, search: q.search, user: q.user,
    date_from: q.date_from ? `${q.date_from}T00:00:00Z` : "", date_to: q.date_to ? `${q.date_to}T23:59:59Z` : "",
  };
  const { data, loading, error, reload } = useApi("/alerts/", {
    ...tab.params, ...filters, page: q.page, ordering: q.ordering || "-created_at",
  });
  // Les compteurs de tous les onglets sont calculés sur les mêmes filtres, jamais sur l'onglet actif.
  const counts = useApi("/alerts/counts/", filters);
  useEffect(() => {
    const id = setInterval(counts.reload, 15000);
    return () => clearInterval(id);
  }, [counts.reload]);
  const [selected, setSelected] = useState([]);
  const [bulkStatus, setBulkStatus] = useState("TRAITEE");
  const [busy, setBusy] = useState(false);

  const c = counts.data?.by_status || {};
  const tabCount = (t) => t.key === "open" ? (Number(c.NOUVELLE) || 0) + (Number(c.EN_COURS) || 0)
    : t.key === "all" ? Object.values(c).reduce((a, b) => a + Number(b || 0), 0) : Number(c[t.key]) || 0;

  const rows = data?.results || [];
  const allChecked = rows.length > 0 && rows.every((r) => selected.includes(r.id));
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function applyBulk() {
    setBusy(true);
    try {
      const { data: r } = await api.post("/alerts/bulk/", { ids: selected, status: bulkStatus });
      toast(`${r.updated} alertes passées en « ${STATUSES[bulkStatus].label} ».`);
      setSelected([]);
      reload(); counts.reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="Alertes"
                sub="Une alerte est créée pour chaque connexion suspecte (gravité faible), à risque élevé (haute) ou critique."
                actions={<button className="btn" onClick={() => download("/alerts/export/", { ...tab.params, ...filters, ordering: q.ordering }, "alertes.csv").catch((e) => toast(errorMessage(e), "error"))}>
                  <Download size={15} /> Exporter en CSV
                </button>} />
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={t.key === tab.key} className={t.key === tab.key ? "on" : ""}
                  onClick={() => { setSelected([]); setQ({ tab: t.key, open: "" }); }}>
            {t.label}<span className="n">{fmtNum(tabCount(t))}</span>
          </button>
        ))}
      </div>
      <section className="panel">
        <div className="filters">
          <Field label="Recherche" className="grow">
            <input key={q.search || ""} className="input" type="search" placeholder="Compte, pays, commentaire…" defaultValue={q.search || ""}
                   onKeyDown={(e) => e.key === "Enter" && setQ({ search: e.currentTarget.value })}
                   onBlur={(e) => e.currentTarget.value !== (q.search || "") && setQ({ search: e.currentTarget.value })} />
          </Field>
          <Field label="Gravité">
            <select className="input" value={q.severity || ""} onChange={(e) => setQ({ severity: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(SEVERITIES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </Field>
          <Field label="Règle">
            <select className="input" value={q.rule || ""} onChange={(e) => setQ({ rule: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(RULES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Tri">
            <select className="input" value={q.ordering || "-created_at"} onChange={(e) => setQ({ ordering: e.target.value })}>
              <option value="-created_at">Plus récentes</option>
              <option value="created_at">Plus anciennes</option>
              <option value="-severity_rank,-created_at">Gravité</option>
              <option value="-evaluation__score">Score décroissant</option>
            </select>
          </Field>
          <Field label="Du">
            <input className="input" type="date" value={q.date_from || ""} onChange={(e) => setQ({ date_from: e.target.value })} />
          </Field>
          <Field label="Au">
            <input className="input" type="date" value={q.date_to || ""} onChange={(e) => setQ({ date_to: e.target.value })} />
          </Field>
          {isAdmin && selected.length > 0 && (
            <div className="row" style={{ marginLeft: "auto" }}>
              <span className="small">{selected.length} sélectionnée(s)</span>
              <select className="input" value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)} aria-label="Nouveau statut">
                {Object.entries(STATUSES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <button className="btn primary" disabled={busy} onClick={applyBulk}>Appliquer</button>
            </div>
          )}
        </div>
        <div style={{ padding: error ? 14 : 0 }}><ErrorBox error={error} onRetry={reload} /></div>
        {!data && loading ? <Loader /> : rows.length === 0 ? <Empty title="Aucune alerte dans cette vue." /> : (
          <div className="table-wrap" style={{ opacity: loading ? 0.6 : 1 }}>
            <table className="data">
              <thead>
                <tr>
                  {isAdmin && (
                    <th style={{ width: 32 }}>
                      <input type="checkbox" aria-label="Tout sélectionner" checked={allChecked}
                             onChange={() => setSelected(allChecked ? [] : rows.map((r) => r.id))} />
                    </th>
                  )}
                  <th>Créée le</th><th>Compte</th><th>Gravité</th><th>Score</th><th>Lieu</th><th>Motifs</th><th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} className={`click${selected.includes(a.id) ? " sel" : ""}`} onClick={() => navigate(`/console/alertes/${a.id}`)}>
                    {isAdmin && (
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label={`Sélectionner l'alerte ${a.id}`} checked={selected.includes(a.id)} onChange={() => toggle(a.id)} />
                      </td>
                    )}
                    <td className="nowrap">{fmtDateSec(a.created_at)}</td>
                    <td><UserCell user={a.user} /></td>
                    <td><SeverityBadge severity={a.severity} /></td>
                    <td style={{ width: 140 }}><RiskMeter score={a.score} /></td>
                    <td>{[a.city, a.country].filter(Boolean).join(", ") || "–"}</td>
                    <td><RuleTags rules={a.triggered_rules} max={2} /></td>
                    <td><StatusBadge status={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager data={data} page={q.page} onPage={(page) => setQ({ page }, false)} />
          </div>
        )}
      </section>
    </>
  );
}
