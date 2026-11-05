// Espace courant : « /console » (administration) ou « /espace » (client).
import { useLocation } from "react-router-dom";

export function useBase() {
  const { pathname } = useLocation();
  return pathname.startsWith("/espace") ? "/espace" : "/console";
}

/** Espace de destination d'un utilisateur après la connexion (fourni par le serveur). */
export function homeFor(user) {
  if (!user) return "/connexion";
  return user.home || (user.role === "UTILISATEUR" ? "/espace" : "/console");
}
