"""
FICHIER : apps/detection/dataio.py

RÔLE
    Fait le lien entre la base de données (Django / PostgreSQL) et le calcul des features
    (pandas). Il transforme les événements et les utilisateurs de la base en DataFrames.

    La colonne « trusted » indique si une connexion est considérée comme légitime :
      - pour le jeu de données : on se fie à l'étiquette réelle (label == "normal") ;
      - pour une connexion en direct : on se fie au verdict déjà rendu par le détecteur.
    Seules les connexions « de confiance » alimentent l'historique de référence d'un
    utilisateur (voir features.py).

UTILISÉ PAR : commandes train_model et score_events
"""
import numpy as np
import pandas as pd

from apps.accounts.models import User

# Champs lus en base pour chaque événement (evaluation__level = niveau de risque déjà calculé, s'il existe).
EVENT_FIELDS = ("id", "user_id", "timestamp", "ip_hash", "country", "latitude", "longitude",
                "device_id", "success", "label", "evaluation__level")


def events_frame(queryset):
    """DataFrame des événements, avec la colonne `trusted` (connexion jugée normale)."""
    df = pd.DataFrame(list(queryset.values(*EVENT_FIELDS)))
    if df.empty:
        return df
    df = df.rename(columns={"id": "event_id", "evaluation__level": "eval_level"})
    # Valeurs manquantes : appareil inconnu = -1, position inconnue = (0, 0).
    df["device_id"] = df["device_id"].fillna(-1)
    df["latitude"] = df["latitude"].fillna(0.0)
    df["longitude"] = df["longitude"].fillna(0.0)
    # Jeu de données : on se fie à l'étiquette ; sinon au verdict déjà rendu par le détecteur.
    has_label = df["label"].fillna("") != ""
    df["trusted"] = np.where(has_label, df["label"] == "normal", df["eval_level"] == "NORMAL")
    return df


def users_frame(user_ids):
    """DataFrame des utilisateurs : position d'attache et heures de connexion habituelles."""
    rows = User.objects.filter(id__in=[int(i) for i in user_ids]).values(
        "id", "home_lat", "home_lon", "home_country", "risk_profile__usual_hours")
    df = pd.DataFrame(list(rows)).rename(columns={"id": "user_id", "risk_profile__usual_hours": "usual_hours"})
    # Un utilisateur sans profil a une liste d'heures vide ; les positions manquantes valent 0.
    df["usual_hours"] = df["usual_hours"].apply(lambda v: v if isinstance(v, list) else [])
    df["home_lat"] = df["home_lat"].fillna(0.0)
    df["home_lon"] = df["home_lon"].fillna(0.0)
    df["home_country"] = df["home_country"].fillna("")
    return df