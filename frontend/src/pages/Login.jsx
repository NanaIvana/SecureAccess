import { ChevronLeft, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { ErrorBox, Field } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDate } from "../lib/format";
import { homeFor } from "../lib/space";

// Exemples illustratifs affichés à gauche de l'écran de connexion
const SAMPLE = [
  { t: "08:12", who: "Douala, appareil connu", lvl: "Normal 6", c: "" },
  { t: "08:14", who: "Yaoundé, appareil connu", lvl: "Normal 3", c: "" },
  { t: "03:41", who: "Moscou, 14 échecs puis succès", lvl: "Critique 97", c: "h" },
  { t: "09:02", who: "Lagos, nouvel appareil", lvl: "Risque élevé 64", c: "s" },
  { t: "02:18", who: "Garoua, horaire inhabituel", lvl: "Suspect 34", c: "s" },
];

export function AuthShell({ children }) {
  return (
    <div className="login">
      <section className="login-art">
        <div>
          <h1>Chaque connexion reçoit un score de risque.</h1>
          <p>
            SecureAccess compare chaque tentative de connexion aux habitudes du compte : appareil, lieu, horaire,
            échecs récents. Les connexions anormales deviennent des alertes à traiter.
          </p>
        </div>
        <div className="stream" aria-hidden="true">
          {SAMPLE.map((r, i) => (
            <div key={i} className={`stream-row ${r.c}`}>
              <span>{r.t}</span><span>{r.who}</span><b>{r.lvl}</b>
            </div>
          ))}
        </div>
      </section>
      <section className="login-form">{children}</section>
    </div>
  );
}

function SecondFactor({ step, onBack }) {
  const { verifySecondFactor } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tf = step.two_factor;

  async function loadSetup() {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/2fa/setup-login/", { challenge: tf.challenge });
      setSetup(data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await verifySecondFactor(tf.challenge, code);
      navigate(homeFor(data.user), { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  const titles = {
    totp: "Saisissez le code de votre application",
    email: "Saisissez le code reçu par e-mail",
    setup: "Activez la double authentification",
  };

  return (
    <form onSubmit={submit}>
      <button type="button" className="back btn ghost sm" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        <ChevronLeft size={15} /> Changer de compte
      </button>
      <div>
        <h2>{titles[tf.method]}</h2>
        <p className="muted" style={{ marginTop: 6 }}>{tf.reason}</p>
      </div>
      {tf.method === "email" && (
        <div className="notice info small">
          Un code à 6 chiffres vient d'être envoyé à {tf.email_hint}. Il est valable 5 minutes.
        </div>
      )}
      {tf.method === "setup" && !setup && (
        <>
          <p className="small">
            Installez une application d'authentification sur votre téléphone (Google Authenticator, Microsoft
            Authenticator ou FreeOTP), puis affichez le QR code à scanner.
          </p>
          <button type="button" className="btn" onClick={loadSetup} disabled={busy}>Afficher le QR code</button>
        </>
      )}
      {setup && (
        <div className="qr">
          <img src={setup.qr_svg} alt="QR code à scanner avec l'application d'authentification" />
          <div className="small">
            <p>Scannez ce QR code, puis saisissez le code à 6 chiffres affiché par l'application.</p>
            <p className="muted mt">Si vous ne pouvez pas scanner, saisissez cette clé dans l'application :</p>
            <div className="secret" style={{ marginTop: 6 }}>{setup.secret}</div>
          </div>
        </div>
      )}
      <ErrorBox error={error} />
      {(tf.method !== "setup" || setup) && (
        <>
          <Field label="Code à 6 chiffres">
            <input className="input code-input" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
                   required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoFocus />
          </Field>
          <button className="btn primary" disabled={busy || code.length !== 6}>
            {busy && <Loader2 size={16} className="spin" />} Vérifier et se connecter
          </button>
        </>
      )}
    </form>
  );
}

export default function Login() {
  const { user, login, endReason } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(null);
  const [wait, setWait] = useState(null); // { until, kind: "lock" | "rate", detail }
  const [now, setNow] = useState(Date.now());

  // Compte à rebours après un verrouillage (423) ou une limitation (429)
  useEffect(() => {
    if (!wait) return undefined;
    const id = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= wait.until) setWait(null);
    }, 1000);
    return () => clearInterval(id);
  }, [wait]);
  const left = wait ? Math.max(0, Math.ceil((wait.until - now) / 1000)) : 0;
  const mmss = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;

  if (user) return <Navigate to="/" replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await login(email, password);
      if (data.two_factor) {
        setStep(data);
        setPassword("");
        return;
      }
      if (data.risk && data.risk.level !== "NORMAL") {
        toast("Cette connexion a été jugée inhabituelle. Vous allez recevoir une notification pour la confirmer.", "error");
      }
      const home = homeFor(data.user);
      const from = location.state?.from?.pathname;
      navigate(from && from.startsWith(home) ? from : home, { replace: true });
    } catch (err) {
      const d = err.response?.data;
      const code = err.response?.status;
      if ((code === 423 || code === 429) && d?.retry_after_seconds) {
        setNow(Date.now());
        setWait({ until: Date.now() + d.retry_after_seconds * 1000, kind: code === 423 ? "lock" : "rate", detail: d.detail });
        return;
      }
      setError(d?.blocked_until ? `${d.detail} Fin du blocage : ${fmtDate(d.blocked_until)}.` : errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (step) return <AuthShell><SecondFactor step={step} onBack={() => setStep(null)} /></AuthShell>;

  return (
    <AuthShell>
      <form onSubmit={submit}>
        <div>
          <h2>Se connecter</h2>
          <p className="muted" style={{ marginTop: 6 }}>Utilisez l'adresse e-mail de votre compte.</p>
        </div>
        {endReason && <div className="notice info small">{endReason}</div>}
        <ErrorBox error={error} />
        {wait && (
          <div className={`notice ${wait.kind === "lock" ? "danger" : "warn"} small`} role="status">
            <div>
              <strong>{wait.kind === "lock" ? "Connexion verrouillée" : "Trop de requêtes"}</strong>
              <div>{wait.detail}</div>
              <div style={{ marginTop: 4 }}>Nouvel essai possible dans <span className="countdown">{mmss}</span>.</div>
            </div>
          </div>
        )}
        <Field label="Adresse e-mail">
          <input className="input" type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label="Mot de passe">
          <input className="input" type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="btn primary" disabled={busy || !!wait}>
          {busy && <Loader2 size={16} className="spin" />} Se connecter
        </button>
        <Link to="/mot-de-passe-oublie" className="small">Mot de passe oublié ?</Link>
        <p className="small muted">
          <ShieldCheck size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          Après 5 échecs en 10 minutes depuis un même appareil, la connexion est verrouillée 5 min, puis 15 min, puis 60 min.
        </p>
        {import.meta.env.DEV && (
          <div className="demo-accounts">
            Comptes de démonstration (mode développement) : <br />
            responsable@secureaccess.test, mot de passe Demo2026! <br />
            serge.tchouamo001@demo.secureaccess.test, mot de passe Demo2026! <br />
            Administrateur : le compte créé avec <span className="code">createsuperuser</span>.
          </div>
        )}
      </form>
    </AuthShell>
  );
}
