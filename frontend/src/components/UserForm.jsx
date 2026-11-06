import { useState } from "react";
import api, { errorMessage } from "../api/client";
import { PROFILE_TYPES, ROLES, WORK_PROFILES } from "../lib/labels";
import { ErrorBox, Field, Modal } from "./ui";

/** Création ou modification d'un utilisateur (administrateur). */
export default function UserForm({ user, onClose, onSaved }) {
  const editing = Boolean(user);
  const [f, setF] = useState({
    email: user?.email || "", full_name: user?.full_name || "", role: user?.role || "UTILISATEUR",
    is_active: user?.is_active ?? true, home_city: user?.home_city || "", home_country: user?.home_country || "Cameroun",
    home_lat: user?.home_lat ?? "", home_lon: user?.home_lon ?? "", work_profile: user?.work_profile || "JOURNEE", profile_type: user?.profile_type || "PERSONNEL", password: "",
    two_factor_required: user?.two_factor?.required ?? false,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save() {
    setBusy(true);
    setError("");
    const body = { ...f, home_lat: f.home_lat === "" ? null : Number(f.home_lat), home_lon: f.home_lon === "" ? null : Number(f.home_lon) };
    if (!body.password) delete body.password;
    try {
      const { data } = editing ? await api.patch(`/users/${user.id}/`, body) : await api.post("/users/", body);
      onSaved(data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={editing ? "Modifier l'utilisateur" : "Nouvel utilisateur"} onClose={onClose} width={640}
           footer={<><button className="btn" onClick={onClose}>Annuler</button>
             <button className="btn primary" disabled={busy} onClick={save}>{editing ? "Enregistrer" : "Créer l'utilisateur"}</button></>}>
      <ErrorBox error={error} />
      <div className="form-grid" style={{ marginTop: error ? 12 : 0 }}>
        <Field label="Adresse e-mail"><input className="input" type="email" value={f.email} onChange={set("email")} required /></Field>
        <Field label="Nom complet"><input className="input" value={f.full_name} onChange={set("full_name")} /></Field>
        <Field label="Rôle">
          <select className="input" value={f.role} onChange={set("role")}>
            {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Profil dans l'établissement">
          <select className="input" value={f.profile_type} onChange={set("profile_type")}>
            {Object.entries(PROFILE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Profil horaire">
          <select className="input" value={f.work_profile} onChange={set("work_profile")}>
            {Object.entries(WORK_PROFILES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Ville de résidence"><input className="input" value={f.home_city} onChange={set("home_city")} /></Field>
        <Field label="Pays de résidence"><input className="input" value={f.home_country} onChange={set("home_country")} /></Field>
        <Field label="Latitude"><input className="input" type="number" step="any" value={f.home_lat} onChange={set("home_lat")} /></Field>
        <Field label="Longitude"><input className="input" type="number" step="any" value={f.home_lon} onChange={set("home_lon")} /></Field>
        <Field label={editing ? "Nouveau mot de passe" : "Mot de passe"} hint={editing ? "Laisser vide pour ne pas le changer." : "8 caractères minimum, pas uniquement des chiffres."} className="full">
          <input className="input" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} />
        </Field>
        <label className="check full"><input type="checkbox" checked={f.is_active} onChange={set("is_active")} /> Compte actif (un compte désactivé ne peut plus se connecter)</label>
        <label className="check full">
          <input type="checkbox" checked={f.two_factor_required} onChange={set("two_factor_required")} />
          Double authentification obligatoire (compte sensible)
        </label>
      </div>
    </Modal>
  );
}
