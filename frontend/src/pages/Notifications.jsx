import { Check, Flag } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { Badge, Empty, ErrorBox, Loader, PageHead, Pager, Panel } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { fmtDate } from "../lib/format";
import { NOTIFICATION_KINDS } from "../lib/labels";
import { useBase } from "../lib/space";
import { useApi } from "../lib/useApi";

export function notifyCountChanged() {
  window.dispatchEvent(new Event("sa:notifications"));
}

export default function Notifications() {
  const toast = useToast();
  const base = useBase();
  const [sp, setSp] = useSearchParams();
  const focus = Number(sp.get("id")) || null;
  const page = sp.get("page") || 1;
  const { data, error, loading, reload } = useApi("/notifications/", { page, page_size: 20 });

  useEffect(() => {
    if (focus) api.post(`/notifications/${focus}/read/`).then(notifyCountChanged).catch(() => {});
  }, [focus]);

  async function respond(n, response) {
    try {
      const { data: r } = await api.post(`/notifications/${n.id}/respond/`, { response });
      toast(r.detail, response === "CONTESTEE" ? "error" : "info");
      reload();
      notifyCountChanged();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  async function readAll() {
    await api.post("/notifications/read_all/");
    reload();
    notifyCountChanged();
  }

  return (
    <>
      <PageHead title="Notifications" sub="Connexions inhabituelles, changements de mot de passe et blocages de votre compte."
                actions={<button className="btn" onClick={readAll}>Tout marquer comme lu</button>} />
      <Panel flush>
        <ErrorBox error={error} onRetry={reload} />
        {!data && loading ? <Loader /> : !data?.results.length ? <Empty title="Aucune notification." /> : (
          <>
            {data.results.map((n) => (
              <div key={n.id} className={`notif${n.read_at ? "" : " unread"}${n.id === focus ? " focus" : ""}`}>
                <span className="dot" aria-hidden="true" />
                <div>
                  <h3>{n.title}</h3>
                  <p>{n.message}</p>
                  <div className="row small muted" style={{ marginTop: 6 }}>
                    <span>{fmtDate(n.created_at)}</span>
                    <Badge plain>{NOTIFICATION_KINDS[n.kind]}</Badge>
                    {n.event && <Link to={`${base}/connexions/${n.event}`}>Voir la connexion</Link>}
                  </div>
                </div>
                <div className="row" style={{ alignItems: "flex-start" }}>
                  {n.needs_response && !n.response && (
                    <>
                      <button className="btn sm" onClick={() => respond(n, "CONFIRMEE")}><Check size={14} /> C'était moi</button>
                      <button className="btn sm danger" onClick={() => respond(n, "CONTESTEE")}><Flag size={14} /> Ce n'était pas moi</button>
                    </>
                  )}
                  {n.response && <Badge tone={n.response === "CONTESTEE" ? "danger" : "ok"} plain>{n.response_label}</Badge>}
                </div>
              </div>
            ))}
            <Pager data={data} page={page} pageSize={20} onPage={(p) => setSp({ page: p })} />
          </>
        )}
      </Panel>
    </>
  );
}
