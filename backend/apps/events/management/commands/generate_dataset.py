from collections import Counter
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from apps.accounts.models import User
from apps.detection.models import UserProfile
from apps.events import datagen
from apps.events.models import Device, LoginEvent

DEMO_PASSWORD = "Demo2026!"
RESPONSABLE_EMAIL = "responsable@secureaccess.test"


class Command(BaseCommand):
    help = "Génère le jeu de données synthétique, l'exporte en CSV et le charge dans PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=300)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true",
                            help="Supprime d'abord les données du jeu synthétique existant")
        parser.add_argument("--no-load", action="store_true", help="Génère seulement les fichiers CSV")

    def handle(self, *args, **opts):
        folder = Path(settings.BASE_DIR) / "data" / "generated"
        self.stdout.write("Génération du jeu de données...")
        data = datagen.generate(n_users=opts["users"], seed=opts["seed"], ip_secret=settings.IP_HASH_SECRET)
        counts = datagen.write_csvs(data, folder)
        self.stdout.write(self.style.SUCCESS(f"CSV écrits dans {folder} : {counts}"))
        if opts["no_load"]:
            return

        existing = User.objects.filter(email__endswith="@" + datagen.DATASET_DOMAIN)
        if existing.exists():
            if not opts["reset"]:
                raise CommandError("Des données synthétiques existent déjà. Relancez avec --reset pour les remplacer.")
            self.stdout.write("Suppression des anciennes données synthétiques...")
            existing.delete()

        self.stdout.write("Chargement dans PostgreSQL (jusqu'à une minute)...")
        password_hash = make_password(DEMO_PASSWORD)
        per_user = Counter(e["user_idx"] for e in data["events"])

        with transaction.atomic():
            users = [
                User(email=u["email"], full_name=u["full_name"], role=u["role"], password=password_hash,
                     home_city=u["home_city"], home_country=u["home_country"], home_lat=u["home_lat"],
                     home_lon=u["home_lon"], work_profile=u["work_profile"])
                for u in data["users"]
            ]
            User.objects.bulk_create(users, batch_size=1000)

            devices = [
                Device(user=users[d["user_idx"]], fingerprint=d["fingerprint"], device_type=d["device_type"],
                       os=d["os"], browser=d["browser"])
                for d in data["devices"]
            ]
            Device.objects.bulk_create(devices, batch_size=2000)

            events = [
                LoginEvent(user=users[e["user_idx"]], device=devices[e["device_idx"]], timestamp=e["timestamp"],
                           ip_hash=e["ip_hash"], country=e["country"], city=e["city"], latitude=e["latitude"],
                           longitude=e["longitude"], success=e["success"], failure_reason=e["failure_reason"],
                           label=e["label"], attack_type=e["attack_type"], source=LoginEvent.Source.DATASET)
                for e in data["events"]
            ]
            LoginEvent.objects.bulk_create(events, batch_size=5000)

            UserProfile.objects.bulk_create([
                UserProfile(user=users[u["idx"]], usual_hours=sorted(datagen.HOUR_WEIGHTS[u["work_profile"]]),
                            usual_countries=["Cameroun"], login_count=per_user.get(u["idx"], 0))
                for u in data["users"]
            ])

            if not User.objects.filter(email=RESPONSABLE_EMAIL).exists():
                User.objects.create_user(RESPONSABLE_EMAIL, password=DEMO_PASSWORD, role="RESPONSABLE",
                                         full_name="Responsable Démo")

        total = LoginEvent.objects.count()
        self.stdout.write(self.style.SUCCESS(f"{User.objects.count()} comptes, {Device.objects.count()} appareils, {total} événements."))
        for row in LoginEvent.objects.order_by().values("label").annotate(n=Count("id")).order_by("-n"):
            self.stdout.write(f"  {row['label']}: {row['n']} ({100 * row['n'] / total:.2f} %)")
        self.stdout.write(f"Mot de passe de démonstration des comptes générés : {DEMO_PASSWORD}")