"""
FICHIER : apps/detection/features.py

RÔLE
    Transforme chaque tentative de connexion en 16 nombres (les « features ») que le
    modèle de Machine Learning et les règles de sécurité savent lire.
    Exemples : le pays est-il nouveau ? l'appareil est-il nouveau ? combien d'échecs
    dans les 10 dernières minutes ? quelle vitesse de déplacement depuis la dernière
    connexion réussie ?

IMPORTANT
    - On n'utilise QUE des événements passés : une tentative ne « voit » jamais le futur.
    - La MÊME fonction sert à l'entraînement (tout l'historique d'un coup) et au scoring
      en direct (historique d'un utilisateur + nouvel événement). Ainsi, pas de décalage
      entre ce que le modèle a appris et ce qu'il reçoit en production.

UTILISÉ PAR : training.py, dataio.py (via les commandes train_model et score_events)

COLONNES ATTENDUES
    events : event_id, user_id, timestamp (UTC), ip_hash, country, latitude, longitude,
             device_id, success (bool), trusted (bool)
             `trusted` = la connexion a été jugée normale. Seules les connexions réussies
             ET de confiance alimentent l'historique de référence (pays, appareils, IP,
             dernière position). Ainsi, la connexion réussie d'un attaquant ne « pollue »
             pas le profil de la victime.
    users  : user_id, home_lat, home_lon, home_country, usual_hours (heures UTC habituelles)
"""
import math
from collections import defaultdict, deque

import numpy as np
import pandas as pd

# Liste ordonnée des features : le modèle doit toujours les recevoir dans cet ordre.
FEATURE_COLUMNS = [
    "hour_of_day", "is_weekend", "is_night", "success",
    "is_new_country", "is_new_device", "is_new_ip",
    "distance_from_home_km", "hours_since_last_login", "speed_kmh", "seconds_since_last_event",
    "failed_10min", "failed_1h", "distinct_users_from_ip_1h",
    "hour_deviation", "user_login_count",
]


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points GPS (formule de haversine)."""
    r = 6371.0  # rayon moyen de la Terre en km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _hour_deviation(hour, usual_hours):
    """Écart (en heures) entre l'heure de la tentative et l'heure habituelle la plus proche.
    0 = heure habituelle. On tient compte du cercle des 24 h (23 h est proche de 1 h)."""
    if not usual_hours:
        return 0
    best = 24
    for h in usual_hours:
        d = abs(hour - h)
        best = min(best, d, 24 - d)
    return best


def build_features(events, users):
    """Calcule les features de tous les événements reçus.
    Retourne un DataFrame (une ligne par événement) indexé par event_id."""
    ev = events.copy()
    # Les dates sont converties en UTC puis triées dans l'ordre chronologique.
    ev["timestamp"] = pd.to_datetime(ev["timestamp"], utc=True, format="ISO8601")
    ev = ev.sort_values(["timestamp", "event_id"]).reset_index(drop=True)
    # Secondes depuis 1970. On évite astype("int64") car, avec pandas 3, la résolution du
    # temps peut changer (micro/nanosecondes) et fausserait tous les calculs de durée.
    ev["t"] = (ev["timestamp"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    u_info = users.set_index("user_id")

    n = len(ev)
    # Un tableau de zéros par feature ; on le remplit événement par événement.
    cols = {name: np.zeros(n, dtype=float) for name in FEATURE_COLUMNS}

    # --- Feature « distinct_users_from_ip_1h » ---
    # On parcourt tous les événements dans l'ordre du temps et, pour chaque adresse IP
    # (pseudonymisée), on garde les connexions de la dernière heure. On compte ensuite
    # combien de comptes différents cette source a visés (détecte le credential stuffing).
    ip_windows = defaultdict(deque)
    t_arr = ev["t"].to_numpy()
    ip_arr = ev["ip_hash"].to_numpy()
    uid_arr = ev["user_id"].to_numpy()
    for i in range(n):
        dq = ip_windows[ip_arr[i]]
        while dq and t_arr[i] - dq[0][0] > 3600:  # on oublie ce qui date de plus d'1 h
            dq.popleft()
        cols["distinct_users_from_ip_1h"][i] = len({u for _, u in dq})
        dq.append((t_arr[i], uid_arr[i]))

    # --- Autres features : calculées utilisateur par utilisateur ---
    # On extrait les colonnes en tableaux numpy une seule fois (beaucoup plus rapide).
    country_arr = ev["country"].to_numpy()
    dev_arr = ev["device_id"].to_numpy()
    lat_arr = ev["latitude"].to_numpy(dtype=float)
    lon_arr = ev["longitude"].to_numpy(dtype=float)
    succ_arr = ev["success"].to_numpy(dtype=bool)
    trust_arr = ev["trusted"].to_numpy(dtype=bool)
    ts_hour = ev["timestamp"].dt.hour.to_numpy()
    ts_dow = ev["timestamp"].dt.dayofweek.to_numpy()

    for uid, idx in ev.groupby("user_id").indices.items():
        info = u_info.loc[uid]
        home_lat, home_lon, home_country = float(info["home_lat"]), float(info["home_lon"]), info["home_country"]
        usual = list(info["usual_hours"])
        # Mémoire de l'utilisateur : ce qu'il a déjà fait de façon légitime.
        known_countries = {home_country}
        known_devices, known_ips = set(), set()
        last_succ_t = last_succ_lat = last_succ_lon = None  # dernière connexion réussie et de confiance
        last_event_t = None                                  # dernier événement (réussi ou non)
        fails = deque()                                      # horodatages des échecs récents
        count = 0                                            # nombre d'événements déjà vus
        for i in idx:  # idx est dans l'ordre chronologique
            t = t_arr[i]
            # Échecs des 10 dernières minutes et de la dernière heure (avant cette tentative).
            while fails and t - fails[0] > 3600:
                fails.popleft()
            cols["failed_1h"][i] = len(fails)
            cols["failed_10min"][i] = sum(1 for x in fails if t - x <= 600)

            # Caractéristiques de la tentative elle-même.
            cols["hour_of_day"][i] = ts_hour[i]
            cols["is_weekend"][i] = 1 if ts_dow[i] >= 5 else 0
            cols["is_night"][i] = 1 if ts_hour[i] <= 5 else 0  # nuit = de 0 h à 5 h
            cols["success"][i] = 1 if succ_arr[i] else 0
            # « Nouveau » = jamais vu lors d'une connexion réussie et de confiance.
            cols["is_new_country"][i] = 0 if country_arr[i] in known_countries else 1
            cols["is_new_device"][i] = 0 if dev_arr[i] in known_devices else 1
            cols["is_new_ip"][i] = 0 if ip_arr[i] in known_ips else 1
            cols["distance_from_home_km"][i] = haversine_km(home_lat, home_lon, lat_arr[i], lon_arr[i])
            cols["hour_deviation"][i] = _hour_deviation(int(ts_hour[i]), usual)
            cols["user_login_count"][i] = count

            # Délai et vitesse implicite depuis la dernière connexion réussie.
            # Une vitesse > 900 km/h = déplacement impossible (voir rules.py, règle R2).
            if last_succ_t is None:
                cols["hours_since_last_login"][i] = 720  # aucune connexion connue : valeur par défaut (30 jours)
                cols["speed_kmh"][i] = 0
            else:
                hours = (t - last_succ_t) / 3600.0
                dist = haversine_km(last_succ_lat, last_succ_lon, lat_arr[i], lon_arr[i])
                cols["hours_since_last_login"][i] = min(hours, 720)
                cols["speed_kmh"][i] = min(dist / max(hours, 1 / 60), 3000)  # plafonné pour éviter les valeurs absurdes
            # Cadence : secondes écoulées depuis le dernier événement (très court = attaque automatique).
            cols["seconds_since_last_event"][i] = 86400 if last_event_t is None else min(t - last_event_t, 86400)

            # Mise à jour de la mémoire APRÈS le calcul : on n'utilise que le passé.
            last_event_t = t
            count += 1
            if succ_arr[i] and trust_arr[i]:
                known_countries.add(country_arr[i])
                known_devices.add(dev_arr[i])
                known_ips.add(ip_arr[i])
                last_succ_t, last_succ_lat, last_succ_lon = t, lat_arr[i], lon_arr[i]
            if not succ_arr[i]:
                fails.append(t)

    feats = pd.DataFrame(cols)
    feats.index = ev["event_id"].to_numpy()
    feats.index.name = "event_id"
    return feats[FEATURE_COLUMNS]