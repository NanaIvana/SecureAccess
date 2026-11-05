import { ShieldAlert } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import EventTable from "../components/EventTable";
import { ErrorBox, Loader, PageHead, Pager, Panel } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { fmtNum } from "../lib/format";
import { useBase } from "../lib/space";
import { useApi } from "../lib/useApi";

export default function MyEvents() {
  const base = useBase();
  const { user, lastRisk, setLastRisk } = useAuth();
  const [sp, setSp] = useSearchParams();
  const page = sp.get("page") || 1;
  const { data, loading, error, reload } = useApi("/events/", { page, page_size: 25, user: user.id });
  const risky = useApi("/events/", { user: user.id, level: "CRITIQUE", page_size: 1 });
  const pending = useApi("/notifications/unread/");

  return (
    <>
      <PageHead title="Mes connexions"
                sub="L'historique des connexions à votre compte. Si vous ne reconnaissez pas une connexion, ouvrez-la et signalez-la." />
      {lastRisk && lastRisk.level !== "NORMAL" && (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          <ShieldAlert size={18} />
          <div style={{ flex: 1 }}>
            <strong>Votre connexion actuelle a été jugée {lastRisk.level === "SUSPECT" ? "suspecte" : "à risque élevé"}.</strong>
            <div className="small">{lastRisk.reasons.join(". ")}. Si c'est bien vous, rien à faire : l'équipe de sécurité vérifiera.</div>
          </div>
          <button className="btn sm" onClick={() => setLastRisk(null)}>J'ai compris</button>
        </div>
      )}
      {pending.data?.pending > 0 && (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          <ShieldAlert size={18} />
          <span style={{ flex: 1 }}>{pending.data.pending} connexion(s) ou action(s) inhabituelle(s) attendent votre confirmation.</span>
          <Link className="btn sm" to={`${base}/notifications`}>Répondre</Link>
        </div>
      )}
      {risky.data?.count > 0 && (
        <div className="notice danger" style={{ marginBottom: 16 }}>
          <ShieldAlert size={18} />
          <span>{fmtNum(risky.data.count)} connexion(s) critique(s) sur votre compte. Vérifiez-les et changez votre mot de passe si besoin.</span>
        </div>
      )}
      <Panel flush>
        <ErrorBox error={error} onRetry={reload} />
        {!data && loading ? <Loader /> : <EventTable events={data?.results} showUser={false} showRules={false} emptyText="Aucune connexion enregistrée." />}
        <Pager data={data} page={page} pageSize={25} onPage={(p) => setSp({ page: p })} />
      </Panel>
    </>
  );
}
