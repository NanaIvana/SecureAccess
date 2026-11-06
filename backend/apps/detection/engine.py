
"""
FICHIER : apps/detection/engine.py

RÔLE
    Cœur du moteur de détection.
    Combine le Machine Learning et les règles de sécurité pour
    produire un score de risque compris entre 0 et 1.

CALCUL
    1. Score ML :
       0.7 x Random Forest + 0.3 x Isolation Forest

    2. Score final :
       0.6 x Score ML + 0.4 x Score des règles

    3. Si une règle critique est déclenchée :
       le score final est au minimum RULES_FLOOR.

    4. Classification :
       normal / suspect / haut_risque

UTILISÉ PAR : training.py, service.py
"""

import math

import joblib
import numpy as np

from .features import FEATURE_COLUMNS
from .rules import RULES_FLOOR, apply_rules


# Poids des différents mécanismes.
W_ML = 0.6
W_RULES = 0.4

W_SUP = 0.7
W_ISO = 0.3

# Seuils utilisés si aucun seuil n'est fourni.
DEFAULT_THRESHOLDS = {
    "suspect": 0.30,
    "haut_risque": 0.60,
}

LEVELS = ["normal", "suspect", "haut_risque"]


def level_from_score(score, thresholds):
    """
    Transforme un score en niveau de risque.

    Score < seuil suspect : normal
    Score >= seuil suspect : suspect
    Score >= seuil haut risque : haut_risque
    """

    if not math.isfinite(float(score)):
        raise ValueError("Le score de risque doit être fini.")

    suspect = float(thresholds["suspect"])
    high = float(thresholds["haut_risque"])

    if not (0 <= suspect < high <= 1):
        raise ValueError("Les seuils de risque sont invalides.")

    score = float(np.clip(score, 0, 1))

    if score >= high:
        return "haut_risque"

    if score >= suspect:
        return "suspect"

    return "normal"


def combine(ml_score, rules_score, critical):
    """
    Combine le score ML et le score des règles.

    Une règle critique impose un score minimal de RULES_FLOOR.
    """

    ml_score = float(ml_score)
    rules_score = float(rules_score)

    if not math.isfinite(ml_score) or not math.isfinite(rules_score):
        raise ValueError("Les scores doivent être des nombres finis.")

    if not (0 <= ml_score <= 1 and 0 <= rules_score <= 1):
        raise ValueError("Les scores doivent être compris entre 0 et 1.")

    score = W_ML * ml_score + W_RULES * rules_score

    if critical:
        score = max(score, RULES_FLOOR)

    return float(np.clip(score, 0, 1))


class Detector:
    """
    Détecteur chargé depuis un fichier .joblib créé par train_model.
    """

    def __init__(self, artifact, version="inconnue"):

        # Vérifier la présence des composants du modèle.
        required = {"rf", "iso", "iso_lo", "iso_hi"}

        missing = required - set(artifact.keys())

        if missing:
            raise ValueError(
                f"Composants manquants dans le modèle : {sorted(missing)}"
            )

        self.rf = artifact["rf"]
        self.iso = artifact["iso"]

        self.iso_lo = float(artifact["iso_lo"])
        self.iso_hi = float(artifact["iso_hi"])

        if not (
            math.isfinite(self.iso_lo)
            and math.isfinite(self.iso_hi)
        ):
            raise ValueError("Les bornes de l'Isolation Forest sont invalides.")

        self.thresholds = artifact.get(
            "thresholds",
            DEFAULT_THRESHOLDS.copy(),
        )

        # Vérifier les seuils dès le chargement.
        self.thresholds = {
            "suspect": float(self.thresholds["suspect"]),
            "haut_risque": float(self.thresholds["haut_risque"]),
        }

        level_from_score(0.0, self.thresholds)

        # Récupérer les classes réellement apprises.
        self.classes = list(self.rf.classes_)

        if not self.classes:
            raise ValueError("Le modèle Random Forest ne possède aucune classe.")

        self.version = version

    @classmethod
    def load(cls, path, version="inconnue"):
        """
        Charge un modèle sauvegardé.

        Attention : ne charger que des fichiers joblib provenant
        d'une source fiable, car joblib peut exécuter du code
        lors de la désérialisation.
        """
        return cls(joblib.load(path), version)

    def ml_scores(self, feats):
        """
        Calcule le score ML de chaque événement.

        Le score combine :
            - Random Forest : classification supervisée.
            - Isolation Forest : détection d'anomalies.

        Retourne un tableau de scores compris entre 0 et 1.
        """

        if feats.empty:
            return np.array([], dtype=float)

        # Vérifier les colonnes attendues.
        missing = set(FEATURE_COLUMNS) - set(feats.columns)

        if missing:
            raise ValueError(
                f"Features manquantes : {sorted(missing)}"
            )

        # Respecter exactement l'ordre des caractéristiques.
        x = feats.loc[:, FEATURE_COLUMNS].copy()

        # Vérifier les valeurs numériques.
        try:
            x = x.apply(pd.to_numeric, errors="raise")
        except (TypeError, ValueError):
            raise ValueError(
                "Les features doivent contenir uniquement des valeurs numériques."
            )

        values = x.to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise ValueError(
                "Les features contiennent des valeurs NaN ou infinies."
            )

        # -----------------------------------------------------
        # 1. RANDOM FOREST
        # -----------------------------------------------------

        probabilities = self.rf.predict_proba(x)

        # Certaines classes peuvent être absentes de l'entraînement.
        class_indices = {
            label: index
            for index, label in enumerate(self.classes)
        }

        supervised = np.zeros(len(x), dtype=float)

        if "suspect" in class_indices:
            supervised += (
                0.5 * probabilities[:, class_indices["suspect"]]
            )

        if "haut_risque" in class_indices:
            supervised += probabilities[:, class_indices["haut_risque"]]

        # -----------------------------------------------------
        # 2. ISOLATION FOREST
        # -----------------------------------------------------

        raw = -self.iso.score_samples(x)

        # Éviter la division par zéro lorsque les bornes
        # d'anomalie sont identiques.
        if self.iso_hi <= self.iso_lo:
            anomaly = np.zeros(len(x), dtype=float)
        else:
            anomaly = (
                (raw - self.iso_lo)
                / (self.iso_hi - self.iso_lo)
            )

            anomaly = np.clip(anomaly, 0, 1)

        # -----------------------------------------------------
        # 3. COMBINAISON DES SCORES ML
        # -----------------------------------------------------

        ml = W_SUP * supervised + W_ISO * anomaly

        return np.clip(ml, 0, 1).astype(float)

    def evaluate(self, feats):
        """
        Évalue chaque événement.

        Retourne une liste de dictionnaires contenant :
            event_id
            score
            level
            ml_score
            rules_score
            triggered_rules
            reasons
        """

        if feats.empty:
            return []

        ml = self.ml_scores(feats)

        out = []

        for (event_id, row), ml_score in zip(
            feats.iterrows(),
            ml,
        ):

            # Appliquer les règles de sécurité.
            rules_score, triggered, reasons, critical = apply_rules(row)

            # Combiner ML et règles.
            score = combine(
                ml_score,
                rules_score,
                critical,
            )

            # Déterminer le niveau de risque.
            level = level_from_score(
                score,
                self.thresholds,
            )

            # Si le modèle détecte une anomalie sans règle
            # déclenchée, expliquer pourquoi l'événement est suspect.
            if ml_score >= 0.4 and not triggered:

                reasons = [
                    "Le modèle de détection juge cette tentative "
                    f"atypique (score ML {ml_score:.2f})."
                ]

            out.append({
                "event_id": int(event_id),
                "score": score,
                "level": level,
                "ml_score": float(ml_score),
                "rules_score": float(rules_score),
                "triggered_rules": triggered,
                "reasons": reasons,
            })

        return out

