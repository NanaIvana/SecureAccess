from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import LoginEvent

from ...models import DetectionConfig


class Command(BaseCommand):
    help = "Supprime les connexions plus anciennes que le délai de conservation configuré."

    def handle(self, *args, **options):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        cutoff = timezone.now() - timedelta(days=config.log_retention_days)
        deleted, details = LoginEvent.objects.filter(timestamp__lt=cutoff).delete()
        events = details.get("events.LoginEvent", 0)
        self.stdout.write(self.style.SUCCESS(
            f"{events} connexion(s) supprimée(s) avant le {cutoff.isoformat()}."
        ))
