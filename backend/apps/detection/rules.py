
"""
FICHIER : apps/detection/rules.py

RÔLE
    Applique les règles de sécurité sur les caractéristiques
    calculées pour chaque tentative de connexion.

OBJECTIFS
    - Détecter les comportements connus.
    - Produire des explications compréhensibles.
    - Éviter les erreurs liées aux valeurs manquantes ou invalides.
    - Conserver les règles, seuils et poids existants.

UTILISÉ PAR : engine.py, training.py
"""

import math


# Score minimal imposé lorsqu'une règle critique est déclenchée.
RULES_FLOOR = 0.75


def _get_number(features, name, default=0.0):
    """
    Récupère une caractéristique numérique de manière sécurisée.

    Une valeur absente, invalide ou infinie est remplacée
    par une valeur neutre.
    """
    try:
        value = float(features.get(name, default))

        if not math.isfinite(value):
            return default

        return value

    except (TypeError, ValueError, OverflowError):
        return default


def _get_flag(features, name):
    """
    Récupère une caractéristique binaire.

    Seules les valeurs numériques 0 et 1 sont acceptées.
    """
    value = _get_number(features, name)

    return value == 1.0


def apply_rules(f):
    """
    Applique les sept règles de sécurité.

    Paramètre :
        f : dictionnaire ou Series pandas contenant les features.

    Retour :
        (
            score des règles,
            liste des règles déclenchées,
            explications en français,
            indicateur critique
        )
    """

    score = 0.0
    triggered = []
    reasons = []
    critical = False

    # ---------------------------------------------------------
    # R1 - FORCE BRUTE
    # ---------------------------------------------------------
    # Au moins 5 échecs en 10 minutes.
    # À partir de 10 échecs : règle critique.

    failed10 = max(
        0,
        int(_get_number(f, "failed_10min"))
    )

    if failed10 >= 5:

        weight = 0.9 if failed10 >= 10 else 0.7

        score += weight

        triggered.append("R1_force_brute")

        reasons.append(
            f"{failed10} échecs de connexion en moins "
            "de 10 minutes sur ce compte"
        )

        if failed10 >= 10:
            critical = True

    # ---------------------------------------------------------
    # R2 - VOYAGE IMPOSSIBLE
    # ---------------------------------------------------------
    # Une vitesse supérieure à 900 km/h peut indiquer
    # une utilisation frauduleuse du compte.
    #
    # La vitesse doit être calculée à partir de deux
    # positions GPS valides.

    speed = max(
        0.0,
        _get_number(f, "speed_kmh")
    )

    if speed > 900:

        score += 0.8

        triggered.append("R2_voyage_impossible")

        reasons.append(
            f"Déplacement inhabituel : environ "
            f"{int(speed)} km/h depuis la dernière connexion réussie"
        )

        critical = True

    # ---------------------------------------------------------
    # R3 - SOURCE MULTI-COMPTES
    # ---------------------------------------------------------
    # Une même IP cible au moins 5 comptes différents
    # dans une fenêtre d'une heure.

    users_ip = max(
        0,
        int(_get_number(f, "distinct_users_from_ip_1h"))
    )

    if users_ip >= 5:

        score += 0.7

        triggered.append("R3_source_multi_comptes")

        reasons.append(
            f"La même source a ciblé {users_ip} comptes "
            "différents en 1 heure"
        )

    # ---------------------------------------------------------
    # R4 - NOUVEAU PAYS
    # ---------------------------------------------------------

    if _get_flag(f, "is_new_country"):

        score += 0.3

        triggered.append("R4_nouveau_pays")

        reasons.append(
            "Connexion depuis un pays jamais utilisé "
            "lors d'une connexion de confiance"
        )

    # ---------------------------------------------------------
    # R5 - NOUVEL APPAREIL
    # ---------------------------------------------------------

    if _get_flag(f, "is_new_device"):

        score += 0.2

        triggered.append("R5_nouvel_appareil")

        reasons.append(
            "Appareil jamais identifié lors d'une "
            "connexion de confiance pour cet utilisateur"
        )

    # ---------------------------------------------------------
    # R6 - HEURE INHABITUELLE
    # ---------------------------------------------------------

    is_night = _get_flag(f, "is_night")

    hour_deviation = max(
        0.0,
        _get_number(f, "hour_deviation")
    )

    hour = max(
        0,
        min(23, int(_get_number(f, "hour_of_day")))
    )

    if is_night and hour_deviation >= 2:

        score += 0.2

        triggered.append("R6_heure_inhabituelle")

        reasons.append(
            f"Connexion à {hour}h UTC, à une heure "
            "inhabituelle pour cet utilisateur"
        )

    # ---------------------------------------------------------
    # R7 - SUCCÈS APRÈS PLUSIEURS ÉCHECS
    # ---------------------------------------------------------
    # Une connexion réussie après au moins 3 échecs
    # récents peut indiquer qu'un mot de passe a été deviné.

    success = _get_flag(f, "success")

    if success and failed10 >= 3:

        score += 0.3

        triggered.append("R7_succes_apres_echecs")

        reasons.append(
            f"Connexion réussie après {failed10} "
            "échecs récents"
        )

    # ---------------------------------------------------------
    # SCORE FINAL DES RÈGLES
    # ---------------------------------------------------------

    score = min(max(score, 0.0), 1.0)

    return score, triggered, reasons, critical


