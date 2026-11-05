import { useEffect, useState } from "react";

const NAMES = ["ink", "ink-2", "ink-3", "line", "surface", "ok", "warn", "high", "danger", "info", "brand"];

function read() {
  const s = getComputedStyle(document.documentElement);
  return Object.fromEntries(NAMES.map((n) => [n.replace("-", ""), s.getPropertyValue(`--${n}`).trim()]));
}

/** Couleurs du thème courant pour les graphiques (Recharts n'accepte pas var()). */
export function useColors() {
  const [c, setC] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setC(read());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return c;
}
