import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Empty, ErrorBox, Loader, PageHead, Panel, RiskMeter, SeverityBadge } from "../components/ui";
import { useColors } from "../lib/colors";
import { fmtDate, fmtDay, fmtNum, fmtPct, relative } from "../lib/format";
import { RULES } from "../lib/labels";
import { useApi } from "../lib/useApi";

const PERIODS = [7, 30, 90, 180];

function Delta({ now, before, invert }) {
  if (!before) return <span className="kpi-sub">Pas de période précédente</span>;
  const d = (now - before) / before;
  const up = d > 0;
  const cls = (up ? !invert : invert) ? "up" : "down";
  return <span className="kpi-sub"><span className={cls}>{up ? "+" : ""}{fmtPct(d, 0)}</span> par rapport à la période précédente</span>;
}

function BarList({ items, danger }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="bar-list">
      {items.map((i) => (
        <div className="bar-item" key={i.key}>
          <span>{i.label}</span><strong>{fmtNum(i.value)}</strong>
          <div className="bar"><i className={danger ? "danger" : ""} style={{ width: `${(i.value / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const { data, loading, error, reload } = useApi("/dashboard/summary/", { days });
  // Rafraîchissement automatique : une alerte critique apparaît en moins d'une minute (US14)
  useEffect(() => {
    const id = setInterval(reload, 30000);
    return () => clearInterval(id);
  }, [reload]);
  const c = useColors();
  const navigate = useNavigate();

  const head = (
    <PageHead
      title="Tableau de bord"
      sub={data ? `Du ${fmtDate(data.period.start)} au ${fmtDate(data.period.end)}, jusqu'au dernier événement enregistré.` : "Vue d'ensemble des connexions et des alertes."}
      actions={
        <>
          <div className="tabs" style={{ margin: 0, border: 0 }} role="group" aria-label="Période">
            {PERIODS.map((p) => (
              <button key={p} className={days === p ? "on" : ""} onClick={() => setDays(p)}>{p} jours</button>
            ))}
          </div>
          <button className="btn" onClick={reload} aria-label="Actualiser"><RefreshCw size={15} /></button>
        </>
      }
    />
  );

  if (error) return <>{head}<ErrorBox error={error} onRetry={reload} /></>;
  if (!data) return <>{head}<Loader /></>;

  const k = data.kpis, p = data.previous;
  const tooltipStyle = { background: c.surface, border: `1px solid ${c.line}`, borderRadius: 4, color: c.ink };

  return (
    <div style={{ opacity: loading ? 0.6 : 1 }}>
      {head}
      <div className="kpis">
        <div className="kpi">
          <div className="kpi-label">Connexions</div>
          <div className="kpi-value">{fmtNum(k.total)}</div>
          <span className="kpi-sub">dont {fmtNum(k.failures)} échecs ({fmtPct(k.total ? k.failures / k.total : 0)})</span>
        </div>
        <div className="kpi">
          <div className="kpi-label">Suspectes</div>
          <div className="kpi-value" style={{ color: "var(--warn)" }}>{fmtNum(k.suspect)}</div>
          <Delta now={k.suspect} before={p.suspect} />
        </div>
        <div className="kpi">
          <div className="kpi-label">Risque élevé</div>
          <div className="kpi-value" style={{ color: "var(--high)" }}>{fmtNum(k.high_risk)}</div>
          <Delta now={k.high_risk} before={p.high_risk} />
        </div>
        <div className="kpi">
          <div className="kpi-label">Critiques</div>
          <div className="kpi-value" style={{ color: "var(--danger)" }}>{fmtNum(k.critical)}</div>
          <Delta now={k.critical} before={p.critical} />
        </div>
        <div className={`kpi${data.alerts.open_critical ? " alarm" : ""}`}>
          <div className="kpi-label">Alertes ouvertes</div>
          <div className="kpi-value"><Link to="/console/alertes?open=true" style={{ color: "inherit" }}>{fmtNum(data.alerts.open)}</Link></div>
          <span className="kpi-sub">dont {fmtNum(data.alerts.open_critical)} critiques, {fmtNum(data.blocked_users)} comptes bloqués</span>
        </div>
      </div>

      <div className="grid grid-main">
        <div className="stack">
          <Panel title="Connexions à risque par jour" sub={`Taux de connexions à risque : ${fmtPct(k.risky_rate)} (période précédente : ${fmtPct(p.risky_rate)})`}>
            <div className="legend" style={{ marginBottom: 8 }}>
              <span><i style={{ background: c.warn }} />Suspectes</span>
              <span><i style={{ background: c.high }} />Risque élevé</span>
              <span><i style={{ background: c.danger }} />Critiques</span>
              <span><i style={{ background: c.ink3, height: 2 }} />Total des connexions (échelle de droite)</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data.timeline} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="day" tickFormatter={fmtDay} tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} minTickGap={24} />
                <YAxis yAxisId="r" tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} allowDecimals={false} />
                <YAxis yAxisId="t" orientation="right" tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={fmtDay}
                         formatter={(v, n) => [fmtNum(v), { suspect: "Suspectes", high_risk: "Risque élevé", critical: "Critiques", total: "Total" }[n] || n]} />
                <Bar yAxisId="r" dataKey="suspect" stackId="a" fill={c.warn} />
                <Bar yAxisId="r" dataKey="high_risk" stackId="a" fill={c.high} />
                <Bar yAxisId="r" dataKey="critical" stackId="a" fill={c.danger} radius={[2, 2, 0, 0]} />
                <Line yAxisId="t" dataKey="total" stroke={c.ink3} dot={false} strokeWidth={1.5} />
              </ComposedChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Répartition horaire" sub="Heure UTC de la tentative. Les attaques se concentrent la nuit.">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.hours} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="hour" tickFormatter={(h) => `${h}h`} tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} />
                <YAxis tick={{ fill: c.ink3, fontSize: 12 }} stroke={c.line} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(h) => `${h} h – ${h + 1} h`}
                         formatter={(v, n) => [fmtNum(v), n === "risky" ? "À risque" : "Toutes"]} />
                <Bar dataKey="total" fill={c.line} />
                <Bar dataKey="risky" fill={c.danger} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <div className="grid grid-2">
            <Panel title="Règles déclenchées" sub="Sur les connexions suspectes et à haut risque">
              {data.rules.length
                ? <BarList items={data.rules.map((r) => ({ key: r.code, label: RULES[r.code] || r.code, value: r.count }))} />
                : <Empty title="Aucune règle déclenchée." />}
            </Panel>
            <Panel title="Pays d'origine des connexions à risque">
              {data.countries.length
                ? <BarList danger items={data.countries.map((r) => ({ key: r.country, label: r.country, value: r.n }))} />
                : <Empty title="Aucune connexion à risque." />}
            </Panel>
          </div>
        </div>

        <div className="stack">
          <Panel title="Alertes à traiter" actions={<Link to="/console/alertes?open=true" className="small">Toutes les alertes</Link>} flush>
            {data.latest_alerts.length === 0 && <Empty title="Aucune alerte ouverte.">Tout a été traité.</Empty>}
            <table className="data">
              <tbody>
                {data.latest_alerts.map((a) => (
                  <tr key={a.id} className="click" onClick={() => navigate(`/console/alertes/${a.id}`)}>
                    <td>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <SeverityBadge severity={a.severity} />
                        <span className="muted small">{relative(a.created_at)}</span>
                      </div>
                      <div style={{ fontWeight: 560, marginTop: 4 }}>{a.user}</div>
                      <div className="muted small">{[a.city, a.country].filter(Boolean).join(", ")} {a.reasons[0] ? `– ${a.reasons[0]}` : ""}</div>
                      <div style={{ marginTop: 6 }}><RiskMeter score={a.score} /></div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>

          <Panel title="Comptes les plus visés" flush>
            <table className="data">
              <thead><tr><th>Compte</th><th className="num">À risque</th><th>Score max</th></tr></thead>
              <tbody>
                {data.top_users.map((u) => (
                  <tr key={u.id} className="click" onClick={() => navigate(`/console/utilisateurs/${u.id}`)}>
                    <td><div className="cell-user"><strong>{u.full_name || u.email}</strong></div></td>
                    <td className="num">{fmtNum(u.risky)}</td>
                    <td style={{ width: 130 }}><RiskMeter score={u.max_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>

          <Panel title="Modèle de détection actif">
            {data.model ? (
              <dl className="facts">
                <dt>Version</dt><dd>{data.model.version}</dd>
                <dt>Entraîné le</dt><dd>{fmtDate(data.model.trained_at)}</dd>
                <dt>F1 (ML seul)</dt><dd>{fmtPct(data.model.f1)}</dd>
                <dt>Attaques détectées</dt><dd>{fmtPct(data.model.recall)}</dd>
                <dt>Faux positifs</dt><dd>{fmtPct(data.model.fpr)}</dd>
              </dl>
            ) : (
              <p className="muted">Aucun modèle actif : le score repose uniquement sur les règles. <Link to="/console/detection?tab=modele">Entraîner un modèle</Link></p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
