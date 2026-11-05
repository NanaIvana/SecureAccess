import { Download, FileText } from "lucide-react";
import { Fragment, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { download, errorMessage } from "../api/client";
import { Empty, ErrorBox, Field, Loader, PageHead, Panel } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { useColors } from "../lib/colors";
import { fmtDate, fmtDay, fmtNum, fmtPct } from "../lib/format";
import { useApi } from "../lib/useApi";

const PRESETS = [{ days: 7, label: "7 jours" }, { days: 30, label: "30 jours" }, { days: 90, label: "Trimestre" }];

function Delta({ now, before, invert }) {
  if (!before) return <span className="muted">–</span>;
  const d = (now - before) / before;
  const bad = invert ? d < 0 : d > 0;
  return <span style={{ color: d === 0 ? "var(--ink-3)" : bad ? "var(--danger)" : "var(--ok)" }}>{d > 0 ? "+" : ""}{fmtPct(d, 0)}</span>;
}

export default function Report() {
  const toast = useToast();
  const c = useColors();
  const [period, setPeriod] = useState({ days: 30, date_from: "", date_to: "" });
  const params = period.date_from && period.date_to ? { date_from: period.date_from, date_to: period.date_to } : { days: period.days };
  const { data: r, loading, error, reload } = useApi("/reports/summary/", params);
  const [busy, setBusy] = useState("");

  async function exportAs(kind) {
    setBusy(kind);
    try {
      await download("/reports/summary/", { ...params, export: kind }, `rapport.${kind}`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHead title="Rapport de synthèse"
                sub="Le niveau de protection et les incidents d'une période, à partager avec la direction ou les auditeurs. Les utilisateurs y apparaissent sous un pseudonyme."
                actions={<>
                  <button className="btn" disabled={!!busy} onClick={() => exportAs("csv")}><Download size={15} /> CSV</button>
                  <button className="btn primary" disabled={!!busy} onClick={() => exportAs("pdf")}><FileText size={15} /> Télécharger le PDF</button>
                </>} />
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="filters" style={{ borderRadius: "var(--radius)", borderBottom: 0 }}>
          <div className="tabs" style={{ margin: 0, border: 0 }} role="group" aria-label="Période">
            {PRESETS.map((p) => (
              <button key={p.days} className={!period.date_from && period.days === p.days ? "on" : ""}
                      onClick={() => setPeriod({ days: p.days, date_from: "", date_to: "" })}>{p.label}</button>
            ))}
          </div>
          <Field label="Du"><input className="input" type="date" value={period.date_from} onChange={(e) => setPeriod({ ...period, date_from: e.target.value })} /></Field>
          <Field label="Au"><input className="input" type="date" value={period.date_to} onChange={(e) => setPeriod({ ...period, date_to: e.target.value })} /></Field>
        </div>
      </section>
      <ErrorBox error={error} onRetry={reload} />
      {!r ? <Loader /> : (
        <div className="stack" style={{ opacity: loading ? 0.6 : 1 }}>
          <p className="muted">Du {fmtDate(r.period.start)} au {fmtDate(r.period.end)} ({r.period.days} jours), comparé aux {r.period.days} jours précédents.</p>
          <div className="grid grid-main">
            <Panel title="Activité" flush>
              <table className="data">
                <thead><tr><th>Indicateur</th><th className="num">Période</th><th className="num">Précédente</th><th className="num">Évolution</th></tr></thead>
                <tbody>
                  {Object.entries(r.kpi_labels).map(([k, label]) => (
                    <tr key={k}>
                      <td>{label}</td>
                      <td className="num"><strong>{fmtNum(r.kpis[k])}</strong></td>
                      <td className="num muted">{fmtNum(r.previous[k])}</td>
                      <td className="num"><Delta now={r.kpis[k]} before={r.previous[k]} invert={["total", "successes", "users"].includes(k)} /></td>
                    </tr>
                  ))}
                  <tr><td>Part des connexions à risque</td><td className="num"><strong>{fmtPct(r.kpis.risky_rate)}</strong></td><td className="num muted">{fmtPct(r.previous.risky_rate)}</td><td /></tr>
                </tbody>
              </table>
            </Panel>
            <Panel title="Traitement des alertes">
              <dl className="facts">
                <dt>Alertes de la période</dt><dd>{fmtNum(r.alerts.total)}</dd>
                <dt>Clôturées</dt><dd>{fmtNum(r.alerts.handled)} {r.alerts.handled_rate != null && `(${fmtPct(r.alerts.handled_rate, 0)})`}</dd>
                <dt>Délai médian</dt><dd>{r.alerts.median_handling_hours != null ? `${fmtNum(r.alerts.median_handling_hours)} h` : "–"}</dd>
                <dt>Comptes bloqués</dt><dd>{fmtNum(r.blocked_users)}</dd>
              </dl>
              <h3 className="mt" style={{ marginBottom: 6 }}>Par gravité</h3>
              <dl className="facts">{Object.entries(r.alerts.by_severity).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{fmtNum(v)}</dd></Fragment>)}</dl>
              <h3 className="mt" style={{ marginBottom: 6 }}>Par statut</h3>
              <dl className="facts">{Object.entries(r.alerts.by_status).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{fmtNum(v)}</dd></Fragment>)}</dl>
            </Panel>
          </div>
          <Panel title="Connexions à risque par jour">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={r.timeline} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="day" tickFormatter={fmtDay} tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} minTickGap={24} />
                <YAxis tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} allowDecimals={false} />
                <Tooltip contentStyle={{ background: c.surface, border: `1px solid ${c.line}`, color: c.ink }} labelFormatter={fmtDay}
                         formatter={(v, n) => [fmtNum(v), n === "suspect" ? "Suspectes" : "Risque élevé et critiques"]} />
                <Bar dataKey="suspect" stackId="a" fill={c.warn} />
                <Bar dataKey="high" stackId="a" fill={c.danger} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Principaux incidents" sub="Alertes de gravité haute ou critique les plus élevées de la période." flush>
            {!r.incidents.length ? <Empty title="Aucun incident sur la période." /> : (
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Date</th><th>Utilisateur</th><th>Lieu</th><th className="num">Score</th><th>Motifs principaux</th><th>Statut</th></tr></thead>
                  <tbody>
                    {r.incidents.map((i) => (
                      <tr key={i.id}>
                        <td className="nowrap">{fmtDate(i.date)}</td><td>{i.user}</td><td>{i.place}</td>
                        <td className="num"><strong>{i.score}</strong></td>
                        <td className="small">{i.reasons.join(" ; ")}</td><td>{i.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <div className="grid grid-2">
            <Panel title="Règles déclenchées" flush>
              <table className="data"><tbody>{r.rules.map((x) => <tr key={x.code}><td>{x.name}</td><td className="num">{fmtNum(x.count)}</td></tr>)}</tbody></table>
            </Panel>
            <Panel title="Pays d'origine des connexions à risque" flush>
              <table className="data"><tbody>{r.countries.map((x) => <tr key={x.country}><td>{x.country}</td><td className="num">{fmtNum(x.n)}</td></tr>)}</tbody></table>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
