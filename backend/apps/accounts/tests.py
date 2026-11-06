from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.detection.models import (
    DetectionConfig, ProgressiveLockout, RiskEvaluation, RiskLevel,
)
from apps.events.models import LoginEvent, Notification

from .models import User


class CurrentAccountApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            "user@example.com", "password", full_name="Secure User"
        )
        self.client.force_authenticate(self.user)

    def _scored_login(self, level, score):
        def score_login(user, request, device_data=None, success=True, reason="", return_event=False):
            event = LoginEvent.objects.create(
                user=user,
                timestamp=timezone.now(),
                ip_hash="test-login-hash",
                success=True,
                source=LoginEvent.Source.LIVE,
            )
            RiskEvaluation.objects.create(
                event=event, score=score, level=level, ml_score=score,
                rules_score=0, model_version="test",
            )
            risk = {"level": level, "score": score}
            return (risk, event) if return_event else risk
        return score_login

    def test_profile_update_returns_complete_user(self):
        response = self.client.patch("/api/me/", {"full_name": "Updated Name"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["role"], self.user.role)
        self.assertEqual(response.data["full_name"], "Updated Name")

    def test_password_change_checks_current_password_and_updates_hash(self):
        wrong = self.client.post("/api/auth/change-password/", {
            "old_password": "wrong",
            "new_password": "An0ther!Secure-Phrase-74",
        })
        self.assertEqual(wrong.status_code, 400)

        response = self.client.post("/api/auth/change-password/", {
            "old_password": "password",
            "new_password": "An0ther!Secure-Phrase-74",
        })

        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("An0ther!Secure-Phrase-74"))

    def test_security_summary_contains_dashboard_fields(self):
        response = self.client.get("/api/me/security/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data["status"], ["ok", "warn", "high", "danger"])
        self.assertEqual(response.data["stats"]["devices"], 0)
        self.assertEqual(response.data["recent_events"], [])
        self.assertEqual(response.data["notices"], [])

    def test_admin_can_create_user_and_read_activity(self):
        admin = User.objects.create_user("admin@example.com", "password", role="ADMIN")
        self.client.force_authenticate(admin)
        create = self.client.post("/api/users/", {
            "email": "new@example.com",
            "password": "C0mpl3x!Passphrase-A74",
            "full_name": "New User",
            "role": "UTILISATEUR",
            "work_profile": "JOURNEE",
            "profile_type": "ENSEIGNANT",
        })

        self.assertEqual(create.status_code, 201)
        created_user = User.objects.get(email="new@example.com")
        self.assertEqual(created_user.profile_type, "ENSEIGNANT")
        activity = self.client.get(f"/api/users/{created_user.id}/activity/")

        self.assertEqual(activity.status_code, 200)
        self.assertEqual(activity.data["user"]["email"], created_user.email)
        self.assertEqual(len(activity.data["hours"]), 24)
        self.assertEqual(activity.data["stats"]["total"], 0)

    def test_notifications_are_private_and_can_be_read_and_answered(self):
        event = LoginEvent.objects.create(
            user=self.user, timestamp=timezone.now(), ip_hash="private-hash", success=True
        )
        notification = Notification.objects.create(
            user=self.user,
            event=event,
            kind=Notification.Kind.CONNEXION_INHABITUELLE,
            title="Connexion inhabituelle",
            message="Vérifiez cette connexion.",
            needs_response=True,
        )
        other = User.objects.create_user("other@example.com", "password")
        Notification.objects.create(
            user=other,
            kind=Notification.Kind.MOT_DE_PASSE,
            title="Mot de passe",
            message="Changé.",
        )

        listing = self.client.get("/api/notifications/")
        unread = self.client.get("/api/notifications/unread/")
        response = self.client.post(f"/api/notifications/{notification.id}/respond/", {"response": "CONFIRMEE"})

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["results"]), 1)
        self.assertEqual(listing.data["results"][0]["event"], event.id)
        self.assertEqual(unread.data, {"unread": 1, "pending": 1})
        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertEqual(notification.response, Notification.Response.CONFIRMEE)
        self.assertIsNotNone(notification.read_at)
        Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.MOT_DE_PASSE,
            title="Mot de passe",
            message="Modifié.",
        )
        self.assertEqual(self.client.post("/api/notifications/read_all/").status_code, 200)
        self.assertEqual(self.client.get("/api/notifications/unread/").data["unread"], 0)

    def test_two_factor_setup_and_login_challenge(self):
        setup = self.client.post("/api/auth/2fa/")
        self.assertEqual(setup.status_code, 200)
        self.assertTrue(setup.data["qr_svg"].startswith("data:image/svg+xml;base64,"))

        from .views import _totp_code

        code = _totp_code(setup.data["secret"])
        confirm = self.client.post("/api/auth/2fa/confirm/", {"code": code})
        self.assertEqual(confirm.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)

        anonymous = APIClient()
        login = anonymous.post("/api/auth/login/", {
            "email": self.user.email,
            "password": "password",
            "device": {
                "fingerprint": "a" * 32,
                "device_type": "Ordinateur",
                "os": "Linux",
                "browser": "Chrome",
            },
        }, format="json")
        self.assertEqual(login.status_code, 200)
        challenge = login.data["two_factor"]["challenge"]
        verified = anonymous.post("/api/auth/2fa/verify/", {"challenge": challenge, "code": _totp_code(setup.data["secret"])})

        self.assertEqual(verified.status_code, 200)
        self.assertIn("access", verified.data)
        self.assertEqual(verified.data["user"]["email"], self.user.email)
        event = LoginEvent.objects.get(user=self.user, source=LoginEvent.Source.LIVE, success=True)
        self.assertEqual(event.device.fingerprint, "a" * 32)

    def test_password_login_records_an_ip_hash_and_device(self):
        response = APIClient().post("/api/auth/login/", {
            "email": self.user.email,
            "password": "password",
            "device": {
                "fingerprint": "a" * 32,
                "device_type": "Ordinateur",
                "os": "Linux",
                "browser": "Firefox",
            },
        }, format="json", REMOTE_ADDR="203.0.113.15")

        self.assertEqual(response.status_code, 200)
        event = LoginEvent.objects.get(user=self.user, source=LoginEvent.Source.LIVE, success=True)
        self.assertNotEqual(event.ip_hash, "203.0.113.15")
        self.assertEqual(event.device.browser, "Firefox")

    def test_refuse_critical_preserves_scored_event_and_denies_tokens(self):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.refuse_critical = True
        config.step_up_high_risk = True
        config.save()

        with patch(
            "apps.accounts.views._record_live_login",
            side_effect=self._scored_login(RiskLevel.CRITIQUE, 0.95),
        ):
            response = APIClient().post("/api/auth/login/", {
                "email": self.user.email, "password": "password",
            })

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("access", response.data)
        self.assertEqual(response.data["risk"]["level"], RiskLevel.CRITIQUE)
        event = LoginEvent.objects.get(user=self.user, source=LoginEvent.Source.LIVE)
        self.assertTrue(hasattr(event, "evaluation"))

    def test_step_up_enrolls_totp_for_unenrolled_high_risk_login(self):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.step_up_high_risk = True
        config.refuse_critical = False
        config.lockout_failures = 0
        config.save()
        anonymous = APIClient()

        with patch(
            "apps.accounts.views._record_live_login",
            side_effect=self._scored_login(RiskLevel.HAUT_RISQUE, 0.70),
        ):
            login = anonymous.post("/api/auth/login/", {
                "email": self.user.email, "password": "password",
            })

        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["two_factor"]["method"], "setup")
        challenge = login.data["two_factor"]["challenge"]
        setup = anonymous.post("/api/auth/2fa/setup-login/", {"challenge": challenge})
        self.assertEqual(setup.status_code, 200)
        from .views import _totp_code
        verified = anonymous.post("/api/auth/2fa/verify/", {
            "challenge": challenge, "code": _totp_code(setup.data["secret"]),
        })

        self.assertEqual(verified.status_code, 200)
        self.assertIn("access", verified.data)
        self.assertEqual(verified.data["risk"]["level"], RiskLevel.HAUT_RISQUE)
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)
        self.assertEqual(
            LoginEvent.objects.filter(user=self.user, source=LoginEvent.Source.LIVE).count(), 1,
        )

    def test_refuse_critical_also_denies_tokens_after_existing_totp_flow(self):
        from .views import _totp_code

        setup = self.client.post("/api/auth/2fa/")
        self.assertEqual(self.client.post(
            "/api/auth/2fa/confirm/", {"code": _totp_code(setup.data["secret"])},
        ).status_code, 200)
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.refuse_critical = True
        config.lockout_failures = 0
        config.save()
        anonymous = APIClient()
        login = anonymous.post("/api/auth/login/", {
            "email": self.user.email, "password": "password",
        })
        self.assertEqual(login.data["two_factor"]["method"], "totp")

        with patch(
            "apps.accounts.views._record_live_login",
            side_effect=self._scored_login(RiskLevel.CRITIQUE, 0.95),
        ):
            verified = anonymous.post("/api/auth/2fa/verify/", {
                "challenge": login.data["two_factor"]["challenge"],
                "code": _totp_code(setup.data["secret"]),
            })
        self.assertEqual(verified.status_code, 403)
        self.assertNotIn("access", verified.data)
        self.assertTrue(LoginEvent.objects.filter(
            user=self.user, source=LoginEvent.Source.LIVE, evaluation__level=RiskLevel.CRITIQUE,
        ).exists())

    def test_step_up_setting_keeps_normal_risk_login_compatible(self):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.step_up_high_risk = True
        config.refuse_critical = True
        config.save()

        with patch(
            "apps.accounts.views._record_live_login",
            side_effect=self._scored_login(RiskLevel.NORMAL, 0.10),
        ):
            response = APIClient().post("/api/auth/login/", {
                "email": self.user.email, "password": "password",
            })

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["risk"]["level"], RiskLevel.NORMAL)

    def test_progressive_lockout_is_account_and_hashed_source_scoped(self):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.lockout_failures = 5
        config.lockout_minutes = 5
        config.save()
        source_ip = "203.0.113.55"
        client = APIClient()
        payload = {"email": self.user.email, "password": "wrong"}

        failures = [client.post("/api/auth/login/", payload, REMOTE_ADDR=source_ip) for _ in range(5)]
        sixth = client.post("/api/auth/login/", payload, REMOTE_ADDR=source_ip)
        self.assertTrue(all(response.status_code == 401 for response in failures))
        self.assertEqual(sixth.status_code, 423)
        self.assertEqual(sixth.data["retry_after_seconds"], 300)
        lockout = ProgressiveLockout.objects.get(user=self.user)
        self.assertEqual(lockout.level, 1)
        self.assertNotEqual(lockout.source_hash, source_ip)
        self.assertEqual(len(lockout.source_hash), 32)

        locked = client.post("/api/auth/login/", {
            "email": self.user.email, "password": "password",
        }, REMOTE_ADDR=source_ip)
        self.assertEqual(locked.status_code, 423)
        other_source = client.post("/api/auth/login/", payload, REMOTE_ADDR="203.0.113.56")
        self.assertEqual(other_source.status_code, 401)

    def test_lockout_escalates_and_success_clears_the_source_streak(self):
        from apps.accounts.views import _login_source_hash, _record_failed_source_attempt

        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.lockout_failures = 1
        config.lockout_minutes = 5
        config.save()
        source_hash = _login_source_hash(type("Request", (), {"META": {"REMOTE_ADDR": "198.51.100.70"}})())
        first = _record_failed_source_attempt(self.user, source_hash)
        self.assertEqual(first.level, 1)
        self.assertEqual(round((first.locked_until - timezone.now()).total_seconds()), 300)
        first.locked_until = timezone.now() - timedelta(seconds=1)
        first.save(update_fields=["locked_until"])
        second = _record_failed_source_attempt(self.user, source_hash)
        self.assertEqual(second.level, 2)
        self.assertGreaterEqual((second.locked_until - timezone.now()).total_seconds(), 899)
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": "password"},
            REMOTE_ADDR="198.51.100.70",
        )
        self.assertEqual(response.status_code, 423)
        second.locked_until = timezone.now() - timedelta(seconds=1)
        second.save(update_fields=["locked_until"])
        response = client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": "password"},
            REMOTE_ADDR="198.51.100.70",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProgressiveLockout.objects.filter(user=self.user).exists())

    def test_critical_auto_block_returns_lock_response_instead_of_tokens(self):
        from datetime import timedelta

        def score_critical(user, request, device_data=None, success=True, reason="", return_event=False):
            user.blocked_until = timezone.now() + timedelta(minutes=7)
            user.save(update_fields=["blocked_until"])
            risk = {"level": "CRITIQUE", "score": 0.95}
            return (risk, None) if return_event else risk

        with patch("apps.accounts.views._record_live_login", side_effect=score_critical):
            response = APIClient().post("/api/auth/login/", {
                "email": self.user.email,
                "password": "password",
            }, REMOTE_ADDR="203.0.113.70")
        self.assertEqual(response.status_code, 423)
        self.assertIn("retry_after_seconds", response.data)
        self.assertNotIn("access", response.data)

    def test_bad_second_factor_attempt_uses_progressive_source_lockout(self):
        from .views import _totp_code

        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        config.lockout_failures = 1
        config.save()
        setup = self.client.post("/api/auth/2fa/")
        confirm = self.client.post("/api/auth/2fa/confirm/", {"code": _totp_code(setup.data["secret"])})
        self.assertEqual(confirm.status_code, 200)
        login = APIClient().post("/api/auth/login/", {
            "email": self.user.email,
            "password": "password",
        }, REMOTE_ADDR="192.0.2.5")
        challenge = login.data["two_factor"]["challenge"]
        response = APIClient().post(
            "/api/auth/2fa/verify/", {"challenge": challenge, "code": "invalid"},
            REMOTE_ADDR="192.0.2.5",
        )
        self.assertEqual(response.status_code, 423)
        self.assertIn("retry_after_seconds", response.data)


    def test_demo_lab_attack_replays_the_real_login_endpoint_for_own_test_account(self):
        from django.test import override_settings

        demo = User.objects.create_user("enseignant@demo.secureaccess.test", "password")
        self.client.force_authenticate(demo)
        with override_settings(DEMO_MODE=True):
            response = self.client.post("/api/lab/attacks/", {
                "scenario": "normal", "password": "password",
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["attempts"][0]["http_status"], 200)
        event = LoginEvent.objects.filter(user=demo, source=LoginEvent.Source.LIVE).latest("id")
        self.assertTrue(event.success)

    def test_demo_lab_attack_is_disabled_by_default(self):
        from django.test import override_settings

        demo = User.objects.create_user("secretaire@demo.secureaccess.test", "password")
        self.client.force_authenticate(demo)
        with override_settings(DEMO_MODE=False):
            response = self.client.post("/api/lab/attacks/", {"scenario": "normal", "password": "password"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_password_reset_sends_generic_response_and_accepts_valid_token(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.test import override_settings
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            request = APIClient().post("/api/auth/password-reset/", {"email": self.user.email})
            self.assertEqual(request.status_code, 200)
            reset = APIClient().post("/api/auth/password-reset/confirm/", {
                "uid": uid, "token": token, "new_password": "An0ther!Secure-Phrase-74",
            })

        self.assertEqual(reset.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("An0ther!Secure-Phrase-74"))
