
"""
FICHIER : apps/detection/dataio.py

RÔLE
    Assure la liaison entre Django et pandas.
    Transforme les événements et les utilisateurs en DataFrames
    exploitables par le moteur de détection.

AMELIORATIONS
    - Conservation des coordonnées GPS manquantes.
    - Utilisation de l'empreinte de l'appareil.
    - Gestion des résultats vides.
    - Détermination sécurisée des connexions de confiance.
"""

import numpy as np
import pandas as pd

from apps.accounts.models import User


EVENT_FIELDS = (
    "id",
    "user_id",
    "timestamp",
    "ip_hash",
    "country",
    "latitude",
    "longitude",
    "device_id",
    "device__fingerprint",
    "success",
    "label",
    "evaluation__level",
)

USER_FIELDS = (
    "id",
    "home_lat",
    "home_lon",
    "home_country",
    "risk_profile__usual_hours",
)


def events_frame(queryset):
    """
    Convertit les événements Django en DataFrame.

    La colonne trusted indique si une connexion peut alimenter
    l'historique de référence de l'utilisateur.
    """

    df = pd.DataFrame(list(queryset.values(*EVENT_FIELDS)))

    if df.empty:
        return pd.DataFrame(columns=[
            "event_id", "user_id", "timestamp", "ip_hash",
            "country", "latitude", "longitude", "device_id",
            "success", "label", "eval_level", "trusted"
        ])

    df = df.rename(columns={
        "id": "event_id",
        "evaluation__level": "eval_level",
    })

    # Utiliser l'empreinte de l'appareil lorsqu'elle existe.
    # Sinon, conserver l'identifiant de l'appareil.
    fingerprint = df["device__fingerprint"]

    fingerprint_available = (
        fingerprint.notna()
        & fingerprint.astype(str).str.strip().ne("")
    )

    df["device_id"] = fingerprint.where(
        fingerprint_available,
        df["device_id"]
    )

    # Une position inconnue reste inconnue.
    # Ne surtout pas remplacer les coordonnées manquantes par (0, 0).
    df["latitude"] = pd.to_numeric(
        df["latitude"], errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"], errors="coerce"
    )

    # Déterminer les connexions de confiance.
    has_label = df["label"].fillna("").astype(str).str.strip().ne("")

    trusted_dataset = df["label"].eq("normal")

    trusted_live = df["eval_level"].eq("NORMAL")

    df["trusted"] = np.where(
        has_label,
        trusted_dataset,
        trusted_live
    ).astype(bool)

    return df.drop(columns=["device__fingerprint"])


def users_frame(user_ids):
    """
    Récupère les informations de référence des utilisateurs.

    Les coordonnées manquantes restent NaN afin que le moteur
    puisse reconnaître une position inconnue.
    """

    ids = list(user_ids)

    columns = [
        "id",
        "home_lat",
        "home_lon",
        "home_country",
        "risk_profile__usual_hours",
    ]

    if not ids:
        return pd.DataFrame(columns=[
            "user_id",
            "home_lat",
            "home_lon",
            "home_country",
            "usual_hours",
        ])

    rows = User.objects.filter(
        id__in=[int(i) for i in ids]
    ).values(*USER_FIELDS)

    df = pd.DataFrame(list(rows), columns=columns)

    df = df.rename(columns={
        "id": "user_id",
        "risk_profile__usual_hours": "usual_hours",
    })

    # Convertir les coordonnées en nombres.
    # Les valeurs absentes deviennent NaN.
    df["home_lat"] = pd.to_numeric(
        df["home_lat"], errors="coerce"
    )

    df["home_lon"] = pd.to_numeric(
        df["home_lon"], errors="coerce"
    )

    # Pays inconnu : chaîne vide.
    df["home_country"] = df["home_country"].fillna("")

    # Un profil sans heures habituelles reçoit une liste vide.
    df["usual_hours"] = df["usual_hours"].apply(
        lambda value: value if isinstance(value, list) else []
    )

    return df

