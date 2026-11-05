const dtf = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const dtfs = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });
const df = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" });
const nf = new Intl.NumberFormat("fr-FR");

export const fmtDate = (v) => (v ? dtf.format(new Date(v)) : "–");
export const fmtDateSec = (v) => (v ? dtfs.format(new Date(v)) : "–");
export const fmtDay = (v) => (v ? df.format(new Date(v)) : "");
export const fmtNum = (v) => (v === null || v === undefined ? "–" : nf.format(v));
export const fmtPct = (v, d = 1) => (v === null || v === undefined ? "–" : `${(v * 100).toLocaleString("fr-FR", { maximumFractionDigits: d, minimumFractionDigits: d })} %`);
export const score100 = (s) => (s === null || s === undefined ? null : Math.round(s * 100));

export function relative(v) {
  if (!v) return "";
  const diff = (Date.now() - new Date(v).getTime()) / 1000;
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}
