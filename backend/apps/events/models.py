# Create your models here.
from django.conf import settings
from django.db import models


class Device(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    fingerprint = models.CharField(max_length=64)
    device_type = models.CharField(max_length=30, blank=True)
    os = models.CharField(max_length=50, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "fingerprint"], name="unique_device_per_user"),
        ]

    def __str__(self):
        return f"{self.device_type} {self.os} (user {self.user_id})"


class LoginEvent(models.Model):
    class Source(models.TextChoices):
        DATASET = "DATASET", "Jeu de données"
        LIVE = "LIVE", "Connexion réelle"
        SIMULATOR = "SIMULATOR", "Simulateur"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_events")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    timestamp = models.DateTimeField()
    ip_hash = models.CharField(max_length=64)
    user_agent = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_source = models.CharField(max_length=20, default="UNKNOWN", choices=[
        ("IP_GEOIP", "Géolocalisation IP locale"),
        ("PROFILE_FALLBACK", "Ville de référence du compte"),
        ("DEMO_SIMULATED", "Lieu simulé en démonstration"),
        ("UNKNOWN", "Localisation indisponible"),
    ])
    success = models.BooleanField()
    failure_reason = models.CharField(max_length=50, blank=True)
    # Ground truth, only filled for the generated dataset (never used as a feature)
    label = models.CharField(max_length=20, blank=True)
    attack_type = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.LIVE)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["ip_hash"]),
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.timestamp:%Y-%m-%d %H:%M} ({'ok' if self.success else 'échec'})"


class Notification(models.Model):
    class Kind(models.TextChoices):
        CONNEXION_INHABITUELLE = "CONNEXION_INHABITUELLE", "Connexion inhabituelle"
        MOT_DE_PASSE = "MOT_DE_PASSE", "Mot de passe"
        COMPTE_BLOQUE = "COMPTE_BLOQUE", "Compte bloqué"
        DOUBLE_AUTH = "DOUBLE_AUTH", "Double authentification"

    class Response(models.TextChoices):
        CONFIRMEE = "CONFIRMEE", "Confirmée"
        CONTESTEE = "CONTESTEE", "Contestée"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event = models.ForeignKey(LoginEvent, on_delete=models.CASCADE, null=True, blank=True,
                              related_name="notifications")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=160)
    message = models.TextField()
    needs_response = models.BooleanField(default=False)
    response = models.CharField(max_length=12, choices=Response.choices, blank=True)
    response_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at", "created_at"])]
