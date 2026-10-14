"""Générateur du jeu de données synthétique de connexions (SecureAccess).

Principe : on simule d'abord le comportement habituel de chaque utilisateur,
puis on injecte des scénarios d'attaque. Chaque événement reçoit une étiquette
de vérité terrain (label) et un type d'attaque (attack_type).

Ce module ne dépend pas de Django : il produit des listes de dictionnaires.
"""
import hashlib
import hmac
import math
import random
import unicodedata
from datetime import datetime, timedelta, timezone

import numpy as np

UTC = timezone.utc
DATASET_DOMAIN = "demo.secureaccess.test"

# (ville, latitude, longitude, poids)
CAMEROON_CITIES = [
    ("Yaoundé", 3.848, 11.502, 0.33),
    ("Douala", 4.051, 9.768, 0.30),
    ("Bafoussam", 5.478, 10.418, 0.08),
    ("Garoua", 9.301, 13.397, 0.06),
    ("Bamenda", 5.959, 10.146, 0.07),
    ("Maroua", 10.591, 14.316, 0.04),
    ("Ngaoundéré", 7.327, 13.584, 0.04),
    ("Bertoua", 4.577, 13.684, 0.03),
    ("Kribi", 2.940, 9.910, 0.025),
    ("Limbé", 4.024, 9.215, 0.025),
]

# (ville, pays, latitude, longitude)
FOREIGN_CITIES = [
    ("Lagos", "Nigeria", 6.524, 3.379),
    ("Paris", "France", 48.857, 2.352),
    ("New York", "États-Unis", 40.713, -74.006),
    ("Moscou", "Russie", 55.756, 37.617),
    ("Pékin", "Chine", 39.904, 116.407),
    ("Mumbai", "Inde", 19.076, 72.878),
    ("São Paulo", "Brésil", -23.550, -46.633),
    ("Casablanca", "Maroc", 33.573, -7.589),
    ("Bucarest", "Roumanie", 44.430, 26.100),
    ("Istanbul", "Turquie", 41.008, 28.978),
    ("Hanoï", "Viêt Nam", 21.028, 105.854),
    ("Johannesburg", "Afrique du Sud", -26.204, 28.047),
]

USER_DEVICES = [
    ("Ordinateur", "Windows 11", "Chrome"),
    ("Ordinateur", "Windows 10", "Edge"),
    ("Ordinateur", "macOS", "Safari"),
    ("Ordinateur", "Ubuntu", "Firefox"),
    ("Mobile", "Android", "Chrome"),
    ("Mobile", "iOS", "Safari"),
    ("Tablette", "iPadOS", "Safari"),
]
ATTACKER_DEVICES = [
    ("Ordinateur", "Linux", "Firefox"),
    ("Ordinateur", "Windows 10", "Chrome"),
    ("Ordinateur", "Linux", "Chrome Headless"),
    ("Mobile", "Android", "Chrome"),
]

FIRST_NAMES = ["Jean", "Marie", "Paul", "Aline", "Brice", "Carine", "Didier", "Estelle", "Franck", "Grace",
               "Hervé", "Inès", "Joël", "Karine", "Landry", "Mireille", "Nadège", "Olivier", "Patrick",
               "Rosine", "Serge", "Thérèse", "Ulrich", "Vanessa", "Yannick", "Zita"]
LAST_NAMES = ["Mballa", "Fotso", "Kamga", "Tchouamo", "Ngono", "Essomba", "Onana", "Atangana", "Nkoulou",
              "Mbarga", "Tagne", "Djomo", "Kouam", "Njoya", "Manga", "Mvondo", "Owona", "Bella", "Abega", "Foka"]

# Heures de connexion habituelles (heure UTC) avec leur poids, selon le profil de travail
HOUR_WEIGHTS = {
    "JOURNEE": {7: 2, 8: 6, 9: 8, 10: 6, 11: 5, 12: 3, 13: 6, 14: 6, 15: 5, 16: 4, 17: 3, 18: 1},
    "SOIREE": {17: 3, 18: 5, 19: 6, 20: 7, 21: 6, 22: 3, 23: 1},
    "MIXTE": {7: 3, 8: 6, 9: 5, 10: 4, 11: 3, 18: 4, 19: 6, 20: 6, 21: 4, 22: 2},
}
PROFILE_CHOICES = [("JOURNEE", 0.60), ("SOIREE", 0.15), ("MIXTE", 0.25)]

# Nombre d'épisodes d'attaque (ajustables)
DEFAULT_ATTACKS = {
    "force_brute": 60,
    "credential_stuffing": 25,
    "prise_de_controle": 60,
    "voyage_impossible": 120,
    "heure_inhabituelle": 1400,
    "nouvel_appareil": 1350,
}
WARMUP_DAYS = 10  # aucune attaque pendant les 10 premiers jours (historique de référence)


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower().replace(" ", "")


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def generate(n_users=300, seed=42, ip_secret="dev-secret", start=None, days=182, attacks=None):
    """Retourne un dict {users, devices, events} (listes de dictionnaires)."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    start = start or datetime(2026, 4, 13, tzinfo=UTC)  # un lundi
    attacks = {**DEFAULT_ATTACKS, **(attacks or {})}

    def ip_hash():
        ip = f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        return hmac.new(ip_secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]

    def fingerprint():
        return f"{rng.getrandbits(128):032x}"

    def weighted(pairs):
        names, weights = zip(*pairs)
        return rng.choices(names, weights=weights, k=1)[0]

    # ---------------- utilisateurs, appareils, habitudes ----------------
    users, devices, events = [], [], []
    state = []  # état interne par utilisateur
    cities = [(c[0], c[1], c[2]) for c in CAMEROON_CITIES]
    city_weights = [c[3] for c in CAMEROON_CITIES]

    def add_device(user_idx, dev_tuple):
        d = {"idx": len(devices), "user_idx": user_idx, "fingerprint": fingerprint(),
             "device_type": dev_tuple[0], "os": dev_tuple[1], "browser": dev_tuple[2]}
        devices.append(d)
        return d["idx"]

    for i in range(n_users):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city = rng.choices(cities, weights=city_weights, k=1)[0]
        profile = weighted(PROFILE_CHOICES)
        users.append({
            "idx": i, "email": f"{slug(first)}.{slug(last)}{i + 1:03d}@{DATASET_DOMAIN}",
            "full_name": f"{first} {last}", "role": "UTILISATEUR",
            "home_city": city[0], "home_country": "Cameroun", "home_lat": city[1], "home_lon": city[2],
            "work_profile": profile,
        })
        n_dev = rng.choices([1, 2, 3], weights=[0.35, 0.45, 0.20], k=1)[0]
        dev_ids = [add_device(i, d) for d in rng.sample(USER_DEVICES, n_dev)]
        state.append({
            "devices": dev_ids,
            "home_ips": [ip_hash() for _ in range(rng.choice([1, 2]))],
            "activity": rng.uniform(0.6, 1.5),
        })

    def make_event(user_idx, ts, ip, country, city, lat, lon, device_idx, success, reason, label, attack):
        return {"user_idx": user_idx, "device_idx": device_idx, "timestamp": ts, "ip_hash": ip,
                "country": country, "city": city, "latitude": round(lat, 4), "longitude": round(lon, 4),
                "success": success, "failure_reason": reason, "label": label, "attack_type": attack}

    def home_place(u):
        return (u["home_country"], u["home_city"],
                u["home_lat"] + rng.uniform(-0.03, 0.03), u["home_lon"] + rng.uniform(-0.03, 0.03))

    def pick_hour(profile):
        w = HOUR_WEIGHTS[profile]
        return rng.choices(list(w.keys()), weights=list(w.values()), k=1)[0]

    def at(day, hour, minute=None, second=None):
        return start + timedelta(days=day, hours=hour,
                                 minutes=rng.randint(0, 59) if minute is None else minute,
                                 seconds=rng.randint(0, 59) if second is None else second)

    # ---------------- comportement normal ----------------
    for u in users:
        st = state[u["idx"]]
        for day in range(days):
            weekend = (start + timedelta(days=day)).weekday() >= 5
            lam = (0.35 if weekend else 1.25) * st["activity"]
            for _ in range(int(np_rng.poisson(lam))):
                hour = pick_hour(u["work_profile"])
                r = rng.random()
                if r < 0.005:                       # connexion tardive légitime
                    hour = rng.choice([5, 6, 22, 23])
                ts = at(day, hour)
                country, city, lat, lon = home_place(u)
                ip = rng.choice(st["home_ips"]) if rng.random() < 0.90 else ip_hash()
                dev = st["devices"][0] if rng.random() < 0.7 else rng.choice(st["devices"])
                r2 = rng.random()
                if r2 < 0.015:                      # déplacement professionnel dans le pays
                    other = rng.choice([c for c in cities if c[0] != u["home_city"]])
                    country, city = "Cameroun", other[0]
                    lat, lon = other[1] + rng.uniform(-0.03, 0.03), other[2] + rng.uniform(-0.03, 0.03)
                    ip = ip_hash()
                elif r2 < 0.018:                    # nouvel appareil légitime à domicile
                    dev = add_device(u["idx"], rng.choice(USER_DEVICES))
                    st["devices"].append(dev)
                if rng.random() < 0.005:            # échecs sans connexion (mot de passe oublié)
                    for k in range(rng.randint(1, 3)):
                        events.append(make_event(u["idx"], ts + timedelta(seconds=k * rng.randint(10, 60)), ip,
                                                 country, city, lat, lon, dev, False,
                                                 "mot_de_passe_incorrect", "normal", "aucune"))
                    continue
                if rng.random() < 0.03:             # fautes de frappe puis succès
                    n_fail = rng.randint(1, 2)
                    for k in range(n_fail):
                        events.append(make_event(u["idx"], ts - timedelta(seconds=(n_fail - k) * rng.randint(10, 60)),
                                                 ip, country, city, lat, lon, dev, False,
                                                 "mot_de_passe_incorrect", "normal", "aucune"))
                events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, True, "", "normal", "aucune"))

    normal_success = {}
    for e in events:
        if e["success"]:
            normal_success.setdefault(e["user_idx"], []).append(e)

    def random_time_in_attack_window():
        return rng.randint(WARMUP_DAYS, days - 2)

    def attacker_device(user_idx):
        return add_device(user_idx, rng.choice(ATTACKER_DEVICES))

    def foreign_place():
        c = rng.choice(FOREIGN_CITIES)
        return c[1], c[0], c[2] + rng.uniform(-0.1, 0.1), c[3] + rng.uniform(-0.1, 0.1)

    # ---------------- force brute ----------------
    for _ in range(attacks["force_brute"]):
        u = rng.choice(users)
        ts = at(random_time_in_attack_window(), rng.choice([0, 1, 2, 3, 4, 5, 13, 14, 20, 22]))
        country, city, lat, lon = foreign_place() if rng.random() < 0.8 else (
            "Cameroun", *rng.choice(cities)[:3])
        ip, dev = ip_hash(), attacker_device(u["idx"])
        k = rng.randint(8, 40)
        for i in range(1, k + 1):
            ts += timedelta(seconds=rng.randint(1, 6))
            events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, False,
                                     "mot_de_passe_incorrect", "suspect" if i <= 5 else "haut_risque", "force_brute"))
        if rng.random() < 0.25:
            ts += timedelta(seconds=rng.randint(1, 6))
            events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, True, "",
                                     "haut_risque", "force_brute"))

    # ---------------- credential stuffing ----------------
    for _ in range(attacks["credential_stuffing"]):
        ts = at(random_time_in_attack_window(), rng.randint(0, 23))
        country, city, lat, lon = foreign_place()
        ip = ip_hash()
        victims = rng.sample(users, rng.randint(8, 15))
        for j, u in enumerate(victims, start=1):
            dev = attacker_device(u["idx"])
            for _k in range(rng.randint(1, 3)):
                ts += timedelta(seconds=rng.randint(5, 40))
                events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, False,
                                         "mot_de_passe_incorrect", "suspect" if j <= 5 else "haut_risque",
                                         "credential_stuffing"))
        if rng.random() < 0.3:
            u = victims[-1]
            ts += timedelta(seconds=rng.randint(5, 40))
            events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, True, "",
                                     "haut_risque", "credential_stuffing"))

    # ---------------- prise de contrôle de compte ----------------
    for _ in range(attacks["prise_de_controle"]):
        u = rng.choice(users)
        ts = at(random_time_in_attack_window(), rng.randint(0, 5))
        country, city, lat, lon = foreign_place()
        ip, dev = ip_hash(), attacker_device(u["idx"])
        for _k in range(rng.randint(3, 8)):
            ts += timedelta(seconds=rng.randint(5, 30))
            events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, False,
                                     "mot_de_passe_incorrect", "haut_risque", "prise_de_controle"))
        ts += timedelta(seconds=rng.randint(5, 30))
        events.append(make_event(u["idx"], ts, ip, country, city, lat, lon, dev, True, "",
                                 "haut_risque", "prise_de_controle"))

    # ---------------- voyage impossible ----------------
    far = [c for c in FOREIGN_CITIES if c[0] != "Lagos"]
    made = 0
    guard = 0
    while made < attacks["voyage_impossible"] and guard < attacks["voyage_impossible"] * 20:
        guard += 1
        u = rng.choice(users)
        base_list = [e for e in normal_success.get(u["idx"], [])
                     if (e["timestamp"] - start).days >= WARMUP_DAYS and e["country"] == "Cameroun"]
        if not base_list:
            continue
        base = rng.choice(base_list)
        c = rng.choice(far)
        dist = haversine_km(base["latitude"], base["longitude"], c[2], c[3])
        max_hours = min(4.0, dist / 950.0)
        if max_hours < 1.0:
            continue
        delta = timedelta(hours=rng.uniform(1.0, max_hours))
        events.append(make_event(u["idx"], base["timestamp"] + delta, ip_hash(), c[1], c[0],
                                 c[2] + rng.uniform(-0.1, 0.1), c[3] + rng.uniform(-0.1, 0.1),
                                 attacker_device(u["idx"]), True, "", "haut_risque", "voyage_impossible"))
        made += 1

    # ---------------- heure inhabituelle ----------------
    for _ in range(attacks["heure_inhabituelle"]):
        u = rng.choice(users)
        st = state[u["idx"]]
        country, city, lat, lon = home_place(u)
        events.append(make_event(u["idx"], at(random_time_in_attack_window(), rng.randint(1, 4)),
                                 rng.choice(st["home_ips"]), country, city, lat, lon, st["devices"][0],
                                 True, "", "suspect", "heure_inhabituelle"))

    # ---------------- nouvel appareil / nouveau pays ----------------
    for _ in range(attacks["nouvel_appareil"]):
        u = rng.choice(users)
        country, city, lat, lon = foreign_place()
        hour = pick_hour(u["work_profile"])
        events.append(make_event(u["idx"], at(random_time_in_attack_window(), hour), ip_hash(), country, city,
                                 lat, lon, attacker_device(u["idx"]), True, "", "suspect", "nouvel_appareil"))

    events.sort(key=lambda e: e["timestamp"])
    return {"users": users, "devices": devices, "events": events}


def write_csvs(data, folder):
    """Écrit users.csv, devices.csv et login_events.csv (identifiants de jeu = index + 1)."""
    import os
    import pandas as pd

    os.makedirs(folder, exist_ok=True)
    users = pd.DataFrame(data["users"])
    users.insert(0, "user_id", users["idx"] + 1)
    users.drop(columns=["idx"]).to_csv(os.path.join(folder, "users.csv"), index=False, encoding="utf-8")

    dev = pd.DataFrame(data["devices"])
    dev.insert(0, "device_id", dev["idx"] + 1)
    dev["user_id"] = dev["user_idx"] + 1
    dev[["device_id", "user_id", "fingerprint", "device_type", "os", "browser"]].to_csv(
        os.path.join(folder, "devices.csv"), index=False, encoding="utf-8")

    ev = pd.DataFrame(data["events"])
    ev.insert(0, "event_id", range(1, len(ev) + 1))
    ev["user_id"] = ev["user_idx"] + 1
    ev["device_id"] = ev["device_idx"] + 1
    cols = ["event_id", "user_id", "timestamp", "ip_hash", "country", "city", "latitude", "longitude",
            "device_id", "success", "failure_reason", "label", "attack_type"]
    ev[cols].to_csv(os.path.join(folder, "login_events.csv"), index=False, encoding="utf-8")
    return {"users": len(users), "devices": len(dev), "events": len(ev)}