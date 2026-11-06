from django.test import TestCase
from rest_framework.test import APIClient

from apps.detection.models import DetectionConfig, RiskEvaluation, RiskLevel
from apps.accounts.models import User

from .models import LoginEvent


class EventApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user("owner@example.com", "password")
        self.other_user = User.objects.create_user("other@example.com", "password")
        self.event = LoginEvent.objects.create(
            user=self.owner,
            timestamp="2026-11-04T10:00:00Z",
            ip_hash="hashed-ip",
            country="Cameroon",
            city="Yaounde",
            success=True,
        )
        LoginEvent.objects.create(
            user=self.other_user,
            timestamp="2026-11-04T11:00:00Z",
            ip_hash="other-hashed-ip",
            country="France",
            city="Paris",
            success=False,
        )

    def test_user_lists_only_own_events_with_frontend_shape(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/events/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        event = payload["results"][0]
        self.assertEqual(event["user"]["email"], self.owner.email)
        self.assertIsNone(event["score"])
        self.assertIsNone(event["level"])
        self.assertEqual(event["triggered_rules"], [])
        self.assertEqual(event["home"]["city"], "")

    def test_user_can_filter_multiple_risk_levels(self):
        high_risk_event = LoginEvent.objects.create(
            user=self.owner,
            timestamp="2026-11-04T12:00:00Z",
            ip_hash="high-risk-hash",
            success=False,
        )
        critical_event = LoginEvent.objects.create(
            user=self.owner,
            timestamp="2026-11-04T13:00:00Z",
            ip_hash="critical-hash",
            success=False,
        )
        RiskEvaluation.objects.create(event=high_risk_event, score=0.7, level=RiskLevel.HAUT_RISQUE)
        RiskEvaluation.objects.create(event=critical_event, score=0.9, level=RiskLevel.CRITIQUE)
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            "/api/events/",
            {"user": self.owner.id, "level": "HAUT_RISQUE,CRITIQUE", "page_size": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_country_list_is_available_to_admin(self):
        admin = User.objects.create_user("admin@example.com", "password", role="ADMIN")
        self.client.force_authenticate(admin)

        response = self.client.get("/api/events/countries/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Cameroon", "France"])

    def test_owner_can_report_event_and_only_admin_receives_notification(self):
        admin = User.objects.create_user("admin@example.com", "password", role="ADMIN")
        self.client.force_authenticate(self.owner)

        response = self.client.post(f"/api/events/{self.event.id}/report/", {"comment": "Ce n'était pas moi."})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(admin.notifications.count(), 1)
        self.assertIn("Ce n'était pas moi.", admin.notifications.first().message)
        self.client.force_authenticate(self.other_user)
        forbidden = self.client.post(f"/api/events/{self.event.id}/report/", {})
        self.assertEqual(forbidden.status_code, 404)

    def test_responsable_event_reads_pseudonymize_user_identity_when_enabled(self):
        responsable = User.objects.create_user(
            "responsable@example.com", "password", role="RESPONSABLE",
        )
        event = LoginEvent.objects.create(
            user=responsable,
            timestamp="2026-11-04T12:00:00Z",
            ip_hash="safe-hash",
            country="Cameroon",
            city="Yaounde",
            success=True,
        )
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.pseudonymize_for_responsable = True
        config.save()
        self.client.force_authenticate(responsable)

        response = self.client.get(f"/api/events/{event.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["user"]["email"], responsable.email)
        self.assertTrue(response.data["user"]["email"].startswith("Utilisateur-"))
        self.assertEqual(response.data["user"]["email"], response.data["user"]["full_name"])
        self.assertEqual(response.data["home"]["city"], "")
        self.assertIsNone(response.data["home"]["latitude"])

    def test_responsable_identity_setting_can_be_disabled(self):
        responsable = User.objects.create_user(
            "responsable2@example.com", "password", role="RESPONSABLE",
        )
        event = LoginEvent.objects.create(
            user=responsable,
            timestamp="2026-11-04T12:00:00Z",
            ip_hash="safe-hash2",
            success=True,
        )
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.pseudonymize_for_responsable = False
        config.save()
        self.client.force_authenticate(responsable)

        response = self.client.get(f"/api/events/{event.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], responsable.email)
