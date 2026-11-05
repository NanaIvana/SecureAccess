import { Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { errorMessage } from "../api/client";
import { ErrorBox, Field } from "../components/ui";
import { AuthShell } from "./Login";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/auth/password-reset/", { email });
      setDone(data.detail);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <form onSubmit={submit}>
        <div>
          <h2>Mot de passe oublié</h2>
          <p className="muted" style={{ marginTop: 6 }}>Nous vous envoyons un lien pour choisir un nouveau mot de passe.</p>
        </div>
        {done ? <div className="notice ok">{done}</div> : (
          <>
            <ErrorBox error={error} />
            <Field label="Adresse e-mail">
              <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <button className="btn primary" disabled={busy}>{busy && <Loader2 size={16} className="spin" />} Envoyer le lien</button>
          </>
        )}
        <Link to="/connexion" className="small">Revenir à la connexion</Link>
      </form>
    </AuthShell>
  );
}

export function ResetPassword() {
  const [sp] = useSearchParams();
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (pwd !== confirm) { setError("Les deux mots de passe ne sont pas identiques."); return; }
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/auth/password-reset/confirm/", { uid: sp.get("uid"), token: sp.get("token"), new_password: pwd });
      setDone(data.detail);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <form onSubmit={submit}>
        <h2>Nouveau mot de passe</h2>
        {done ? <><div className="notice ok">{done}</div><Link to="/connexion" className="btn primary">Se connecter</Link></> : (
          <>
            <ErrorBox error={error} />
            <Field label="Nouveau mot de passe" hint="8 caractères minimum, pas uniquement des chiffres.">
              <input className="input" type="password" autoComplete="new-password" required value={pwd} onChange={(e) => setPwd(e.target.value)} />
            </Field>
            <Field label="Confirmer le mot de passe">
              <input className="input" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </Field>
            <button className="btn primary" disabled={busy}>{busy && <Loader2 size={16} className="spin" />} Enregistrer le mot de passe</button>
          </>
        )}
      </form>
    </AuthShell>
  );
}
