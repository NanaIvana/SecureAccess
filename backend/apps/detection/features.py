
"""
FICHIER : apps/detection/features.py

RÔLE
    Transforme chaque tentative de connexion en 16 caractéristiques
    numériques utilisées par le modèle ML et les règles de sécurité.

PRINCIPES
    - Les événements sont traités chronologiquement.
    - Une tentative ne voit jamais les événements futurs.
    - Seules les connexions réussies ET de confiance enrichissent
      l'historique de référence de l'utilisateur.
    - Les données GPS inconnues ne génèrent pas de fausses distances.
    - Les valeurs manquantes ne sont pas considérées comme de
      nouveaux appareils, pays ou IP.

COMPATIBILITÉ
    Les 16 caractéristiques et leur ordre sont conservés.
"""

import math
from collections import defaultdict, deque

import numpy as np
import pandas as pd


# ATTENTION :
# Ne pas modifier les noms ou l'ordre sans réentraîner le modèle.
FEATURE_COLUMNS = [
    "hour_of_day", "is_weekend", "is_night", "success",
    "is_new_country", "is_new_device", "is_new_ip",
    "distance_from_home_km", "hours_since_last_login",
    "speed_kmh", "seconds_since_last_event",
    "failed_10min", "failed_1h", "distinct_users_from_ip_1h",
    "hour_deviation", "user_login_count",
]


EVENT_REQUIRED = [
    "event_id", "user_id", "timestamp", "ip_hash", "country",
    "latitude", "longitude", "device_id", "success", "trusted",
]

USER_REQUIRED = [
    "user_id", "home_lat", "home_lon", "home_country", "usual_hours",
]


def _is_missing(value):
    """Indique si une valeur est absente."""
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _valid_identifier(value):
    """Vérifie qu'un identifiant (IP, appareil, pays) est exploitable."""
    if _is_missing(value):
        return False

    if isinstance(value, str) and not value.strip():
        return False

    return True


def _valid_coordinates(latitude, longitude):
    """Vérifie que les coordonnées GPS sont présentes et géographiquement valides."""
    if _is_missing(latitude) or _is_missing(longitude):
        return False

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False

    return (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calcule la distance en kilomètres entre deux positions GPS.

    Retourne 0 si l'une des positions est invalide.
    """
    if not (
        _valid_coordinates(lat1, lon1)
        and _valid_coordinates(lat2, lon2)
    ):
        return 0.0

    r = 6371.0

    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))

    delta_lat = math.radians(float(lat2) - float(lat1))
    delta_lon = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(delta_lon / 2) ** 2
    )

    # Protection contre les petites erreurs numériques.
    a = min(1.0, max(0.0, a))

    return 2 * r * math.asin(math.sqrt(a))


def _hour_deviation(hour, usual_hours):
    """
    Calcule l'écart entre l'heure actuelle et les heures habituelles.

    Exemple :
        Heure actuelle : 23 h
        Heure habituelle : 1 h
        Écart : 2 heures.
    """
    if not isinstance(usual_hours, (list, tuple)) or not usual_hours:
        return 0.0

    best = 24.0

    for value in usual_hours:
        try:
            h = float(value)

            if not math.isfinite(h) or not 0 <= h < 24:
                continue

            deviation = abs(hour - h)
            best = min(best, deviation, 24 - deviation)

        except (TypeError, ValueError):
            continue

    return 0.0 if best == 24.0 else best


def _get_user_info(user_id, user_info):
    """
    Récupère les informations de référence d'un utilisateur.

    Si aucun profil n'existe, utilise des valeurs neutres.
    Cela évite de faire échouer toute l'évaluation.
    """
    if user_id not in user_info.index:
        return {
            "home_lat": np.nan,
            "home_lon": np.nan,
            "home_country": "",
            "usual_hours": [],
        }

    info = user_info.loc[user_id]

    # En cas de doublon dans le DataFrame des utilisateurs,
    # on refuse de choisir arbitrairement un profil.
    if isinstance(info, pd.DataFrame):
        raise ValueError(
            f"Plusieurs profils trouvés pour l'utilisateur {user_id}."
        )

    return {
        "home_lat": info["home_lat"],
        "home_lon": info["home_lon"],
        "home_country": info["home_country"],
        "usual_hours": info["usual_hours"],
    }


def build_features(events, users):
    """
    Calcule les 16 caractéristiques pour chaque événement.

    Paramètres :
        events : DataFrame contenant les événements de connexion.
        users  : DataFrame contenant les profils de référence.

    Retour :
        DataFrame indexé par event_id.
    """

    # ---------------------------------------------------------
    # 1. Vérification des données reçues
    # ---------------------------------------------------------

    missing_events = set(EVENT_REQUIRED) - set(events.columns)

    if missing_events:
        raise ValueError(
            f"Colonnes manquantes dans events : {sorted(missing_events)}"
        )

    missing_users = set(USER_REQUIRED) - set(users.columns)

    if missing_users:
        raise ValueError(
            f"Colonnes manquantes dans users : {sorted(missing_users)}"
        )

    if events["event_id"].duplicated().any():
        raise ValueError("Les event_id doivent être uniques.")

    # Un historique vide ne doit pas provoquer d'erreur.
    if events.empty:
        empty = pd.DataFrame(columns=FEATURE_COLUMNS)
        empty.index.name = "event_id"
        return empty

    # ---------------------------------------------------------
    # 2. Préparation et tri chronologique
    # ---------------------------------------------------------

    ev = events.copy()

    ev["timestamp"] = pd.to_datetime(
        ev["timestamp"],
        utc=True,
        format="ISO8601",
        errors="coerce",
    )

    if ev["timestamp"].isna().any():
        raise ValueError("Certains événements possèdent une date invalide.")

    ev = ev.sort_values(
        ["timestamp", "event_id"]
    ).reset_index(drop=True)

    # Nombre de secondes depuis le 1er janvier 1970.
    ev["t"] = (
        ev["timestamp"] - pd.Timestamp("1970-01-01", tz="UTC")
    ).dt.total_seconds()

    user_info = users.set_index("user_id")

    n = len(ev)

    cols = {
        name: np.zeros(n, dtype=float)
        for name in FEATURE_COLUMNS
    }

    t_arr = ev["t"].to_numpy()
    ip_arr = ev["ip_hash"].to_numpy()
    uid_arr = ev["user_id"].to_numpy()

    # ---------------------------------------------------------
    # 3. Détection des IP utilisées par plusieurs comptes
    # ---------------------------------------------------------

    # Pour chaque IP, conserver les événements de la dernière heure.
    ip_windows = defaultdict(deque)

    for i in range(n):
        ip = ip_arr[i]
        current_time = t_arr[i]

        # Une IP inconnue ne doit pas être considérée comme
        # une source commune à tous les utilisateurs.
        if not _valid_identifier(ip):
            continue

        dq = ip_windows[ip]

        while dq and current_time - dq[0][0] > 3600:
            dq.popleft()

        cols["distinct_users_from_ip_1h"][i] = len({
            user_id for _, user_id in dq
        })

        dq.append((current_time, uid_arr[i]))

    # ---------------------------------------------------------
    # 4. Préparation des autres caractéristiques
    # ---------------------------------------------------------

    country_arr = ev["country"].to_numpy()
    device_arr = ev["device_id"].to_numpy()

    lat_arr = pd.to_numeric(
        ev["latitude"], errors="coerce"
    ).to_numpy(dtype=float)

    lon_arr = pd.to_numeric(
        ev["longitude"], errors="coerce"
    ).to_numpy(dtype=float)

    success_arr = ev["success"].to_numpy(dtype=bool)
    trusted_arr = ev["trusted"].to_numpy(dtype=bool)

    hours = ev["timestamp"].dt.hour.to_numpy()
    days = ev["timestamp"].dt.dayofweek.to_numpy()

    # ---------------------------------------------------------
    # 5. Calcul de l'historique de chaque utilisateur
    # ---------------------------------------------------------

    for uid, indices in ev.groupby("user_id", sort=False).indices.items():

        info = _get_user_info(uid, user_info)

        home_lat = info["home_lat"]
        home_lon = info["home_lon"]
        home_country = info["home_country"]
        usual_hours = info["usual_hours"]

        home_gps_valid = _valid_coordinates(home_lat, home_lon)

        # Historique des connexions reconnues comme légitimes.
        known_countries = set()
        known_devices = set()
        known_ips = set()

        if _valid_identifier(home_country):
            known_countries.add(home_country)

        last_success_time = None
        last_success_lat = None
        last_success_lon = None

        last_event_time = None

        failures = deque()

        login_count = 0

        # Les indices suivent déjà l'ordre chronologique.
        for i in indices:

            current_time = t_arr[i]

            country = country_arr[i]
            device = device_arr[i]
            ip = ip_arr[i]

            latitude = lat_arr[i]
            longitude = lon_arr[i]

            current_gps_valid = _valid_coordinates(
                latitude, longitude
            )

            # -------------------------------------------------
            # 5.1 Échecs récents
            # -------------------------------------------------

            while (
                failures
                and current_time - failures[0] > 3600
            ):
                failures.popleft()

            cols["failed_1h"][i] = len(failures)

            cols["failed_10min"][i] = sum(
                1 for failure_time in failures
                if current_time - failure_time <= 600
            )

            # -------------------------------------------------
            # 5.2 Heure et calendrier
            # -------------------------------------------------

            cols["hour_of_day"][i] = hours[i]

            cols["is_weekend"][i] = (
                1 if days[i] >= 5 else 0
            )

            cols["is_night"][i] = (
                1 if hours[i] <= 5 else 0
            )

            cols["success"][i] = (
                1 if success_arr[i] else 0
            )

            # -------------------------------------------------
            # 5.3 Pays, appareil et adresse IP
            # -------------------------------------------------

            # Une donnée absente n'est pas automatiquement nouvelle.
            cols["is_new_country"][i] = (
                1 if (
                    _valid_identifier(country)
                    and country not in known_countries
                ) else 0
            )

            cols["is_new_device"][i] = (
                1 if (
                    _valid_identifier(device)
                    and device not in known_devices
                ) else 0
            )

            cols["is_new_ip"][i] = (
                1 if (
                    _valid_identifier(ip)
                    and ip not in known_ips
                ) else 0
            )

            # -------------------------------------------------
            # 5.4 Distance depuis le domicile
            # -------------------------------------------------

            if home_gps_valid and current_gps_valid:
                cols["distance_from_home_km"][i] = haversine_km(
                    home_lat,
                    home_lon,
                    latitude,
                    longitude,
                )
            else:
                # Position inconnue : aucune distance fictive.
                cols["distance_from_home_km"][i] = 0.0

            # -------------------------------------------------
            # 5.5 Écart par rapport aux heures habituelles
            # -------------------------------------------------

            cols["hour_deviation"][i] = _hour_deviation(
                int(hours[i]),
                usual_hours,
            )

            cols["user_login_count"][i] = login_count

            # -------------------------------------------------
            # 5.6 Délai depuis la dernière connexion réussie
            # -------------------------------------------------

            if last_success_time is None:

                cols["hours_since_last_login"][i] = 720
                cols["speed_kmh"][i] = 0.0

            else:

                elapsed_hours = (
                    current_time - last_success_time
                ) / 3600.0

                cols["hours_since_last_login"][i] = min(
                    max(elapsed_hours, 0.0),
                    720,
                )

                previous_gps_valid = _valid_coordinates(
                    last_success_lat,
                    last_success_lon,
                )

                if (
                    current_gps_valid
                    and previous_gps_valid
                    and elapsed_hours > 0
                ):

                    distance = haversine_km(
                        last_success_lat,
                        last_success_lon,
                        latitude,
                        longitude,
                    )

                    speed = distance / max(
                        elapsed_hours,
                        1 / 60,
                    )

                    cols["speed_kmh"][i] = min(
                        speed,
                        3000,
                    )

                else:
                    # Sans deux positions valides, impossible
                    # de calculer une vitesse fiable.
                    cols["speed_kmh"][i] = 0.0

            # -------------------------------------------------
            # 5.7 Temps depuis le dernier événement
            # -------------------------------------------------

            if last_event_time is None:
                cols["seconds_since_last_event"][i] = 86400
            else:
                elapsed_seconds = max(
                    current_time - last_event_time,
                    0.0,
                )

                cols["seconds_since_last_event"][i] = min(
                    elapsed_seconds,
                    86400,
                )

            # -------------------------------------------------
            # 6. Mise à jour de l'historique APRÈS le calcul
            # -------------------------------------------------

            last_event_time = current_time
            login_count += 1

            # Seules les connexions réussies et de confiance
            # enrichissent l'historique de référence.
            if success_arr[i] and trusted_arr[i]:

                if _valid_identifier(country):
                    known_countries.add(country)

                if _valid_identifier(device):
                    known_devices.add(device)

                if _valid_identifier(ip):
                    known_ips.add(ip)

                last_success_time = current_time

                # Une connexion sans GPS ne doit pas remplacer
                # une ancienne position valide par une position fictive.
                if current_gps_valid:
                    last_success_lat = latitude
                    last_success_lon = longitude
                else:
                    last_success_lat = None
                    last_success_lon = None

            # Seules les tentatives échouées alimentent
            # le compteur des échecs récents.
            if not success_arr[i]:
                failures.append(current_time)

    # ---------------------------------------------------------
    # 7. Construction du DataFrame final
    # ---------------------------------------------------------

    features = pd.DataFrame(cols)

    features.index = ev["event_id"].to_numpy()
    features.index.name = "event_id"

    # Garantie : exactement les 16 features attendues.
    return features[FEATURE_COLUMNS]


