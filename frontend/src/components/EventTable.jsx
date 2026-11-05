import { CheckCircle2, XCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBase } from "../lib/space";
import { fmtDateSec } from "../lib/format";
import { SOURCES } from "../lib/labels";
import { Badge, Empty, LevelBadge, RiskMeter, RuleTags, UserCell } from "./ui";

export function Outcome({ success, reason }) {
  return success
    ? <span className="row" style={{ color: "var(--ok)", gap: 4 }}><CheckCircle2 size={15} /> Réussie</span>
    : <span className="row" style={{ color: "var(--danger)", gap: 4 }} title={reason}><XCircle size={15} /> Échec</span>;
}

/** Tableau des connexions, partagé entre le journal, la fiche utilisateur et « Mes connexions ». */
export default function EventTable({ events, showUser = true, showRules = true, emptyText = "Aucune connexion ne correspond aux filtres." }) {
  const navigate = useNavigate();
  const base = useBase();
  if (!events?.length) return <Empty title={emptyText} />;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Date</th>
            {showUser && <th>Compte</th>}
            <th>Lieu</th>
            <th>Appareil</th>
            <th>Résultat</th>
            <th>Score</th>
            <th>Niveau</th>
            {showRules && <th>Règles</th>}
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id} className="click" onClick={() => navigate(`${base}/connexions/${e.id}`)}>
              <td className="nowrap">
                {fmtDateSec(e.timestamp)}
                {e.source !== "DATASET" && <div><Badge tone="info" plain>{SOURCES[e.source]}</Badge></div>}
              </td>
              {showUser && <td><UserCell user={e.user} /></td>}
              <td>{[e.city, e.country].filter(Boolean).join(", ") || <span className="muted">Inconnu</span>}</td>
              <td className="small">{e.device ? `${e.device.os || ""} ${e.device.browser || ""}`.trim() || e.device.device_type : "–"}</td>
              <td><Outcome success={e.success} reason={e.failure_reason} /></td>
              <td style={{ width: 140 }}><RiskMeter score={e.score} /></td>
              <td><LevelBadge level={e.level} /></td>
              {showRules && <td><RuleTags rules={e.triggered_rules} max={2} /></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
