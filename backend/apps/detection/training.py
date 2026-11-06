"""
FICHIER : apps/detection/training.py

RÔLE
    Entraîne et évalue le détecteur. Il :
      1. découpe les données DANS LE TEMPS : 120 premiers jours = entraînement, 30 jours
         suivants = validation, le reste = test (jamais vu pendant l'entraînement) ;
      2. entraîne deux modèles : un Isolation Forest (anomalies, appris sur les connexions
         normales seulement) et un Random Forest (classification, appris avec les étiquettes) ;
      3. choisit les seuils « suspect » / « haut risque » sur la VALIDATION ;
      4. mesure la qualité sur le TEST : règles seules, modèle seul, et hybride (les deux).

POURQUOI UN DÉCOUPAGE PAR DATE ?
    Dans la réalité, on prédit l'avenir à partir du passé. Mélanger les dates au hasard
    donnerait des résultats trop optimistes.

ATTENTION
    Le jeu de données est synthétique : les scores obtenus ne préjugent pas des
    performances sur de vraies données.

UTILISÉ PAR : commande train_model
"""
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

from .engine import LEVELS, W_ISO, W_SUP, combine, level_from_score
from .features import FEATURE_COLUMNS
from .rules import apply_rules

# Couples de seuils (suspect, haut risque) testés ; on garde le meilleur sur la validation.
CANDIDATE_THRESHOLDS = [(0.35, 0.65), (0.30, 0.60), (0.25, 0.55)]


def _rules_arrays(x):
    """Score des règles et indicateur « règle critique » pour chaque ligne de features."""
    scores, critical = [], []
    for _, row in x.iterrows():
        s, _, _, c = apply_rules(row)
        scores.append(s)
        critical.append(c)
    return np.array(scores), np.array(critical)


def _metrics(y_true, y_pred):
    """Précision, rappel et F1 par niveau ; précision et rappel des alertes ; matrice de confusion.
    « Alerte » = tout ce qui n'est pas « normal » (suspect ou haut risque)."""
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, labels=LEVELS, zero_division=0)
    true_alert, pred_alert = y_true != "normal", y_pred != "normal"
    hits = (true_alert & pred_alert).sum()  # vraies alertes correctement détectées
    return {
        "par_classe": {lvl: {"precision": float(p[i]), "rappel": float(r[i]), "f1": float(f[i])}
                       for i, lvl in enumerate(LEVELS)},
        "alertes": {"precision": float(hits / max(pred_alert.sum(), 1)), "rappel": float(hits / max(true_alert.sum(), 1))},
        "matrice_confusion": confusion_matrix(y_true, y_pred, labels=LEVELS).tolist(),
    }


def train_detector(
    feats, labels, timestamps, train_days=120, val_days=30, seed=42,
    n_estimators=300, max_depth=None, attack_types=None,
):
    """feats : features ; labels : étiquettes réelles ; timestamps : dates (alignés sur feats.index).
    Retourne (artefact à sauvegarder, dictionnaire de métriques)."""
    # --- 1. Découpage dans le temps ---
    start = timestamps.min().normalize()
    train = timestamps < start + pd.Timedelta(days=train_days)
    val = (timestamps >= start + pd.Timedelta(days=train_days)) & (timestamps < start + pd.Timedelta(days=train_days + val_days))
    test = timestamps >= start + pd.Timedelta(days=train_days + val_days)

    # Les signaux auxiliaires restent disponibles aux règles, mais le modèle ML conserve exactement FEATURE_COLUMNS.
    all_x_tr, y_tr = feats[train], labels[train]
    x_tr = all_x_tr[FEATURE_COLUMNS]
    normal_tr = x_tr[y_tr == "normal"]
    if normal_tr.empty or set(y_tr.unique()) != set(LEVELS):
        raise ValueError("L'apprentissage doit contenir des exemples normaux, suspects et à haut risque.")
    if not val.any() or not test.any():
        raise ValueError("Le jeu de données doit couvrir les périodes d'apprentissage, de validation et de test.")

    # --- 2a. Isolation Forest : apprend le comportement « normal » ---
    iso = IsolationForest(n_estimators=200, random_state=seed, n_jobs=-1).fit(normal_tr)
    raw_tr = -iso.score_samples(normal_tr)
    # Bornes servant à ramener le score d'anomalie entre 0 et 1 (médiane -> 0, percentile 99,5 -> 1).
    iso_lo, iso_hi = float(np.percentile(raw_tr, 50)), float(np.percentile(raw_tr, 99.5))

    # --- 2b. Random Forest : apprend à reconnaître normal / suspect / haut risque ---
    # class_weight : compense le fait que les attaques sont rares par rapport aux connexions normales.
    rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth,
                                class_weight="balanced_subsample", min_samples_leaf=2,
                                n_jobs=-1, random_state=seed).fit(x_tr, y_tr)
    classes = list(rf.classes_)

    def ml_score(x):
        """Score ML : même formule que dans engine.py (Detector.ml_scores)."""
        proba = rf.predict_proba(x)
        sup = proba[:, classes.index("suspect")] * 0.5 + proba[:, classes.index("haut_risque")]
        raw = -iso.score_samples(x)
        anomaly = (
            np.clip((raw - iso_lo) / (iso_hi - iso_lo), 0, 1)
            if iso_hi > iso_lo else np.zeros(len(raw))
        )
        return W_SUP * sup + W_ISO * anomaly

    def levels(scores, th):
        """Convertit des scores en niveaux avec un couple de seuils (suspect, haut risque)."""
        return np.array([level_from_score(s, {"suspect": th[0], "haut_risque": th[1]}) for s in scores])

    # --- 3. Scores sur la validation et sur le test ---
    parts = {}
    for name, mask in (("val", val), ("test", test)):
        all_x, y = feats[mask], labels[mask].to_numpy()
        x = all_x[FEATURE_COLUMNS]
        ml = ml_score(x)
        rs, crit = _rules_arrays(all_x)
        final = np.array([combine(m, r, c) for m, r, c in zip(ml, rs, crit)])
        parts[name] = {"x": x, "y": y, "ml": ml, "rs": rs, "final": final}

    # --- 4. Calibrage des seuils sur la VALIDATION (jamais sur le test) ---
    # On garde le couple qui donne la meilleure moyenne des F1 (suspect, haut risque).
    best, best_value = CANDIDATE_THRESHOLDS[0], -1
    for th in CANDIDATE_THRESHOLDS:
        m = _metrics(parts["val"]["y"], levels(parts["val"]["final"], th))["par_classe"]
        value = (m["suspect"]["f1"] + m["haut_risque"]["f1"]) / 2
        if value > best_value:
            best, best_value = th, value
    thresholds = {"suspect": best[0], "haut_risque": best[1]}

    # --- 5. Métriques à enregistrer (affichées plus tard dans l'application) ---
    metrics = {
        "decoupage": {"train": int(train.sum()), "validation": int(val.sum()), "test": int(test.sum()),
                      "debut": str(start.date()), "fin_train_jours": train_days,
                      "fin_validation_jours": train_days + val_days},
        "seuils": thresholds,
        "poids": {"ml": 0.6, "regles": 0.4},
        "importance_variables": dict(sorted(zip(FEATURE_COLUMNS, map(float, rf.feature_importances_)),
                                            key=lambda kv: -kv[1])),
        "avertissement": "Jeu de données synthétique : ces scores ne préjugent pas des performances sur des données réelles.",
    }
    for name in ("val", "test"):
        p = parts[name]
        metrics[name] = {
            "regles_seules": _metrics(p["y"], levels(p["rs"], best)),
            "modele_seul": _metrics(p["y"], levels(p["ml"], best)),
            "hybride": _metrics(p["y"], levels(p["final"], best)),
        }
    test = parts["test"]
    test_levels = levels(test["final"], best)
    class_to_alert = lambda scores: levels(scores, best)
    majority = pd.Series(test["y"]).mode().iloc[0]
    naive_levels = np.full(len(test["y"]), majority)
    methods = {
        "naive": _ui_metrics(test["y"], naive_levels, np.zeros(len(test["y"]))),
        "baseline": _ui_metrics(test["y"], class_to_alert(test["rs"]), test["rs"]),
        "ml": _ui_metrics(test["y"], class_to_alert(test["ml"]), test["ml"]),
        "final": _ui_metrics(test["y"], test_levels, test["final"]),
    }
    methods["naive"]["label"] = "Prédiction majoritaire"
    methods["baseline"]["label"] = "Règles seules"
    methods["ml"]["label"] = "Modèle seul"
    methods["final"]["label"] = "Hybride"
    by_attack = {}
    if attack_types is not None:
        attack_values = pd.Series(attack_types, index=feats.index).reindex(parts["test"]["x"].index)
        detected = test_levels != "normal"
        for attack in attack_values.fillna("").astype(str).unique():
            if not attack:
                continue
            mask = attack_values.fillna("").astype(str).to_numpy() == attack
            total = int(mask.sum())
            n_detected = int(detected[mask].sum())
            by_attack[attack] = {
                "total": total, "detected": n_detected,
                "rate": float(n_detected / total) if total else 0.0,
            }
    metrics["ui"] = {
        "split": f"{train_days} jours apprentissage / {val_days} jours validation",
        "n_train": metrics["decoupage"]["train"],
        "n_test": len(test["y"]),
        "feature_importances": metrics["importance_variables"],
        "methods": methods,
        "final": {
            **{key: methods["final"][key] for key in (
                "recall", "precision", "f1", "fpr", "roc_auc", "pr_auc", "accuracy"
            )},
            "by_attack": by_attack,
            "level_confusion": {
                "labels": ["normal", "suspect", "haut_risque"],
                "levels": ["NORMAL", "SUSPECT", "HAUT_RISQUE"],
                "matrix": confusion_matrix(test["y"], test_levels, labels=LEVELS).tolist(),
            },
        },
    }
    # Ce qui est sauvegardé sur le disque : les deux modèles et leurs réglages.
    artifact = {"rf": rf, "iso": iso, "iso_lo": iso_lo, "iso_hi": iso_hi, "thresholds": thresholds,
                "features": FEATURE_COLUMNS}
    # Conversion des nombres numpy en nombres Python pour pouvoir les stocker en JSON.
    metrics = json.loads(json.dumps(metrics, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return artifact, metrics


def _ui_metrics(y_true, y_pred, scores):
    """Binary attack metrics measured from the supplied test predictions."""
    truth = np.asarray(y_true) != "normal"
    predicted = np.asarray(y_pred) != "normal"
    scores = np.asarray(scores, dtype=float)
    tp = int((truth & predicted).sum())
    fp = int((~truth & predicted).sum())
    positives = int(truth.sum())
    negatives = int((~truth).sum())
    precision = tp / max(int(predicted.sum()), 1)
    recall = tp / max(positives, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    auc_defined = len(np.unique(truth)) == 2
    return {
        "recall": float(recall),
        "precision": float(precision),
        "f1": float(f1),
        "fpr": float(fp / max(negatives, 1)),
        "roc_auc": float(roc_auc_score(truth, scores)) if auc_defined else None,
        "pr_auc": float(average_precision_score(truth, scores)) if positives else None,
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }