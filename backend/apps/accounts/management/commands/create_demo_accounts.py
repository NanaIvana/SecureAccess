"""Crée les trois comptes-écoles de démonstration, uniquement en environnement DEBUG."""
import hashlib
import hmac
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import ProfileType, Role, User, WorkProfile
from apps.events.models import Device, LoginEvent
from apps.detection.models import ProgressiveLockout, UserProfile


class Command(BaseCommand):
    help = "Crée les comptes de démonstration enseignant, secrétariat et administration."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=os.getenv("DEMO_ACCOUNT_PASSWORD", "DemoSchool2026!"))

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Cette commande est réservée à DEBUG=True. Ne créez pas ces comptes en production.")
        password = options["password"]
        if len(password) < 12:
            raise CommandError("Le mot de passe de démonstration doit contenir au moins 12 caractères.")

        demo_users = [
            ("enseignant@demo.secureaccess.test", "Compte Enseignant", ProfileType.ENSEIGNANT, "a" * 32, Role.UTILISATEUR),
            ("secretaire@demo.secureaccess.test", "Compte Secrétariat", ProfileType.SECRETAIRE, "b" * 32, Role.UTILISATEUR),
            ("administration@demo.secureaccess.test", "Compte Administration scolaire", ProfileType.ADMINISTRATION, "c" * 32, Role.ADMIN),
        ]
        for email, full_name, profile_type, fingerprint, role in demo_users:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": full_name,
                    "role": role,
                    "profile_type": profile_type,
                    "home_city": "Yaoundé",
                    "home_country": "Cameroun",
                    "home_lat": 3.848,
                    "home_lon": 11.502,
                    "work_profile": WorkProfile.JOURNEE,
                    "is_active": True,
                },
            )
            if not created:
                user.full_name = full_name
                user.role = role
                user.profile_type = profile_type
                user.home_city = "Yaoundé"
                user.home_country = "Cameroun"
                user.home_lat = 3.848
                user.home_lon = 11.502
                user.is_active = True
            user.blocked_until = None
            user.two_factor_enabled = False
            user.two_factor_required = False
            user.two_factor_secret = ""
            user.set_password(password)
            user.save()
            Device.objects.filter(user=user).exclude(fingerprint=fingerprint).delete()
            device, _ = Device.objects.get_or_create(
                user=user, fingerprint=fingerprint,
                defaults={"device_type": "Ordinateur", "os": "Windows 11", "browser": "Chrome"},
            )
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={"usual_hours": list(range(7, 19)), "usual_countries": ["Cameroun"]},
            )
            profile.usual_hours = list(range(7, 19))
            profile.usual_countries = ["Cameroun"]
            profile.save(update_fields=["usual_hours", "usual_countries"])
            ProgressiveLockout.objects.filter(user=user).delete()
            # Nettoie les tentatives LIVE de la précédente démo, puis installe une connexion de référence synthétique.
            LoginEvent.objects.filter(user=user, source=LoginEvent.Source.LIVE).delete()
            LoginEvent.objects.filter(user=user, source=LoginEvent.Source.DATASET, attack_type="demo_baseline").delete()
            baseline_time = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)
            baseline_ip = hmac.new(settings.IP_HASH_SECRET.encode(), f"baseline:{email}".encode(), hashlib.sha256).hexdigest()[:32]
            LoginEvent.objects.create(
                user=user, device=device, timestamp=baseline_time, ip_hash=baseline_ip,
                user_agent="SecureAccess demo baseline", country="Cameroun", city="Yaoundé",
                latitude=3.848, longitude=11.502, success=True, label="normal",
                attack_type="demo_baseline", source=LoginEvent.Source.DATASET,
            )
            self.stdout.write(self.style.SUCCESS(f"{email} ({'créé' if created else 'mis à jour'})"))
        self.stdout.write(self.style.WARNING(f"Mot de passe commun de démonstration : {password}"))
        self.stdout.write("Ces comptes sont des comptes de test ; changez les mots de passe avant toute utilisation réelle.")
