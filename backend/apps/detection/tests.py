
"""
Tests unitaires du mécanisme de détection.

Vérifie :
- Les règles de détection.
- La combinaison des scores.
- La classification des niveaux de risque.
- Le fonctionnement du moteur ML.
"""

import numpy as np
import pandas as pd

from django.test import SimpleTestCase

from .engine import Detector, combine, level_from_score
from .features import FEATURE_COLUMNS
from .rules import apply_rules


class DetectionRulesTests(SimpleTestCase):
    """Tests des règles de détection."""

    def test_ten_failed_logins_trigger_critical_rule(self):
        features = {"failed_10min": 10}

        score, triggered, reasons, critical = apply_rules(features)

        self.assertGreaterEqual(score, 0.9)
        self.assertIn("R1", triggered)
        self.assertTrue(critical)
        self.assertTrue(reasons)

    def test_impossible_travel_triggers_rule(self):
        features = {"speed_kmh": 1000}

        score, triggered, reasons, critical = apply_rules(features)

        self.assertGreaterEqual(score, 0.8)
        self.assertIn("R2", triggered)
        self.assertTrue(critical)

    def test_new_country_triggers_rule(self):
        features = {"is_new_country": 1}

        score, triggered, reasons, critical = apply_rules(features)

        self.assertGreater(score, 0)
        self.assertIn("R4", triggered)

    def test_empty_features_do_not_crash(self):
        score, triggered, reasons, critical = apply_rules({})

        self.assertEqual(score, 0)
        self.assertEqual(triggered, [])
        self.assertFalse(critical)


class DetectionEngineTests(SimpleTestCase):
    """Tests du moteur hybride."""

    def test_combine_scores(self):
        score = combine(0.5, 0.5, False)

        self.assertAlmostEqual(score, 0.5)

    def test_critical_rule_enforces_minimum_score(self):
        score = combine(0.2, 0.1, True)

        self.assertGreaterEqual(score, 0.75)

    def test_normal_level(self):
        thresholds = {"suspect": 0.30, "haut_risque": 0.60}

        self.assertEqual(
            level_from_score(0.20, thresholds),
            "normal"
        )

    def test_suspect_level(self):
        thresholds = {"suspect": 0.30, "haut_risque": 0.60}

        self.assertEqual(
            level_from_score(0.40, thresholds),
            "suspect"
        )

    def test_high_risk_level(self):
        thresholds = {"suspect": 0.30, "haut_risque": 0.60}

        self.assertEqual(
            level_from_score(0.80, thresholds),
            "haut_risque"
        )

    def test_ml_scores_are_bounded(self):
        """Vérifie que le score ML reste compris entre 0 et 1."""

        class FakeRandomForest:
            classes_ = np.array([
                "normal",
                "suspect",
                "haut_risque"
            ])

            def predict_proba(self, data):
                return np.tile(
                    [0.2, 0.5, 0.3],
                    (len(data), 1)
                )

        class FakeIsolationForest:
            def score_samples(self, data):
                return np.full(len(data), -0.5)

        artifact = {
            "rf": FakeRandomForest(),
            "iso": FakeIsolationForest(),
            "iso_lo": 0.0,
            "iso_hi": 1.0,
            "thresholds": {
                "suspect": 0.30,
                "haut_risque": 0.60
            }
        }

        detector = Detector(artifact)

        features = pd.DataFrame(
            np.zeros((3, len(FEATURE_COLUMNS))),
            columns=FEATURE_COLUMNS
        )

        scores = detector.ml_scores(features)

        self.assertEqual(len(scores), 3)
        self.assertTrue(np.isfinite(scores).all())
        self.assertTrue(np.all(scores >= 0))
        self.assertTrue(np.all(scores <= 1))

    def test_empty_features_return_empty_scores(self):
        """Un lot vide ne doit pas provoquer d'erreur."""

        class FakeRandomForest:
            classes_ = np.array(["normal"])

        class FakeIsolationForest:
            pass

        artifact = {
            "rf": FakeRandomForest(),
            "iso": FakeIsolationForest(),
            "iso_lo": 0.0,
            "iso_hi": 1.0,
            "thresholds": {
                "suspect": 0.30,
                "haut_risque": 0.60
            }
        }

        detector = Detector(artifact)

        features = pd.DataFrame(columns=FEATURE_COLUMNS)

        scores = detector.ml_scores(features)

        self.assertEqual(len(scores), 0)

