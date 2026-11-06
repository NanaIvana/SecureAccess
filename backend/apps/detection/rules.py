"""Configurable expert rules used by both training and live scoring."""

RULES_FLOOR = 0.75

DEFAULT_RULES = {
    "ECHECS_REPETES": {"points": 70, "threshold": 5},
    "VOYAGE_IMPOSSIBLE": {"points": 80, "threshold": 900},
    "ATTAQUE_MASSE": {"points": 70, "threshold": 5},
    "NOUVEAU_PAYS": {"points": 30, "threshold": None},
    "NOUVEL_APPAREIL": {"points": 20, "threshold": None},
    "HEURE_INHABITUELLE": {"points": 20, "threshold": 2},
    "SUCCES_APRES_ECHECS": {"points": 30, "threshold": 3},
    "IP_MAUVAISE_REPUTATION": {"points": 100, "threshold": None},
    "PASSWORD_SPRAYING": {"points": 85, "threshold": 10},
    "FORCE_BRUTE_LENTE": {"points": 85, "threshold": 10},
    "ROBOT": {"points": 80, "threshold": 1},
}


def _rule(settings, key):
    configured = settings.get(key, {})
    defaults = DEFAULT_RULES[key]
    return {
        "enabled": configured.get("is_enabled", True),
        "points": configured.get("points", defaults["points"]),
        "threshold": configured.get("threshold", defaults["threshold"]),
    }


def apply_rules(f, rule_settings=None):
    """Return normalized rule score, triggered keys, explanations, and critical flag."""
    settings = rule_settings or {}
    score = 0.0
    triggered, reasons = [], []
    critical = False

    def add(key, reason, force_critical=False, points=None):
        nonlocal score, critical
        rule = _rule(settings, key)
        if not rule["enabled"]:
            return
        score += (rule["points"] if points is None else points) / 100
        triggered.append(key)
        reasons.append(reason)
        critical = critical or force_critical

    if f.get("is_blocked", False):
        add("IP_MAUVAISE_REPUTATION", "Source présente dans la liste de blocage", True)

    failed10 = int(f["failed_10min"])
    threshold = _rule(settings, "ECHECS_REPETES")["threshold"]
    if threshold is not None and failed10 >= threshold:
        rule_points = _rule(settings, "ECHECS_REPETES")["points"]
        points = min(100, rule_points + 20) if failed10 >= threshold * 2 else rule_points
        add("ECHECS_REPETES", f"{failed10} échecs de connexion en moins de 10 minutes sur ce compte",
            failed10 >= threshold * 2, points)

    threshold = _rule(settings, "VOYAGE_IMPOSSIBLE")["threshold"]
    if threshold is not None and f["speed_kmh"] > threshold:
        add("VOYAGE_IMPOSSIBLE",
            f"Déplacement impossible : {int(f['speed_kmh'])} km/h depuis la dernière connexion réussie", True)

    threshold = _rule(settings, "ATTAQUE_MASSE")["threshold"]
    users_ip = int(f["distinct_users_from_ip_1h"])
    if not f.get("is_trusted", False) and threshold is not None and users_ip >= threshold:
        add("ATTAQUE_MASSE", f"La même source a ciblé {users_ip} comptes différents en 1 heure")

    trusted = bool(f.get("is_trusted", False))
    if not trusted and f["is_new_country"]:
        add("NOUVEAU_PAYS", "Connexion depuis un pays jamais utilisé par cet utilisateur")
    if not trusted and f["is_new_device"]:
        add("NOUVEL_APPAREIL", "Appareil jamais vu pour cet utilisateur")

    threshold = _rule(settings, "HEURE_INHABITUELLE")["threshold"]
    if threshold is not None and f["is_night"] and f["hour_deviation"] >= threshold:
        add("HEURE_INHABITUELLE", f"Heure inhabituelle pour cet utilisateur ({int(f['hour_of_day'])}h UTC)")

    threshold = _rule(settings, "SUCCES_APRES_ECHECS")["threshold"]
    if threshold is not None and f["success"] and failed10 >= threshold:
        add("SUCCES_APRES_ECHECS", f"Connexion réussie après {failed10} échecs récents")

    # R8 : password spraying, au moins 10 comptes distincts depuis la même source en 24 h.
    if not trusted and int(f.get("distinct_users_from_ip_24h", 0)) >= int(_rule(settings, "PASSWORD_SPRAYING")["threshold"] or 10):
        add("PASSWORD_SPRAYING", "La même source a tenté de joindre au moins 10 comptes en 24 heures")

    # R9 : force brute lente, au moins 10 échecs sur 24 h depuis 3 sources distinctes.
    if int(f.get("failed_24h", 0)) >= int(_rule(settings, "FORCE_BRUTE_LENTE")["threshold"] or 10) and int(f.get("distinct_sources_user_24h", 0)) >= 3:
        add("FORCE_BRUTE_LENTE", "Au moins 10 échecs en 24 heures depuis plusieurs sources")

    # R10 : User-Agent automatisé ou cadence de robot.
    if bool(f.get("automated_user_agent", 0)) or bool(f.get("regular_rapid_cadence", 0)):
        add("ROBOT", "Client automatisé ou cadence de tentatives quasi instantanée")

    if trusted and not f.get("is_blocked", False):
        score *= 0.35
    return max(0.0, min(score, 1.0)), triggered, reasons, critical
