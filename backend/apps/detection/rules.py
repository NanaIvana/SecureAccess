"""
FICHIER : apps/detection/rules.py

RÔLE
    Contient les règles de sécurité écrites par les spécialistes SSI (force brute,
    voyage impossible, source qui vise plusieurs comptes, etc.).
    Chaque règle déclenchée :
      - ajoute un poids au « score des règles » (plafonné à 1) ;
      - produit une phrase en français expliquant POURQUOI la tentative est suspecte
        (affichée dans le détail d'une alerte).

POURQUOI DES RÈGLES EN PLUS DU MACHINE LEARNING ?
    Les règles attrapent les attaques connues et sont faciles à expliquer ; le modèle
    attrape les combinaisons de signaux faibles. Le score final mélange les deux
    (voir engine.py).

UTILISÉ PAR : engine.py, training.py
"""

# Si une règle critique est déclenchée, le score final ne peut pas descendre sous cette valeur.
RULES_FLOOR = 0.75


def apply_rules(f):
    """Applique toutes les règles à une ligne de features (dict ou Series pandas).
    Retourne (score des règles, noms des règles déclenchées, motifs en français, critique ?)."""
    score, triggered, reasons, critical = 0.0, [], [], False

    # R1 - Force brute : beaucoup d'échecs en peu de temps sur le même compte.
    failed10 = int(f["failed_10min"])
    if failed10 >= 5:
        w = 0.9 if failed10 >= 10 else 0.7  # 10 échecs ou plus = cas critique
        score += w
        triggered.append("R1_force_brute")
        reasons.append(f"{failed10} échecs de connexion en moins de 10 minutes sur ce compte")
        critical = critical or failed10 >= 10

    # R2 - Voyage impossible : vitesse supérieure à 900 km/h depuis la dernière connexion réussie.
    if f["speed_kmh"] > 900:
        score += 0.8
        triggered.append("R2_voyage_impossible")
        reasons.append(f"Déplacement impossible : {int(f['speed_kmh'])} km/h depuis la dernière connexion réussie")
        critical = True

    # R3 - Source multi-comptes : la même adresse vise au moins 5 comptes en 1 heure.
    users_ip = int(f["distinct_users_from_ip_1h"])
    if users_ip >= 5:
        score += 0.7
        triggered.append("R3_source_multi_comptes")
        reasons.append(f"La même source a ciblé {users_ip} comptes différents en 1 heure")

    # R4 - Nouveau pays : jamais utilisé par cet utilisateur.
    if f["is_new_country"]:
        score += 0.3
        triggered.append("R4_nouveau_pays")
        reasons.append("Connexion depuis un pays jamais utilisé par cet utilisateur")

    # R5 - Nouvel appareil : jamais vu pour cet utilisateur.
    if f["is_new_device"]:
        score += 0.2
        triggered.append("R5_nouvel_appareil")
        reasons.append("Appareil jamais vu pour cet utilisateur")

    # R6 - Heure inhabituelle : de nuit ET à au moins 2 h de ses heures habituelles.
    if f["is_night"] and f["hour_deviation"] >= 2:
        score += 0.2
        triggered.append("R6_heure_inhabituelle")
        reasons.append(f"Heure inhabituelle pour cet utilisateur ({int(f['hour_of_day'])}h UTC)")

    # R7 - Succès après plusieurs échecs : le mot de passe a peut-être été deviné.
    if f["success"] and failed10 >= 3:
        score += 0.3
        triggered.append("R7_succes_apres_echecs")
        reasons.append(f"Connexion réussie après {failed10} échecs récents")

    return min(score, 1.0), triggered, reasons, critical