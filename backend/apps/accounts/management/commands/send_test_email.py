from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un e-mail de test via le backend SMTP configuré."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Adresse e-mail de réception du test")

    def handle(self, *args, **options):
        recipient = options["to"].strip()
        if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("SMTP incomplet : renseignez EMAIL_HOST, EMAIL_HOST_USER et EMAIL_HOST_PASSWORD dans backend/.env.")
        try:
            sent = send_mail(
                subject="SecureAccess — test de configuration e-mail",
                message=("Bonjour,\n\nCet e-mail confirme que SecureAccess peut envoyer des notifications via SMTP.\n\n"
                         "Si vous recevez ce message, la configuration SMTP fonctionne.\n\nL'équipe SecureAccess"),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f"Échec d'envoi SMTP ({exc.__class__.__name__}) : {exc}") from exc
        if sent != 1:
            raise CommandError("Le serveur SMTP n'a confirmé aucun e-mail envoyé.")
        self.stdout.write(self.style.SUCCESS(f"E-mail de test accepté par SMTP pour {recipient}. Vérifiez aussi les spams."))
