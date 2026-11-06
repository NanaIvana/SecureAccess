from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.events.models import LoginEvent


class ReportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("manager@example.com", "password", role="RESPONSABLE")
        self.client.force_authenticate(self.user)
        LoginEvent.objects.create(
            user=self.user, timestamp=timezone.now(), ip_hash="private-hash", success=True,
        )

    def test_summary_has_frontend_contract_and_pseudonymous_incident_data(self):
        response = self.client.get("/api/reports/summary/", {"days": 7})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["kpis"]["total"], 1)
        self.assertEqual(response.data["kpis"]["successes"], 1)
        self.assertEqual(response.data["kpis"]["risky_rate"], 0)
        self.assertIn("risky_rate", response.data["previous"])
        self.assertIn("by_severity", response.data["alerts"])
        self.assertEqual(response.data["incidents"], [])
        self.assertEqual(response.data["period"]["days"], 7)

    def test_invalid_period_is_rejected(self):
        response = self.client.get("/api/reports/summary/", {"date_from": "2026-02-02", "date_to": "2026-01-01"})

        self.assertEqual(response.status_code, 400)

    def test_csv_and_pdf_exports_return_downloadable_files(self):
        csv_response = self.client.get("/api/reports/summary/", {"days": 7, "export": "csv"})
        pdf_response = self.client.get("/api/reports/summary/", {"days": 7, "export": "pdf"})
        protection_pdf = self.client.get("/api/protection/", {"export": "pdf"})

        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertEqual(pdf_response.status_code, 200)
        self.assertTrue(pdf_response.content.startswith(b"%PDF-"))
        self.assertEqual(protection_pdf.status_code, 200)
        self.assertTrue(protection_pdf.content.startswith(b"%PDF-"))

    def test_protection_response_reports_real_security_configuration(self):
        response = self.client.get("/api/protection/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["measures"])
        self.assertEqual(
            response.data["measures"][0]["status"],
            "active",
        )
