from pathlib import Path
import ipaddress

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Vérifie la base GeoLite2 City et teste la localisation d'une adresse IP publique."

    def add_arguments(self, parser):
        parser.add_argument("--ip", required=True, help="Adresse IP publique à tester (pas 127.0.0.1 ou une IP privée).")

    def handle(self, *args, **options):
        path = Path(str(getattr(settings, "GEOIP2_CITY_DB_PATH", "")))
        if not path.is_file():
            raise CommandError(
                f"Base GeoLite2 introuvable : {path}. Téléchargez GeoLite2 City (.mmdb) depuis MaxMind "
                "et placez GeoLite2-City.mmdb dans backend/data/ ou configurez GEOIP2_CITY_DB_PATH dans .env."
            )
        try:
            ip = ipaddress.ip_address(options["ip"].strip())
        except ValueError as exc:
            raise CommandError("Adresse IP invalide.") from exc
        if not ip.is_global:
            raise CommandError("Cette IP est privée/de test et ne peut pas être géolocalisée. Utilisez une IP publique réelle.")
        try:
            from geoip2.database import Reader
            with Reader(str(path)) as reader:
                record = reader.city(str(ip))
        except Exception as exc:
            raise CommandError(f"Échec de lecture GeoLite2 : {exc.__class__.__name__}: {exc}") from exc
        names = record.city.names or {}
        country_names = record.country.names or {}
        city = names.get("fr") or names.get("en") or "Ville non déterminée"
        country = country_names.get("fr") or country_names.get("en") or record.country.iso_code or "Pays non déterminé"
        self.stdout.write(self.style.SUCCESS("Base GeoLite2 City valide et recherche exécutée."))
        self.stdout.write(f"IP testée : {ip}")
        self.stdout.write(f"Lieu estimé : {city}, {country}")
        self.stdout.write(f"Coordonnées approximatives : {record.location.latitude}, {record.location.longitude}")
        self.stdout.write("Source attendue dans SecureAccess : IP_GEOIP")
