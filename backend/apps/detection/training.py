
"""
FICHIER : apps/detection/training.py

ROLE
    Entraîne et évalue le détecteur de comportements suspects.

ETAPES
    1. Découpage chronologique : entraînement, validation et test.
    2. Entraînement d'un Isolation Forest sur les connexions normales.
    3. Entraînement d'un Random Forest sur les événements étiquetés.
    4. Calibrage des seuils uniquement sur la validation.
    5. Évaluation finale sur le jeu de test.

IMPORTANT
    Le jeu de test n'intervient jamais dans le choix des seuils.
"""

import json

import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from .engine import LEVELS, W_ISO, W_SUP, combine, level_from_score
from .features import FEATURE_COLUMNS
from .rules import apply_rules


# Couples de seuils candidats : (suspect, haut risque).
CANDIDATE_THRESHOLDS = [
    (0.35, 0.65),
    (0.30, 0.60),
    (0.25, 0.55),
]


def _validate_inputs(feats, labels, timestamps, train_days, val_days):
    """
    Vérifie les données avant de lancer l'entraînement.
    """

    if not isinstance(feats, pd.DataFrame):
        raise TypeError("feats doit être un DataFrame pandas.")

    if feats.empty:
        raise ValueError("Aucune donnée disponible pour l'entraînement.")

    if not feats.index.is_unique:
        raise ValueError("Les index des événements doivent être uniques.")

    if not feats.columns.is_unique:
        raise ValueError("Les colonnes des variables doivent être uniques.")

    missing = [col for col in FEATURE_COLUMNS if col not in feats.columns]

    if missing:
        raise ValueError(
            f"Variables manquantes dans les données : {missing}"
        )

    if isinstance(labels, pd.Series):
        if not labels.index.equals(feats.index):
            raise ValueError(
                "Les index de labels et de feats ne correspondent pas."
            )
        y = labels.to_numpy()
    else:
        y = np.asarray(labels)

    if isinstance(timestamps, pd.Series):
        if not timestamps.index.equals(feats.index):
            raise ValueError(
                "Les index de timestamps et de feats ne correspondent pas."
            )
        dates = timestamps.to_numpy()
    else:
        dates = np.asarray(timestamps)

    if len(y) != len(feats) or len(dates) != len(feats):
        raise ValueError(
            "Les nombres de features, labels et timestamps doivent être égaux."
        )

    if pd.isna(y).any():
        raise ValueError("Certaines étiquettes sont manquantes.")

    unknown_labels = set(y) - set(LEVELS)

    if unknown_labels:
        raise ValueError(
            f"Étiquettes inconnues : {unknown_labels}. "
            f"Valeurs autorisées : {LEVELS}"
        )

    if train_days <= 0 or val_days <= 0:
        raise ValueError(
            "train_days et val_days doivent être strictement positifs."
        )

    dates = pd.to_datetime(dates, errors="coerce")

    if pd.isna(dates).any():
        raise ValueError("Certaines dates sont invalides ou manquantes.")

    # Vérification et conversion des variables numériques.
    x = feats[FEATURE_COLUMNS].apply(
        pd.to_numeric,
        errors="coerce"
    )

    values = x.to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise ValueError(
            "Les variables contiennent des valeurs manquantes "
            "ou non finies. Vérifier features.py et dataio.py."
        )

    return x, y, dates


def _rules_arrays(x):
    """
    Calcule le score des règles et l'indicateur de criticité
    pour chaque événement.
    """

    scores = []
    critical = []

    for _, row in x.iterrows():
        score, _, _, is_critical = apply_rules(row)

        scores.append(score)
        critical.append(is_critical)

    return (
        np.asarray(scores, dtype=float),
        np.asarray(critical, dtype=bool)
    )


def _metrics(y_true, y_pred):
    """
    Calcule les métriques de classification.

    Une alerte correspond à un événement suspect ou haut risque.
    """

    if len(y_true) == 0:
        raise ValueError(
            "Impossible de calculer les métriques sur un ensemble vide."
        )

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=LEVELS,
        zero_division=0
    )

    true_alert = y_true != "normal"
    predicted_alert = y_pred != "normal"

    hits = (true_alert & predicted_alert).sum()

    alert_precision = hits / max(predicted_alert.sum(), 1)
    alert_recall = hits / max(true_alert.sum(), 1)

    return {
        "par_classe": {
            level: {
                "precision": float(precision[i]),
                "rappel": float(recall[i]),
                "f1": float(f1[i])
            }
            for i, level in enumerate(LEVELS)
        },

        "alertes": {
            "precision": float(alert_precision),
            "rappel": float(alert_recall)
        },

        "matrice_confusion": confusion_matrix(
            y_true,
            y_pred,
            labels=LEVELS
        ).tolist()
    }


def train_detector(
    feats,
    labels,
    timestamps,
    train_days=120,
    val_days=30,
    seed=42
):
    """
    Entraîne le détecteur et retourne :

        artifact : modèles et paramètres à sauvegarder.
        metrics  : résultats de l'évaluation.

    Les données doivent être alignées dans le même ordre.
    """

    # ---------------------------------------------------------
    # 1. Validation des données
    # ---------------------------------------------------------

    x, y, dates = _validate_inputs(
        feats,
        labels,
        timestamps,
        train_days,
        val_days
    )

    # ---------------------------------------------------------
    # 2. Découpage chronologique
    # ---------------------------------------------------------

    start = dates.min().normalize()

    train_end = start + pd.Timedelta(days=train_days)
    val_end = train_end + pd.Timedelta(days=val_days)

    train_mask = np.asarray(dates < train_end)
    val_mask = np.asarray(
        (dates >= train_end) & (dates < val_end)
    )
    test_mask = np.asarray(dates >= val_end)

    x_tr = x.iloc[np.flatnonzero(train_mask)]
    y_tr = y[train_mask]

    x_val = x.iloc[np.flatnonzero(val_mask)]
    y_val = y[val_mask]

    x_test = x.iloc[np.flatnonzero(test_mask)]
    y_test = y[test_mask]

    if len(x_tr) == 0:
        raise ValueError("L'ensemble d'entraînement est vide.")

    if len(x_val) == 0:
        raise ValueError(
            "L'ensemble de validation est vide. "
            "Il faut davantage de données sur la période choisie."
        )

    if len(x_test) == 0:
        raise ValueError(
            "L'ensemble de test est vide. "
            "Il faut davantage de données sur la période choisie."
        )

    # ---------------------------------------------------------
    # 3. Préparation des connexions normales
    # ---------------------------------------------------------

    normal_mask = y_tr == "normal"
    normal_tr = x_tr.iloc[np.flatnonzero(normal_mask)]

    if len(normal_tr) < 2:
        raise ValueError(
            "Isolation Forest nécessite au moins deux événements normaux."
        )

    # ---------------------------------------------------------
    # 4. Entraînement de l'Isolation Forest
    # ---------------------------------------------------------

    iso = IsolationForest(
        n_estimators=200,
        random_state=seed,
        n_jobs=-1
    )

    iso.fit(normal_tr)

    raw_normal = -iso.score_samples(normal_tr)

    # Médiane et percentile 99,5 pour normaliser les anomalies.
    iso_lo = float(np.percentile(raw_normal, 50))
    iso_hi = float(np.percentile(raw_normal, 99.5))

    # ---------------------------------------------------------
    # 5. Entraînement du Random Forest
    # ---------------------------------------------------------

    rf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=seed
    )

    rf.fit(x_tr, y_tr)

    classes = list(rf.classes_)

    # Les classes absentes sont traitées comme une contribution nulle.
    suspect_index = (
        classes.index("suspect")
        if "suspect" in classes else None
    )

    high_risk_index = (
        classes.index("haut_risque")
        if "haut_risque" in classes else None
    )

    # ---------------------------------------------------------
    # 6. Calcul du score ML
    # ---------------------------------------------------------

    def ml_score(data):
        """
        Combine :
            - Random Forest : classification supervisée.
            - Isolation Forest : détection d'anomalies.
        """

        if len(data) == 0:
            return np.empty(0, dtype=float)

        probabilities = rf.predict_proba(data)

        supervised = np.zeros(len(data), dtype=float)

        if suspect_index is not None:
            supervised += (
                probabilities[:, suspect_index] * 0.5
            )

        if high_risk_index is not None:
            supervised += probabilities[:, high_risk_index]

        raw_anomaly = -iso.score_samples(data)

        if iso_hi <= iso_lo:
            anomaly = np.zeros(len(data), dtype=float)
        else:
            anomaly = np.clip(
                (raw_anomaly - iso_lo) / (iso_hi - iso_lo),
                0,
                1
            )

        score = W_SUP * supervised + W_ISO * anomaly

        return np.clip(score, 0, 1)

    # ---------------------------------------------------------
    # 7. Conversion des scores en niveaux
    # ---------------------------------------------------------

    def levels(scores, thresholds):
        return np.asarray([
            level_from_score(
                score,
                {
                    "suspect": thresholds[0],
                    "haut_risque": thresholds[1]
                }
            )
            for score in scores
        ])

    # ---------------------------------------------------------
    # 8. Calcul des scores sur validation et test
    # ---------------------------------------------------------

    parts = {}

    for name, data, real_labels in (
        ("val", x_val, y_val),
        ("test", x_test, y_test)
    ):

        ml = ml_score(data)

        rule_scores, critical = _rules_arrays(data)

        final_scores = np.asarray([
            combine(m, r, c)
            for m, r, c in zip(ml, rule_scores, critical)
        ])

        parts[name] = {
            "y": real_labels,
            "ml": ml,
            "rs": rule_scores,
            "final": final_scores
        }

    # ---------------------------------------------------------
    # 9. Calibrage des seuils sur la validation uniquement
    # ---------------------------------------------------------

    best_thresholds = CANDIDATE_THRESHOLDS[0]
    best_value = -1.0

    for thresholds_candidate in CANDIDATE_THRESHOLDS:

        predictions = levels(
            parts["val"]["final"],
            thresholds_candidate
        )

        result = _metrics(
            parts["val"]["y"],
            predictions
        )

        class_metrics = result["par_classe"]

        value = (
            class_metrics["suspect"]["f1"]
            + class_metrics["haut_risque"]["f1"]
        ) / 2

        if value > best_value:
            best_value = value
            best_thresholds = thresholds_candidate

    thresholds = {
        "suspect": float(best_thresholds[0]),
        "haut_risque": float(best_thresholds[1])
    }

    # ---------------------------------------------------------
    # 10. Construction des métriques
    # ---------------------------------------------------------

    metrics = {
        "decoupage": {
            "train": int(len(x_tr)),
            "validation": int(len(x_val)),
            "test": int(len(x_test)),
            "debut": str(start.date()),
            "fin_train_jours": int(train_days),
            "fin_validation_jours": int(train_days + val_days)
        },

        "repartition_train": {
            level: int(np.sum(y_tr == level))
            for level in LEVELS
        },

        "seuils": thresholds,

        "poids": {
            "ml": float(W_SUP + W_ISO),
            "supervise": float(W_SUP),
            "anomalie": float(W_ISO),
            "regles": 0.4
        },

        "importance_variables": dict(
            sorted(
                zip(
                    FEATURE_COLUMNS,
                    map(float, rf.feature_importances_)
                ),
                key=lambda item: -item[1]
            )
        ),

        "avertissement": (
            "Jeu de données synthétique : les performances "
            "ne préjugent pas des résultats sur des données réelles."
        )
    }

    # Évaluation des deux ensembles.
    for name in ("val", "test"):

        data = parts[name]

        metrics[name] = {
            "regles_seules": _metrics(
                data["y"],
                levels(data["rs"], best_thresholds)
            ),

            "modele_seul": _metrics(
                data["y"],
                levels(data["ml"], best_thresholds)
            ),

            "hybride": _metrics(
                data["y"],
                levels(data["final"], best_thresholds)
            )
        }

    # ---------------------------------------------------------
    # 11. Construction de l'artefact du modèle
    # ---------------------------------------------------------

    artifact = {
        "rf": rf,
        "iso": iso,
        "iso_lo": iso_lo,
        "iso_hi": iso_hi,
        "thresholds": thresholds,
        "features": FEATURE_COLUMNS
    }

    # Conversion en types Python compatibles avec JSON.
    metrics = json.loads(
        json.dumps(
            metrics,
            default=lambda value: (
                value.item()
                if hasattr(value, "item")
                else str(value)
            )
        )
    )

    return artifact, metrics

