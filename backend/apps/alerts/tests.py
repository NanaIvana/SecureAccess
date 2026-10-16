"""
Tests d'accès (critères R3 / US03 / US21) : 401 sans jeton, 403 pour un rôle non autorisé.
Lancer : python manage.py test apps.alerts
"""
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User


class AccessControlTests(APITestCase):
    ADMIN_ONLY = ["/api/alerts/", "/api/events/", "/api/audit/", "/api/ml/model/", "/api/users/"]
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
