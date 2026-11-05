export const LEVELS = {
  NORMAL: { label: "Normal", tone: "ok", range: "0 à 29" },
  SUSPECT: { label: "Suspect", tone: "warn", range: "30 à 59" },
  HAUT_RISQUE: { label: "Risque élevé", tone: "high", range: "60 à 84" },
  CRITIQUE: { label: "Critique", tone: "danger", range: "85 à 100" },
};
export const SEVERITIES = {
  FAIBLE: { label: "Faible", tone: "warn" },
  HAUTE: { label: "Haute", tone: "high" },
  CRITIQUE: { label: "Critique", tone: "danger" },
};
export const STATUSES = {
  NOUVELLE: { label: "Nouvelle", tone: "danger" },
  EN_COURS: { label: "En cours", tone: "info" },
  TRAITEE: { label: "Traitée", tone: "ok" },
  FAUSSE_ALERTE: { label: "Fausse alerte", tone: "neutral" },
};
export const ROLES = {
  ADMIN: "Administrateur",
  RESPONSABLE: "Responsable d'institution",
  UTILISATEUR: "Utilisateur",
};
export const WORK_PROFILES = {
  JOURNEE: "Journée (7h-18h)",
  SOIREE: "Soirée (17h-23h)",
  MIXTE: "Mixte",
};
export const SOURCES = {
  DATASET: "Jeu de données",
  LIVE: "Connexion réelle",
  SIMULATOR: "Simulateur",
};
export const RULES = {
  ECHECS_REPETES: "Échecs répétés",
  ATTAQUE_MASSE: "Attaque en masse",
  VOYAGE_IMPOSSIBLE: "Voyage impossible",
  NOUVEAU_PAYS: "Nouveau pays",
  NOUVEL_APPAREIL: "Nouvel appareil",
  HEURE_INHABITUELLE: "Horaire inhabituel",
  IP_MAUVAISE_REPUTATION: "IP à mauvaise réputation",
  COMPTE_DORMANT: "Compte dormant",
  SUCCES_APRES_ECHECS: "Succès après échecs",
  ECHECS_IP: "Rafale d'échecs IP",
  ELOIGNEMENT: "Éloignement",
  SOURCE_DE_CONFIANCE: "Source de confiance",
};
export const ATTACKS = {
  aucune: "Aucune (normal)",
  force_brute: "Force brute",
  credential_stuffing: "Credential stuffing",
  prise_de_controle: "Prise de contrôle",
  voyage_impossible: "Voyage impossible",
  heure_inhabituelle: "Heure inhabituelle",
  nouvel_appareil: "Nouvel appareil / pays",
};
export const GROUND_TRUTH = { normal: "Normal", suspect: "Suspect", haut_risque: "Haut risque" };
export const NOTIFICATION_KINDS = {
  CONNEXION_INHABITUELLE: "Connexion inhabituelle",
  MOT_DE_PASSE: "Mot de passe",
  COMPTE_BLOQUE: "Compte bloqué",
  DOUBLE_AUTH: "Double authentification",
};
export const LIST_TYPES = { CONFIANCE: "Confiance", BLOCAGE: "Blocage" };
export const LIST_KINDS = { IP: "Adresse IP", PAYS: "Pays", APPAREIL: "Appareil" };
export const AUDIT_ACTIONS = {
  LOGIN: "Connexion",
  LOGIN_FAILED: "Échec de connexion",
  LOGIN_BLOCKED: "Connexion refusée (compte bloqué)",
  LOGOUT: "Déconnexion",
  PASSWORD_CHANGED: "Mot de passe modifié",
  USER_CREATED: "Utilisateur créé",
  USER_UPDATED: "Utilisateur modifié",
  USER_DELETED: "Utilisateur supprimé",
  USER_BLOCKED: "Compte bloqué",
  USER_UNBLOCKED: "Compte débloqué",
  USER_AUTO_BLOCKED: "Blocage automatique",
  ALERT_UPDATED: "Alerte mise à jour",
  ALERT_BULK_UPDATED: "Alertes mises à jour en lot",
  RULE_UPDATED: "Règle modifiée",
  CONFIG_UPDATED: "Paramètres modifiés",
  MODEL_TRAINED: "Modèle entraîné",
  MODEL_ACTIVATED: "Modèle activé",
  SCORES_RECOMPUTED: "Scores recalculés",
  SIMULATION: "Simulation",
  EVENT_REPORTED: "Connexion signalée",
  SCORING_ERROR: "Erreur de calcul du score",
  ACCOUNT_LOCKED: "Verrouillage après échecs",
  LOGIN_REFUSED_CRITICAL: "Connexion refusée (critique)",
  LOGIN_REFUSED_BLOCKLIST: "Connexion refusée (liste de blocage)",
  TWO_FACTOR_REQUIRED: "Seconde étape demandée",
  TWO_FACTOR_FAILED: "Code de vérification refusé",
  TWO_FACTOR_ENABLED: "Double authentification activée",
  TWO_FACTOR_DISABLED: "Double authentification désactivée",
  TWO_FACTOR_RESET: "Double authentification réinitialisée",
  PASSWORD_RESET_REQUESTED: "Réinitialisation demandée",
  PASSWORD_RESET: "Mot de passe réinitialisé",
  USER_ROLE_CHANGED: "Rôle modifié",
  USER_DEACTIVATED: "Compte désactivé",
  EVENT_CONFIRMED: "Connexion confirmée par l'utilisateur",
  LIST_ENTRY_ADDED: "Ajout à une liste",
  LIST_ENTRY_REMOVED: "Retrait d'une liste",
  EXPORT: "Export",
  DATASET_IMPORTED: "Jeu de données importé",
  DATA_PURGED: "Données purgées",
};
