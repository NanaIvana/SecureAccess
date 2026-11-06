from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.alerts.models import Alert, Severity
from apps.detection.models import RiskEvaluation, RiskLevel
from apps.events.models import LoginEvent


class DashboardSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin@example.com", "password", role=Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def test_summary_returns_dashboard_data(self):
        timestamp = timezone.now() - timedelta(days=1)
        user = User.objects.create_user("person@example.com", "password")
        event = LoginEvent.objects.create(
            user=user,
            timestamp=timestamp,
            ip_hash="hashed-ip",
            country="France",
            city="Paris",
            success=True,
        )
        evaluation = RiskEvaluation.objects.create(
            event=event,
            score=0.9,
            level=RiskLevel.HAUT_RISQUE,
            triggered_rules=["R1_force_brute"],
            reasons=["Several recent failed logins"],
        )
        Alert.objects.create(
            evaluation=evaluation,
            severity=Severity.CRITIQUE,
            created_at=timestamp,
        )

        response = self.client.get("/api/dashboard/summary/?days=30")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["total"], 1)
        self.assertEqual(data["kpis"]["high_risk"], 0)
        self.assertEqual(data["kpis"]["critical"], 1)
        self.assertEqual(data["alerts"], {"open": 1, "open_critical": 1})
        self.assertEqual(data["rules"], [{"code": "R1_force_brute", "count": 1}])
        self.assertEqual(data["countries"], [{"country": "France", "n": 1}])
        self.assertEqual(data["latest_alerts"][0]["user"], "person@example.com")
        self.assertEqual(data["top_users"][0]["id"], user.id)
        self.assertEqual(len(data["hours"]), 24)
        self.assertIsNone(data["model"])

    def test_summary_requires_dashboard_role(self):
        self.client.force_authenticate(User.objects.create_user("person@example.com", "password"))

        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 403)
