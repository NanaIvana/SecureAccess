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
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

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


def train_detector(feats, labels, timestamps, train_days=120, val_days=30, seed=42):
    """feats : features ; labels : étiquettes réelles ; timestamps : dates (alignés sur feats.index).
    Retourne (artefact à sauvegarder, dictionnaire de métriques)."""
    # --- 1. Découpage dans le temps ---
    start = timestamps.min().normalize()
    train = timestamps < start + pd.Timedelta(days=train_days)
    val = (timestamps >= start + pd.Timedelta(days=train_days)) & (timestamps < start + pd.Timedelta(days=train_days + val_days))
    test = timestamps >= start + pd.Timedelta(days=train_days + val_days)

    x_tr, y_tr = feats[train], labels[train]
    normal_tr = x_tr[y_tr == "normal"]

    # --- 2a. Isolation Forest : apprend le comportement « normal » ---
    iso = IsolationForest(n_estimators=200, random_state=seed, n_jobs=-1).fit(normal_tr)
    raw_tr = -iso.score_samples(normal_tr)
    # Bornes servant à ramener le score d'anomalie entre 0 et 1 (médiane -> 0, percentile 99,5 -> 1).
    iso_lo, iso_hi = float(np.percentile(raw_tr, 50)), float(np.percentile(raw_tr, 99.5))

    # --- 2b. Random Forest : apprend à reconnaître normal / suspect / haut risque ---
    # class_weight : compense le fait que les attaques sont rares par rapport aux connexions normales.
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced_subsample", min_samples_leaf=2,
                                n_jobs=-1, random_state=seed).fit(x_tr, y_tr)
    classes = list(rf.classes_)

    def ml_score(x):
        """Score ML : même formule que dans engine.py (Detector.ml_scores)."""
        proba = rf.predict_proba(x)
        sup = proba[:, classes.index("suspect")] * 0.5 + proba[:, classes.index("haut_risque")]
        anomaly = np.clip((-iso.score_samples(x) - iso_lo) / (iso_hi - iso_lo), 0, 1)
        return W_SUP * sup + W_ISO * anomaly

    def levels(scores, th):
        """Convertit des scores en niveaux avec un couple de seuils (suspect, haut risque)."""
        return np.array([level_from_score(s, {"suspect": th[0], "haut_risque": th[1]}) for s in scores])

    # --- 3. Scores sur la validation et sur le test ---
    parts = {}
    for name, mask in (("val", val), ("test", test)):
        x, y = feats[mask], labels[mask].to_numpy()
        ml = ml_score(x)
        rs, crit = _rules_arrays(x)
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
    # Ce qui est sauvegardé sur le disque : les deux modèles et leurs réglages.
    artifact = {"rf": rf, "iso": iso, "iso_lo": iso_lo, "iso_hi": iso_hi, "thresholds": thresholds,
                "features": FEATURE_COLUMNS}
    # Conversion des nombres numpy en nombres Python pour pouvoir les stocker en JSON.
    metrics = json.loads(json.dumps(metrics, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return artifact, metrics