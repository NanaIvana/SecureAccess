import io
import hashlib
import hmac
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.alerts.models import Alert, AlertStatus
from apps.events.models import LoginEvent

from .models import (
    DetectionConfig,
    DetectionListEntry,
    DetectionRule,
    MLModel,
    RiskEvaluation,
    RiskLevel,
)
from .service import NoActiveModel
from .features import FEATURE_COLUMNS
from .training import train_detector
from .engine import Detector
from datetime import timedelta


class DetectionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin@example.test", password="Password1!", role=Role.ADMIN)
        self.responsable = User.objects.create_user(
            "responsable@example.test", password="Password1!", role=Role.RESPONSABLE,
        )
        self.user = User.objects.create_user("user@example.test", password="Password1!", role=Role.UTILISATEUR)
        self.rules_url = reverse("detection-rules")
        self.config_url = reverse("detection-config")
        self.lists_url = reverse("detection-lists")
        self.models_url = reverse("detection-models")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_reads_allow_admin_and_responsable_but_not_regular_user(self):
        for url in (self.rules_url, self.config_url, self.lists_url, self.models_url):
            self.authenticate(self.admin)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.authenticate(self.responsable)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.authenticate(self.user)
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_rules_are_persisted_and_admin_only_to_change(self):
        rule = DetectionRule.objects.get(key="NOUVEAU_PAYS")
        self.authenticate(self.responsable)
        response = self.client.patch(reverse("detection-rule-detail", args=[rule.pk]), {"points": 44})
        self.assertEqual(response.status_code, 403)
        self.authenticate(self.admin)
        response = self.client.patch(
            reverse("detection-rule-detail", args=[rule.pk]),
            {"points": 44, "is_enabled": False},
        )
        self.assertEqual(response.status_code, 200)
        rule.refresh_from_db()
        self.assertEqual((rule.points, rule.is_enabled), (44, False))
        self.assertEqual(response.data["id"], rule.pk)
        self.assertEqual(response.data["key"], "NOUVEAU_PAYS")

    def test_config_contract_validation_and_persistence(self):
        self.authenticate(self.admin)
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lockout_minutes"], 5)
        self.assertTrue({
            "ml_points", "suspect_threshold", "high_risk_threshold", "critical_threshold",
            "notify_users", "step_up_high_risk", "refuse_critical", "auto_block_critical",
            "auto_block_minutes", "lockout_failures", "lockout_window_minutes", "lockout_minutes",
            "log_retention_days", "sensitive_offset", "pseudonymize_for_responsable", "updated_at",
        }.issubset(response.data))
        payload = dict(response.data)
        payload["ml_points"] = 25
        response = self.client.put(self.config_url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ml_points"], 25)
        self.assertEqual(DetectionConfig.objects.get(pk=1).ml_points, 25)
        payload["critical_threshold"] = payload["high_risk_threshold"]
        response = self.client.put(self.config_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_lists_hash_ip_paginate_and_delete(self):
        self.authenticate(self.responsable)
        response = self.client.post(self.lists_url, {
            "list_type": "BLOCAGE", "kind": "IP", "ip": "198.51.100.8", "comment": "bad source",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.authenticate(self.admin)
        response = self.client.post(self.lists_url, {
            "list_type": "BLOCAGE", "kind": "IP", "ip": "198.51.100.8", "comment": "bad source",
            "expires_days": 2,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        entry = DetectionListEntry.objects.get()
        expected = hmac.new(
            settings.IP_HASH_SECRET.encode(), b"198.51.100.8", hashlib.sha256,
        ).hexdigest()[:32]
        self.assertEqual(entry.value, expected)
        self.assertNotIn("198.51.100.8", response.data["value"])
        self.assertEqual(response.data["list_type"], "BLOCAGE")
        self.assertEqual(response.data["kind"], "IP")
        self.assertIn("results", self.client.get(self.lists_url, {"list_type": "BLOCAGE"}).data)
        self.assertEqual(
            self.client.delete(reverse("detection-list-detail", args=[entry.pk])).status_code, 204,
        )
        self.assertFalse(DetectionListEntry.objects.exists())

    def test_invalid_list_inputs_are_rejected(self):
        self.authenticate(self.admin)
        for payload in (
            {"list_type": "INVALID", "kind": "IP", "ip": "127.0.0.1"},
            {"list_type": "BLOCAGE", "kind": "IP", "ip": "not-an-ip"},
            {"list_type": "BLOCAGE", "kind": "PAYS", "value": ""},
            {"list_type": "BLOCAGE", "kind": "PAYS", "value": "X", "expires_days": 0},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.lists_url, payload, format="json").status_code, 400)

    def test_models_features_and_import_metadata_contracts(self):
        self.authenticate(self.admin)
        model = MLModel.objects.create(
            version="v-test", algorithm="RF", metrics={"ui": {"final": {"recall": 0.75}}}, is_active=True,
        )
        response = self.client.get(self.models_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], model.pk)
        self.assertEqual(response.data[0]["metrics"]["final"]["recall"], 0.75)
        features = self.client.get(reverse("detection-features")).data
        self.assertTrue(all({"name", "label"} <= set(item) for item in features))
        info = self.client.get(reverse("detection-import")).data
        self.assertIn("email", info["columns"])
        self.assertIn("timestamp", info["columns"])
        self.assertEqual(info["label_values"], ["normal", "suspect", "haut_risque"])

    def test_activation_rejects_missing_artifacts_without_changing_active_model(self):
        model = MLModel.objects.create(version="v-missing", algorithm="RF", file_path="")
        url = reverse("detection-model-activate", args=[model.pk])
        self.authenticate(self.responsable)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.authenticate(self.admin)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        model.refresh_from_db()
        self.assertFalse(model.is_active)

    def test_csv_import_persists_only_pseudonymized_ip_and_reports_counts(self):
        self.authenticate(self.admin)
        content = (
            "email,timestamp,ip,country,label,attack_type\n"
            "imported@example.test,2026-10-01T10:00:00Z,198.51.100.10,France,normal,aucune\n"
            "bad-email,2026-10-01T10:00:00Z,not-an-ip,France,normal,aucune\n"
        )
        upload = SimpleUploadedFile("events.csv", content.encode(), content_type="text/csv")
        response = self.client.post(reverse("detection-import"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["imported"], 1)
        self.assertEqual(response.data["labelled"], 1)
        self.assertEqual(response.data["created_users"], 1)
        self.assertEqual(response.data["error_count"], 1)
        event = LoginEvent.objects.get()
        self.assertEqual(len(event.ip_hash), 32)
        self.assertNotIn("198.51.100.10", event.ip_hash)
        self.assertEqual(event.source, LoginEvent.Source.DATASET)

    def test_training_input_validation_happens_before_work(self):
        self.authenticate(self.admin)
        response = self.client.post(reverse("detection-model-train"), {
            "n_estimators": 1, "max_depth": 12, "activate": True, "rescore": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse("detection-model-train"), {
            "n_estimators": 1000, "max_depth": 12, "activate": True, "rescore": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_training_returns_measured_ui_metrics_and_honors_parameters(self):
        labels = np.tile(["normal", "suspect", "haut_risque"], 60)
        features = pd.DataFrame(
            np.random.RandomState(3).normal(size=(180, len(FEATURE_COLUMNS))),
            columns=FEATURE_COLUMNS,
        )
        timestamps = pd.Series(pd.date_range("2026-01-01", periods=180, freq="D", tz="UTC"))
        attacks = pd.Series(np.where(labels == "normal", "aucune", "force_brute"))
        artifact, metrics = train_detector(
            features, pd.Series(labels), timestamps, n_estimators=10, max_depth=3,
            attack_types=attacks,
        )
        ui = metrics["ui"]
        self.assertEqual(artifact["rf"].n_estimators, 10)
        self.assertEqual(artifact["rf"].max_depth, 3)
        self.assertEqual(ui["n_train"], 120)
        self.assertEqual(ui["n_test"], 30)
        self.assertEqual(set(ui["methods"]), {"naive", "baseline", "ml", "final"})
        self.assertEqual(set(ui["final"]["by_attack"]), {"aucune", "force_brute"})
        self.assertEqual(len(ui["final"]["level_confusion"]["matrix"]), 3)
        self.assertGreaterEqual(ui["final"]["recall"], 0)
        self.assertLessEqual(ui["final"]["recall"], 1)

    def test_rescore_without_active_model_returns_conflict_not_fake_success(self):
        self.authenticate(self.admin)
        with patch("apps.detection.views.get_detector", side_effect=NoActiveModel("No active model")):
            response = self.client.post(reverse("detection-rescore"))
        self.assertEqual(response.status_code, 409)
        self.assertIn("detail", response.data)

    def test_sensitive_account_offset_lowers_only_its_risk_threshold(self):
        features = pd.DataFrame(
            [{**{name: 0.0 for name in FEATURE_COLUMNS}, "is_sensitive": False},
             {**{name: 0.0 for name in FEATURE_COLUMNS}, "is_sensitive": True}],
            index=[1, 2],
        )
        detector = Detector.__new__(Detector)
        detector.ml_scores = lambda rows: np.array([0.25, 0.25])
        config = {
            "ml_points": 100,
            "suspect_threshold": 0.30,
            "high_risk_threshold": 0.60,
            "critical_threshold": 0.85,
            "sensitive_offset": 0.10,
        }
        results = detector.evaluate(features, config, {})
        self.assertEqual([item["level"] for item in results], ["normal", "suspect"])

    def test_live_critical_evaluation_applies_configured_account_auto_block(self):
        user = User.objects.create_user("critical@example.test", password="Password1!")
        event = LoginEvent.objects.create(
            user=user, timestamp=timezone.now(), ip_hash="critical-hash",
            country="France", success=True, source=LoginEvent.Source.LIVE,
        )
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.auto_block_critical = True
        config.auto_block_minutes = 12
        config.save()

        class FakeDetector:
            version = "v-critical"

            def evaluate(self, feats, config, rules):
                return [{
                    "event_id": int(feats.index[0]), "score": 0.95, "level": "critique",
                    "ml_score": 0.8, "rules_score": 0.9,
                    "triggered_rules": [], "reasons": ["critical"],
                }]

        with patch("apps.detection.service.get_detector", return_value=FakeDetector()):
            from apps.detection.service import evaluate_events
            evaluate_events([event])
        user.refresh_from_db()
        self.assertGreater(user.blocked_until, timezone.now())
        self.assertLessEqual(
            (user.blocked_until - timezone.now()).total_seconds(), 12 * 60,
        )

    def test_retention_command_purges_only_events_older_than_configured_age(self):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.log_retention_days = 30
        config.save()
        user = User.objects.create_user("retention@example.test", password="Password1!")
        old_event = LoginEvent.objects.create(
            user=user, timestamp=timezone.now() - timedelta(days=31),
            ip_hash="old-hash", success=True,
        )
        recent_event = LoginEvent.objects.create(
            user=user, timestamp=timezone.now() - timedelta(days=29),
            ip_hash="recent-hash", success=True,
        )

        call_command("purge_old_data", stdout=io.StringIO())

        self.assertFalse(LoginEvent.objects.filter(pk=old_event.pk).exists())
        self.assertTrue(LoginEvent.objects.filter(pk=recent_event.pk).exists())

    def test_rescore_persists_real_level_and_removes_obsolete_new_alert(self):
        user = User.objects.create_user("event@example.test", password="Password1!")
        event = LoginEvent.objects.create(
            user=user, timestamp=timezone.now(), ip_hash="known-hash", country="France", success=True,
        )

        class FakeDetector:
            version = "v-policy"

            def __init__(self):
                self.level = "critique"

            def evaluate(self, feats, config, rules):
                self.asserted_flags = list(feats["is_blocked"])
                return [{
                    "event_id": int(feats.index[0]), "score": 0.91, "level": self.level,
                    "ml_score": 0.5, "rules_score": 0.7,
                    "triggered_rules": ["IP_MAUVAISE_REPUTATION"], "reasons": ["blocked"],
                }]

        detector = FakeDetector()
        blocked = DetectionListEntry.objects.create(
            list_type="BLOCAGE", kind="IP", value="known-hash", label="IP pseudonymisée",
        )
        with patch("apps.detection.views.get_detector", return_value=detector):
            response = self.client.post(reverse("detection-rescore"))
        self.assertEqual(response.status_code, 401)
        self.authenticate(self.admin)
        with patch("apps.detection.views.get_detector", return_value=detector):
            response = self.client.post(reverse("detection-rescore"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["levels"]["CRITIQUE"], 1)
        evaluation = RiskEvaluation.objects.get(event=event)
        self.assertEqual(evaluation.level, RiskLevel.CRITIQUE)
        self.assertTrue(detector.asserted_flags[0])
        alert = Alert.objects.get(evaluation=evaluation)
        self.assertEqual(alert.status, AlertStatus.NOUVELLE)

        detector.level = "normal"
        with patch("apps.detection.views.get_detector", return_value=detector):
            response = self.client.post(reverse("detection-rescore"))
        self.assertEqual(response.status_code, 200)
        evaluation.refresh_from_db()
        self.assertEqual(evaluation.level, RiskLevel.NORMAL)
        self.assertFalse(Alert.objects.filter(evaluation=evaluation).exists())
        blocked.delete()
