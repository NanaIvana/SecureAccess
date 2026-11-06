import { useEffect, useState } from "react";
import api, { errorMessage } from "../api/client";
import { Badge, ErrorBox, Field, PageHead, Panel } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { fmtDate } from "../lib/format";
import { ROLES, WORK_PROFILES } from "../lib/labels";

function TwoFactorPanel() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [disabling, setDisabling] = useState(false);
  const [pwd, setPwd] = useState("");
  const [error, setError] = useState("");

  async function start() {
    setError("");
    try { const { data } = await api.post("/auth/2fa/"); setSetup(data); }
    catch (e) { setError(errorMessage(e)); }
  }
  async function confirm(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/2fa/confirm/", { code });
      setUser({ ...user, two_factor_enabled: true });
      setSetup(null); setCode("");
      toast("Double authentification activée.");
    } catch (err) { setError(errorMessage(err)); }
  }
  async function disable(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/2fa/disable/", { password: pwd, code });
      setUser({ ...user, two_factor_enabled: false });
      setDisabling(false); setPwd(""); setCode("");
      toast("Double authentification désactivée.");
    } catch (err) { setError(errorMessage(err)); }
  }

  return (
    <Panel title="Double authentification" actions={user.two_factor_enabled ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>}>
      <div className="stack" style={{ gap: 12 }}>
        <p className="muted small">
          À chaque connexion, un code à 6 chiffres affiché par une application sur votre téléphone (Google Authenticator,
          Microsoft Authenticator, FreeOTP) vous sera demandé en plus du mot de passe.
        </p>
        {user.two_factor_required && <div className="notice info small">L'administrateur impose la double authentification sur votre compte.</div>}
        <ErrorBox error={error} />
        {!user.two_factor_enabled && !setup && <div><button className="btn primary" onClick={start}>Activer la double authentification</button></div>}
        {setup && (
          <form onSubmit={confirm} className="stack" style={{ gap: 12 }}>
            <div className="qr">
              <img src={setup.qr_svg} alt="QR code à scanner" />
              <div className="small">
                <p>1. Scannez ce QR code avec l'application.</p>
                <p className="mt">2. Saisissez le code affiché pour terminer.</p>
                <p className="muted mt">Clé à saisir à la main si besoin :</p>
                <div className="secret" style={{ marginTop: 6 }}>{setup.secret}</div>
              </div>
            </div>
            <Field label="Code à 6 chiffres">
              <input className="input code-input" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </Field>
            <div className="row"><button className="btn primary" disabled={code.length !== 6}>Valider et activer</button>
              <button type="button" className="btn ghost" onClick={() => setSetup(null)}>Annuler</button></div>
          </form>
        )}
        {user.two_factor_enabled && !user.two_factor_required && !disabling && (
          <div><button className="btn" onClick={() => setDisabling(true)}>Désactiver</button></div>
        )}
        {disabling && (
          <form onSubmit={disable} className="stack" style={{ gap: 12 }}>
            <Field label="Mot de passe"><input className="input" type="password" autoComplete="current-password" value={pwd} onChange={(e) => setPwd(e.target.value)} /></Field>
            <Field label="Code actuel de l'application">
              <input className="input" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </Field>
            <div className="row"><button className="btn danger" disabled={!pwd || code.length !== 6}>Désactiver la double authentification</button>
              <button type="button" className="btn ghost" onClick={() => setDisabling(false)}>Annuler</button></div>
          </form>
        )}
      </div>
    </Panel>
  );
}

export default function MyAccount() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user.full_name);
  const [pwd, setPwd] = useState({ old_password: "", new_password: "", confirm: "" });
  const [rules, setRules] = useState([]);
  useEffect(() => { api.get("/auth/password-rules/").then(({ data }) => setRules(data.rules)).catch(() => {}); }, []);
  const [error, setError] = useState("");

  async function saveName(e) {
    e.preventDefault();
    try {
      const { data } = await api.patch("/me/", { full_name: name });
      setUser(data);
      toast("Nom enregistré.");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  async function changePassword(e) {
    e.preventDefault();
    setError("");
    if (pwd.new_password !== pwd.confirm) { setError("Les deux nouveaux mots de passe ne sont pas identiques."); return; }
    try {
      await api.post("/auth/change-password/", { old_password: pwd.old_password, new_password: pwd.new_password });
      setPwd({ old_password: "", new_password: "", confirm: "" });
      toast("Mot de passe modifié.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <>
      <PageHead title="Mon compte" />
      <div className="grid grid-2" style={{ maxWidth: 1000 }}>
        <Panel title="Profil">
          <dl className="facts" style={{ marginBottom: 16 }}>
            <dt>E-mail</dt><dd>{user.email}</dd>
            <dt>Rôle</dt><dd>{ROLES[user.role]}</dd>
            <dt>Résidence</dt><dd>{[user.home_city, user.home_country].filter(Boolean).join(", ") || "–"}</dd>
            <dt>Profil horaire</dt><dd>{WORK_PROFILES[user.work_profile]}</dd>
            <dt>Compte créé le</dt><dd>{fmtDate(user.created_at)}</dd>
          </dl>
          <form onSubmit={saveName} className="row" style={{ alignItems: "flex-end" }}>
            <Field label="Nom complet" className="grow"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <button className="btn">Enregistrer le nom</button>
          </form>
        </Panel>
        <Panel title="Changer de mot de passe">
          <form onSubmit={changePassword} className="stack" style={{ gap: 12 }}>
            <ErrorBox error={error} />
            <Field label="Mot de passe actuel">
              <input className="input" type="password" autoComplete="current-password" required value={pwd.old_password}
                     onChange={(e) => setPwd({ ...pwd, old_password: e.target.value })} />
            </Field>
            <Field label="Nouveau mot de passe" hint={rules.length ? rules.join(" ") : "10 caractères minimum, pas de mot de passe courant."}>
              <input className="input" type="password" autoComplete="new-password" required value={pwd.new_password}
                     onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} />
            </Field>
            <Field label="Confirmer le nouveau mot de passe">
              <input className="input" type="password" autoComplete="new-password" required value={pwd.confirm}
                     onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} />
            </Field>
            <div><button className="btn primary">Changer le mot de passe</button></div>
          </form>
        </Panel>
        <TwoFactorPanel />
      </div>
    </>
  );
}
