"""
FICHIER : apps/detection/engine.py

RÔLE
    Cœur du moteur de détection. Il prend les features d'une tentative de connexion et
    produit : un score de risque entre 0 et 1, un niveau (normal / suspect / haut risque),
    la liste des règles déclenchées et les motifs en français.

COMMENT LE SCORE EST CALCULÉ
    1. Score ML     = 0,7 x score du modèle supervisé (Random Forest)
                    + 0,3 x score d'anomalie (Isolation Forest)
    2. Score final  = 0,6 x score ML + 0,4 x score des règles
                      (au minimum 0,75 si une règle critique est déclenchée)
    3. Niveau       : en dessous du seuil « suspect » = normal ; entre les deux seuils =
                      suspect ; au-dessus du seuil « haut risque » = haut risque.
                      Les seuils sont calibrés à l'entraînement (voir training.py).

UTILISÉ PAR : training.py (évaluation du modèle), commande score_events (évaluation en base)
"""
import joblib
import numpy as np

from .features import FEATURE_COLUMNS
from .rules import RULES_FLOOR, apply_rules

W_ML, W_RULES = 0.6, 0.4   # poids du score ML et du score des règles dans le score final
W_SUP, W_ISO = 0.7, 0.3    # poids du modèle supervisé et de l'Isolation Forest dans le score ML
DEFAULT_THRESHOLDS = {"suspect": 0.30, "haut_risque": 0.60}
LEVELS = ["normal", "suspect", "haut_risque"]


def level_from_score(score, thresholds):
    """Transforme un score (0 à 1) en niveau de risque grâce aux deux seuils."""
    if score >= thresholds["haut_risque"]:
        return "haut_risque"
    if score >= thresholds["suspect"]:
        return "suspect"
    return "normal"


def combine(ml_score, rules_score, critical):
    """Mélange le score ML et le score des règles en un score final entre 0 et 1."""
    score = W_ML * ml_score + W_RULES * rules_score
    if critical:
        score = max(score, RULES_FLOOR)  # une règle critique impose un score élevé
    return float(min(score, 1.0))


class Detector:
    """Détecteur chargé depuis un fichier .joblib créé par la commande train_model."""

    def __init__(self, artifact, version="inconnue"):
        self.rf = artifact["rf"]              # Random Forest (modèle supervisé)
        self.iso = artifact["iso"]            # Isolation Forest (détection d'anomalies)
        self.iso_lo = artifact["iso_lo"]      # bornes pour ramener le score d'anomalie entre 0 et 1
        self.iso_hi = artifact["iso_hi"]
        self.thresholds = artifact["thresholds"]  # seuils calibrés à l'entraînement
        self.classes = list(self.rf.classes_)
        self.version = version

    @classmethod
    def load(cls, path, version="inconnue"):
        """Charge un modèle sauvegardé sur le disque."""
        return cls(joblib.load(path), version)

    def ml_scores(self, feats):
        """Score ML (0 à 1) pour chaque ligne de features."""
        x = feats[FEATURE_COLUMNS]
        # Modèle supervisé : probabilité de « suspect » (comptée à moitié) + « haut risque » (comptée en entier).
        proba = self.rf.predict_proba(x)
        supervised = proba[:, self.classes.index("suspect")] * 0.5 + proba[:, self.classes.index("haut_risque")]
        # Isolation Forest : plus la tentative est atypique, plus le score est grand.
        raw = -self.iso.score_samples(x)
        anomaly = np.clip((raw - self.iso_lo) / (self.iso_hi - self.iso_lo), 0, 1)
        return W_SUP * supervised + W_ISO * anomaly

    def evaluate(self, feats):
        """Évalue chaque ligne de features (DataFrame indexé par event_id).
        Retourne une liste de dictionnaires : score, niveau, règles et motifs."""
        ml = self.ml_scores(feats)
        out = []
        for (event_id, row), ml_score in zip(feats.iterrows(), ml):
            rules_score, triggered, reasons, critical = apply_rules(row)
            score = combine(ml_score, rules_score, critical)
            # Si aucune règle ne s'applique mais que le modèle trouve la tentative atypique,
            # on le dit clairement pour que l'administrateur ait un motif à lire.
            if ml_score >= 0.4 and not triggered:
                reasons = [f"Le modèle de détection juge cette tentative atypique (score ML {ml_score:.2f})"]
            out.append({
                "event_id": int(event_id), "score": score, "level": level_from_score(score, self.thresholds),
                "ml_score": float(ml_score), "rules_score": float(rules_score),
                "triggered_rules": triggered, "reasons": reasons,
            })
        return out