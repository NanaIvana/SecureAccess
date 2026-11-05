import { AlertTriangle, CheckCircle2, FileText, XCircle } from "lucide-react";
import { useState } from "react";
import { download, errorMessage } from "../api/client";
import { ErrorBox, Loader, PageHead, Panel } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { fmtDate } from "../lib/format";
import { useApi } from "../lib/useApi";

const ICON = {
  active: <CheckCircle2 size={17} color="var(--ok)" aria-label="Active" />,
  partial: <AlertTriangle size={17} color="var(--warn)" aria-label="Partielle" />,
  inactive: <XCircle size={17} color="var(--danger)" aria-label="Inactive" />,
};

export default function Protection() {
  const toast = useToast();
  const { data, error, reload } = useApi("/protection/");
  const [busy, setBusy] = useState(false);

  async function pdf() {
    setBusy(true);
    try { await download("/protection/", { export: "pdf" }, "mesures-protection.pdf"); }
    catch (e) { toast(errorMessage(e), "error"); }
    finally { setBusy(false); }
  }

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loader />;
  const groups = [...new Set(data.measures.map((m) => m.group))];
  const counts = data.measures.reduce((a, m) => ({ ...a, [m.status]: (a[m.status] || 0) + 1 }), {});

  return (
    <>
      <PageHead title="Mesures de protection"
                sub="Ce que la plateforme met en œuvre pour protéger les comptes et les données, avec l'état réel de chaque mesure. Ce document peut être remis aux usagers ou aux auditeurs."
                actions={<button className="btn primary" disabled={busy} onClick={pdf}><FileText size={15} /> Télécharger le PDF</button>} />
      <p className="muted" style={{ marginBottom: 16 }}>
        {counts.active || 0} mesures actives, {counts.partial || 0} partielles, {counts.inactive || 0} inactives. État au {fmtDate(data.generated_at)}.
      </p>
      <div className="stack">
        {groups.map((g) => (
          <Panel key={g} title={g} flush>
            {data.measures.filter((m) => m.group === g).map((m) => (
              <div className="measure" key={m.name}>
                {ICON[m.status]}
                <div><strong>{m.name}</strong><p>{m.detail}</p></div>
              </div>
            ))}
          </Panel>
        ))}
      </div>
    </>
  );
}
