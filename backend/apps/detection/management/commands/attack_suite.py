"""Exécute une suite de scénarios via le vrai endpoint de connexion et affiche attaque → décision."""
import hashlib
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ProfileType, Role, User
from apps.events.models import Device, LoginEvent
from apps.detection.models import MLModel, RiskEvaluation, UserProfile


class Command(BaseCommand):
    help = "Rejoue au moins huit scénarios de connexion sur le pipeline réel (mode DEMO_MODE)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="DemoSchool2026!")

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("Activez DEMO_MODE=True dans backend/.env avant d'exécuter attack_suite.")
        if not MLModel.objects.filter(is_active=True).exists():
            raise CommandError("Aucun modèle actif : lancez d'abord python manage.py train_model.")
        password = options["password"]
        results = []

        # La transaction est annulée à la fin : la suite valide le vrai endpoint sans polluer les tableaux de bord.
        with transaction.atomic():
            ip_prefix = f"10.251.{secrets.randbelow(250) + 1}"
            test_ip = lambda host: f"{ip_prefix}.{host}"
            users = []
            for index in range(12):
                email = f"attack-suite-{index}@demo.secureaccess.test"
                user = User.objects.create_user(
                    email=email, password=password, full_name=f"Compte de test {index + 1}",
                    role=Role.UTILISATEUR,
                    profile_type=ProfileType.ENSEIGNANT if index % 2 == 0 else ProfileType.SECRETAIRE,
                    home_city="Yaoundé", home_country="Cameroun", home_lat=3.848, home_lon=11.502,
                )
                UserProfile.objects.create(user=user, usual_hours=list(range(7, 19)), usual_countries=["Cameroun"])
                baseline_fingerprint = hashlib.sha256(f"baseline-device-{index}".encode()).hexdigest()[:32]
                baseline_device = Device.objects.create(
                    user=user, fingerprint=baseline_fingerprint, device_type="Ordinateur", os="Windows", browser="Chrome",
                )
                LoginEvent.objects.create(
                    user=user, device=baseline_device,
                    timestamp=timezone.now().replace(hour=2, minute=0, second=0, microsecond=0),
                    ip_hash=hashlib.sha256(f"baseline-ip-{index}".encode()).hexdigest()[:32],
                    country="Cameroun", city="Yaoundé", latitude=3.848, longitude=11.502,
                    success=True, label="normal", attack_type="demo_baseline", source=LoginEvent.Source.DATASET,
                )
                users.append(user)

            def attempt(user, secret, remote_ip, fingerprint, user_agent="Mozilla/5.0", extra=None):
                client = APIClient()
                headers = {"HTTP_USER_AGENT": user_agent, "HTTP_X_SECUREACCESS_DEMO_TIME": "09:00"}
                if extra:
                    headers.update(extra)
                payload = {
                    "email": user.email,
                    "password": secret,
                    "device": {"fingerprint": fingerprint, "device_type": "Ordinateur", "os": "Windows", "browser": "Chrome"},
                }
                previous_event_id = LoginEvent.objects.filter(user=user, source=LoginEvent.Source.LIVE).order_by("-id").values_list("id", flat=True).first() or 0
                response = client.post("/api/auth/login/", payload, format="json", HTTP_HOST="localhost", REMOTE_ADDR=remote_ip, **headers)
                event = LoginEvent.objects.filter(user=user, source=LoginEvent.Source.LIVE, id__gt=previous_event_id).order_by("-id").first()
                evaluation = None
                if event:
                    try:
                        evaluation = event.evaluation
                    except RiskEvaluation.DoesNotExist:
                        evaluation = None
                return response.status_code, evaluation, bool(getattr(response, "data", {}).get("two_factor"))

            # 1. Connexion normale : appareil connu, pays habituel et horaire de journée.
            normal_fingerprint = hashlib.sha256(b"baseline-device-0").hexdigest()[:32]
            code, ev, step_up = attempt(users[0], password, test_ip(11), normal_fingerprint)
            results.append(("Connexion normale", code, getattr(ev, "level", "—"), step_up))

            # 2. Identifiant inconnu : même code public qu'un mot de passe incorrect
            client = APIClient()
            code = client.post("/api/auth/login/", {
                "email": "unknown@demo.secureaccess.test", "password": "WrongPassword2026!",
                "device": {"fingerprint": hashlib.sha256(b"unknown").hexdigest()[:32], "device_type": "Ordinateur", "os": "Windows", "browser": "Chrome"},
            }, format="json", HTTP_HOST="localhost", REMOTE_ADDR=test_ip(12)).status_code
            results.append(("Énumération d'identifiant", code, "—", False))

            # 3. Mot de passe incorrect
            code, ev, step_up = attempt(users[1], "IncorrectPassword2026!", test_ip(13), hashlib.sha256(b"wrong").hexdigest()[:32])
            results.append(("Mot de passe incorrect", code, getattr(ev, "level", "—"), step_up))

            # 4. Nouvel appareil
            code, ev, step_up = attempt(users[2], password, test_ip(14), hashlib.sha256(b"new-device").hexdigest()[:32])
            results.append(("Nouvel appareil", code, getattr(ev, "level", "—"), step_up))

            # 5. Client automatisé (R10)
            code, ev, step_up = attempt(users[3], password, test_ip(15), hashlib.sha256(b"robot").hexdigest()[:32], "python-requests/2.31")
            results.append(("Client automatisé", code, getattr(ev, "level", "—"), step_up))

            # 6. Force brute : cinq échecs puis le sixième essai doit être verrouillé
            last_code, last_ev, last_step_up = None, None, False
            for index in range(6):
                last_code, last_ev, last_step_up = attempt(users[4], f"BadPassword-{index}!", test_ip(16), hashlib.sha256(f"brute-{index}".encode()).hexdigest()[:32])
            results.append(("Force brute (6e essai)", last_code, getattr(last_ev, "level", "—"), last_step_up))

            # 7. Password spraying : même source sur 11 comptes distincts
            spray_codes = []
            for index in range(11):
                code, spray_eval, step_up = attempt(users[index], "WrongSprayPassword!", test_ip(17), hashlib.sha256(f"spray-{index}".encode()).hexdigest()[:32])
                spray_codes.append((code, getattr(spray_eval, "level", "—"), step_up))
            results.append(("Password spraying (11 comptes)", spray_codes[-1][0], spray_codes[-1][1], spray_codes[-1][2]))

            # 8. Force brute lente : 11 échecs sur un compte via 3 sources
            slow_codes = []
            for index in range(11):
                remote_ip = (test_ip(18), test_ip(19), test_ip(20))[index % 3]
                code, slow_eval, step_up = attempt(users[11], f"SlowWrong-{index}!", remote_ip, hashlib.sha256(f"slow-{index}".encode()).hexdigest()[:32])
                slow_codes.append((code, getattr(slow_eval, "level", "—"), step_up))
            results.append(("Force brute lente (11 échecs)", slow_codes[-1][0], slow_codes[-1][1], slow_codes[-1][2]))

            # 9. Pays/heure simulés : en-têtes acceptés uniquement en DEMO_MODE
            code, ev, step_up = attempt(
                users[5], password, test_ip(21), hashlib.sha256(b"compromised").hexdigest()[:32],
                extra={"HTTP_X_SECUREACCESS_DEMO_COUNTRY": "France", "HTTP_X_SECUREACCESS_DEMO_CITY": "Paris", "HTTP_X_SECUREACCESS_DEMO_TIME": "03:00"},
            )
            results.append(("Pays/heure inhabituels", code, getattr(ev, "level", "—"), step_up))

            self.stdout.write("\nATTAQUE → DÉCISION (appels au vrai endpoint /api/auth/login/)\n")
            self.stdout.write(f"{'Scénario':38} {'HTTP':>6} {'Niveau':>18}")
            self.stdout.write("-" * 66)
            for label, code, level, step_up in results:
                if step_up:
                    decision = "VÉRIFICATION SUPPLÉMENTAIRE"
                elif code == 200 and level in ("SUSPECT", "HAUT_RISQUE", "CRITIQUE"):
                    decision = "AUTORISÉE AVEC ALERTE"
                elif code == 200:
                    decision = "AUTORISÉE"
                elif code == 423:
                    decision = "VERROUILLÉE"
                elif code == 429:
                    decision = "LIMITÉE"
                elif code == 401 and level in ("SUSPECT", "HAUT_RISQUE", "CRITIQUE"):
                    decision = "REFUSÉE / SIGNALÉE"
                else:
                    decision = "REFUSÉE"
                self.stdout.write(f"{label:38} {code:>6} {str(level):>18}  {decision}")
            blocked = sum(1 for _, code, level, _ in results
                          if code in (403, 423, 429) or level in ("SUSPECT", "HAUT_RISQUE", "CRITIQUE"))
            self.stdout.write("-" * 66)
            self.stdout.write(f"Scénarios : {len(results)} | refusés/verrouillés/limités : {blocked}/{len(results)}")
            transaction.set_rollback(True)
