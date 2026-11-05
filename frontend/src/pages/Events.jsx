import { Download } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { download, errorMessage } from "../api/client";
import EventTable from "../components/EventTable";
import { ErrorBox, Field, Loader, PageHead, Pager } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { useApi, useQueryState } from "../lib/useApi";
import { ATTACKS, LEVELS, RULES, SOURCES } from "../lib/labels";

export default function Events() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useQueryState(sp, setSp);
  const countries = useApi("/events/countries/");
  const params = {
    page: q.page, search: q.search, level: q.level, success: q.success, source: q.source, country: q.country,
    rule: q.rule, attack_type: q.attack_type, user: q.user, ordering: q.ordering || "-timestamp",
    date_from: q.date_from ? `${q.date_from}T00:00:00Z` : "", date_to: q.date_to ? `${q.date_to}T23:59:59Z` : "",
  };
  const { data, loading, error, reload } = useApi("/events/", params);
  const toast = useToast();
  const exportCsv = (mode) => download("/events/export/", { ...params, page: "", mode }, "connexions.csv")
    .catch((e) => toast(errorMessage(e), "error"));

  return (
    <>
      <PageHead title="Journal des connexions"
                sub="Toutes les tentatives de connexion, avec leur score de risque et les règles qui se sont déclenchées."
                actions={<>
                  <button className="btn" onClick={() => exportCsv("")}><Download size={15} /> Exporter en CSV</button>
                  <button className="btn ghost" onClick={() => exportCsv("analyse")} title="Utilisateurs pseudonymisés, pour la Data Science">
                    Export pour l'analyse
                  </button>
                </>} />
      <section className="panel">
        <div className="filters">
          <Field label="Recherche" className="grow">
            <input key={q.search || ""} className="input" type="search" placeholder="E-mail, nom, ville…" defaultValue={q.search || ""}
                   onKeyDown={(e) => e.key === "Enter" && setQ({ search: e.currentTarget.value })}
                   onBlur={(e) => e.currentTarget.value !== (q.search || "") && setQ({ search: e.currentTarget.value })} />
          </Field>
          <Field label="Niveau">
            <select className="input" value={q.level || ""} onChange={(e) => setQ({ level: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </Field>
          <Field label="Résultat">
            <select className="input" value={q.success || ""} onChange={(e) => setQ({ success: e.target.value })}>
              <option value="">Tous</option><option value="true">Réussie</option><option value="false">Échec</option>
            </select>
          </Field>
          <Field label="Règle">
            <select className="input" value={q.rule || ""} onChange={(e) => setQ({ rule: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(RULES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Pays">
            <select className="input" value={q.country || ""} onChange={(e) => setQ({ country: e.target.value })}>
              <option value="">Tous</option>
              {(countries.data || []).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Source">
            <select className="input" value={q.source || ""} onChange={(e) => setQ({ source: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Type d'attaque réel" hint="Vérité terrain du jeu de données">
            <select className="input" value={q.attack_type || ""} onChange={(e) => setQ({ attack_type: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(ATTACKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Du">
            <input className="input" type="date" value={q.date_from || ""} onChange={(e) => setQ({ date_from: e.target.value })} />
          </Field>
          <Field label="Au">
            <input className="input" type="date" value={q.date_to || ""} onChange={(e) => setQ({ date_to: e.target.value })} />
          </Field>
          <Field label="Tri">
            <select className="input" value={q.ordering || "-timestamp"} onChange={(e) => setQ({ ordering: e.target.value })}>
              <option value="-timestamp">Plus récentes</option>
              <option value="timestamp">Plus anciennes</option>
              <option value="-evaluation__score">Score décroissant</option>
            </select>
          </Field>
          {Object.keys(q).length > 0 && <button className="btn ghost" onClick={() => setSp({})}>Effacer les filtres</button>}
        </div>
        <div style={{ padding: error ? 14 : 0 }}><ErrorBox error={error} onRetry={reload} /></div>
        {!data && loading ? <Loader /> : (
          <div style={{ opacity: loading ? 0.6 : 1 }}>
            <EventTable events={data?.results} />
            <Pager data={data} page={q.page} onPage={(page) => setQ({ page }, false)} />
          </div>
        )}
      </section>
    </>
  );
}
