import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { fmtNum } from "../lib/format";
import { LEVELS, RULES, SEVERITIES, STATUSES } from "../lib/labels";

export function Badge({ tone = "neutral", children, plain }) {
  return <span className={`badge b-${tone}${plain ? " plain" : ""}`}>{children}</span>;
}

export function LevelBadge({ level }) {
  if (!level) return <Badge plain>Non évalué</Badge>;
  const l = LEVELS[level] || { label: level, tone: "neutral" };
  return <Badge tone={l.tone}>{l.label}</Badge>;
}

export function StatusBadge({ status }) {
  const s = STATUSES[status] || { label: status, tone: "neutral" };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function SeverityBadge({ severity }) {
  const s = SEVERITIES[severity] || { label: severity, tone: "neutral" };
  return <Badge tone={s.tone} plain>{s.label}</Badge>;
}

export function RuleTags({ rules = [], max = 3 }) {
  if (!rules?.length) return <span className="muted">–</span>;
  const shown = rules.slice(0, max);
  return (
    <span>
      {shown.map((r) => <span key={r} className="tag">{RULES[r] || r}</span>)}
      {rules.length > max && <span className="muted small">+{rules.length - max}</span>}
    </span>
  );
}

function toneColor(score, t) {
  if (score >= t.critical) return "var(--danger)";
  if (score >= t.high) return "var(--high)";
  if (score >= t.suspect) return "var(--warn)";
  return "var(--ok)";
}

/** Jauge de risque 0-100, avec les seuils « suspect » et « haut risque ». */
export function RiskMeter({ score, big = false, label }) {
  const { thresholds } = useAuth();
  if (score === null || score === undefined) return <span className="muted">–</span>;
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const [s, h, c] = [thresholds.suspect * 100, thresholds.high * 100, thresholds.critical * 100];
  const track = {
    background: `linear-gradient(90deg, var(--ok-soft) 0 ${s}%, var(--warn-soft) ${s}% ${h}%, var(--high-soft) ${h}% ${c}%, var(--danger-soft) ${c}% 100%)`,
  };
  return (
    <div>
      <div className={`meter${big ? " big" : ""}`} role="meter" aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={Math.round(pct)} aria-label={label || "Score de risque"}>
        <div className="meter-track" style={track}>
          <div className="meter-fill" style={{ width: `${pct}%`, background: toneColor(score, thresholds) }} />
          <i className="meter-tick" style={{ left: `${s}%` }} />
          <i className="meter-tick" style={{ left: `${h}%` }} />
          <i className="meter-tick" style={{ left: `${c}%` }} />
        </div>
        <span className="meter-val">{Math.round(pct)}</span>
      </div>
      {big && (
        <div className="meter-scale" style={{ marginRight: 78 }}>
          <span style={{ left: 0, transform: "none" }}>0</span>
          <span style={{ left: `${s}%` }}>suspect {Math.round(s)}</span>
          <span style={{ left: `${h}%` }}>élevé {Math.round(h)}</span>
          <span style={{ left: `${c}%` }}>critique {Math.round(c)}</span>
        </div>
      )}
    </div>
  );
}

export function Loader({ label = "Chargement…" }) {
  return <div className="loader"><Loader2 size={18} className="spin" /> {label}</div>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-box row" role="alert">
      <AlertTriangle size={16} /> <span style={{ flex: 1 }}>{error}</span>
      {onRetry && <button className="btn sm" onClick={onRetry}>Réessayer</button>}
    </div>
  );
}

export function Empty({ title, children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

export function Panel({ title, sub, actions, children, flush, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div><h2>{title}</h2>{sub && <p>{sub}</p>}</div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      <div className={`panel-body${flush ? " flush" : ""}`}>{children}</div>
    </section>
  );
}

export function Pager({ data, page, pageSize = 50, onPage }) {
  if (!data) return null;
  const p = Number(page || 1);
  const pages = Math.max(1, Math.ceil(data.count / pageSize));
  const from = data.count ? (p - 1) * pageSize + 1 : 0;
  const to = Math.min(p * pageSize, data.count);
  return (
    <div className="pager">
      <span>{fmtNum(from)}–{fmtNum(to)} sur {fmtNum(data.count)}</span>
      <div className="row">
        <button className="btn sm" disabled={!data.previous} onClick={() => onPage(p - 1)} aria-label="Page précédente">
          <ChevronLeft size={15} />
        </button>
        <span>Page {p} / {fmtNum(pages)}</span>
        <button className="btn sm" disabled={!data.next} onClick={() => onPage(p + 1)} aria-label="Page suivante">
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}

export function Modal({ title, onClose, children, footer, width }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} style={width ? { maxWidth: width } : null}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn ghost sm" onClick={onClose} aria-label="Fermer"><X size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

export function UserCell({ user }) {
  if (!user) return null;
  return (
    <div className="cell-user">
      <strong>{user.full_name || user.email}</strong>
      {user.full_name && user.full_name !== user.email && <span>{user.email}</span>}
    </div>
  );
}

export function PageHead({ title, sub, actions, back }) {
  return (
    <>
      {back}
      <div className="page-head">
        <div><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
        {actions && <div className="actions">{actions}</div>}
      </div>
    </>
  );
}
