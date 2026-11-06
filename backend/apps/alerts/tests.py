"""
Tests d'accès (critères R3 / US03 / US21) : 401 sans jeton, 403 pour un rôle non autorisé.
Lancer : python manage.py test apps.alerts
"""
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.detection.models import RiskEvaluation, RiskLevel
from apps.events.models import LoginEvent

from .models import Alert, AlertStatus, Severity


class AccessControlTests(APITestCase):
    ADMIN_ONLY = ["/api/alerts/", "/api/audit/", "/api/ml/model/", "/api/users/"]
    DASHBOARD = ["/api/dashboard/kpis/", "/api/dashboard/timeline/", "/api/dashboard/risk-distribution/",
                 "/api/dashboard/top-targets/"]

    def setUp(self):
        self.admin = User.objects.create_user("admin@test.local", "Mot2Passe!Solide", role=Role.ADMIN)
        self.resp = User.objects.create_user("resp@test.local", "Mot2Passe!Solide", role=Role.RESPONSABLE)
        self.user = User.objects.create_user("user@test.local", "Mot2Passe!Solide", role=Role.UTILISATEUR)

    def test_anonymous_gets_401(self):
        for url in self.ADMIN_ONLY + self.DASHBOARD:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_simple_user_gets_403_everywhere(self):
        self.client.force_authenticate(self.user)
        for url in self.ADMIN_ONLY + self.DASHBOARD:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_responsable_reads_dashboard_but_not_logs(self):
        self.client.force_authenticate(self.resp)
        for url in self.DASHBOARD:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        for url in self.ADMIN_ONLY:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_admin_reads_everything(self):
        self.client.force_authenticate(self.admin)
        for url in self.DASHBOARD + ["/api/alerts/", "/api/events/", "/api/audit/", "/api/users/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_user_can_only_read_own_events(self):
        own_event = LoginEvent.objects.create(
            user=self.user, timestamp="2026-11-04T10:00:00Z", ip_hash="own", success=True
        )
        LoginEvent.objects.create(
            user=self.resp, timestamp="2026-11-04T11:00:00Z", ip_hash="other", success=True
        )
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["id"] for event in response.data["results"]], [own_event.id])
        self.assertEqual(response.data["results"][0]["user"]["email"], self.user.email)

    def test_alert_counts_and_detail_match_frontend_contract(self):
        event = LoginEvent.objects.create(
            user=self.user, timestamp="2026-11-04T10:00:00Z", ip_hash="alert", success=True
        )
        evaluation = RiskEvaluation.objects.create(
            event=event, score=0.9, level=RiskLevel.HAUT_RISQUE,
            triggered_rules=["R1_force_brute"], reasons=["Repeated login failures"]
        )
        alert = Alert.objects.create(evaluation=evaluation, severity=Severity.CRITIQUE)
        # Jeu de statuts contrôlé : 4 nouvelles + 1 en cours = 5 « à traiter ».
        for index in range(3):
            extra_event = LoginEvent.objects.create(
                user=self.user, timestamp=f"2026-11-04T10:{index + 1:02d}:00Z", ip_hash=f"alert-{index}", success=True
            )
            extra_eval = RiskEvaluation.objects.create(
                event=extra_event, score=0.7, level=RiskLevel.HAUT_RISQUE,
                triggered_rules=["NOUVEL_APPAREIL"], reasons=["New device"],
            )
            Alert.objects.create(evaluation=extra_eval, severity=Severity.MOYENNE)
        in_progress_event = LoginEvent.objects.create(
            user=self.user, timestamp="2026-11-04T10:10:00Z", ip_hash="in-progress", success=True
        )
        in_progress_eval = RiskEvaluation.objects.create(
            event=in_progress_event, score=0.7, level=RiskLevel.HAUT_RISQUE,
            triggered_rules=["NOUVEL_APPAREIL"], reasons=["New device"],
        )
        Alert.objects.create(evaluation=in_progress_eval, severity=Severity.MOYENNE, status=AlertStatus.EN_COURS)
        for index, state in enumerate((AlertStatus.TRAITEE, AlertStatus.TRAITEE, AlertStatus.FAUSSE_ALERTE)):
            extra_event = LoginEvent.objects.create(
                user=self.user, timestamp=f"2026-11-04T10:{20 + index:02d}:00Z", ip_hash=f"closed-{index}", success=True
            )
            extra_eval = RiskEvaluation.objects.create(
                event=extra_event, score=0.7, level=RiskLevel.HAUT_RISQUE,
                triggered_rules=["NOUVEL_APPAREIL"], reasons=["New device"],
            )
            Alert.objects.create(evaluation=extra_eval, severity=Severity.MOYENNE, status=state)
        self.client.force_authenticate(self.admin)

        all_counts = self.client.get("/api/alerts/counts/")
        open_counts = self.client.get("/api/alerts/counts/", {"open": "true"})
        detail = self.client.get(f"/api/alerts/{alert.id}/")

        self.assertEqual(all_counts.status_code, 200)
        self.assertEqual(all_counts.data["by_status"][AlertStatus.NOUVELLE], 4)
        self.assertEqual(all_counts.data["by_status"][AlertStatus.EN_COURS], 1)
        self.assertEqual(all_counts.data["by_status"][AlertStatus.TRAITEE], 2)
        self.assertEqual(all_counts.data["by_status"][AlertStatus.FAUSSE_ALERTE], 1)
        self.assertEqual(open_counts.data["by_status"][AlertStatus.NOUVELLE] + open_counts.data["by_status"][AlertStatus.EN_COURS], 5)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["user"]["email"], self.user.email)
        self.assertEqual(detail.data["evaluation"]["level"], RiskLevel.HAUT_RISQUE)
        self.assertEqual(detail.data["triggered_rules"], ["R1_force_brute"])

        bulk = self.client.post("/api/alerts/bulk/", {
            "ids": [alert.id], "status": AlertStatus.TRAITEE,
        }, format="json")

        self.assertEqual(bulk.status_code, 200)
        self.assertEqual(bulk.data["updated"], 1)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.TRAITEE)
