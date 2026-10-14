from django.conf import settings
from django.db import models
from django.utils import timezone


class RiskLevel(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    SUSPECT = "SUSPECT", "Suspect"
    HAUT_RISQUE = "HAUT_RISQUE", "Haut risque"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_profile")
    usual_hours = models.JSONField(default=list)
    usual_countries = models.JSONField(default=list)
    login_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user_id}"


class MLModel(models.Model):
    version = models.CharField(max_length=30, unique=True)
    algorithm = models.CharField(max_length=100)
    metrics = models.JSONField(default=dict)
    file_path = models.CharField(max_length=255, blank=True)
    trained_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.version} ({'actif' if self.is_active else 'inactif'})"


class RiskEvaluation(models.Model):
    event = models.OneToOneField("events.LoginEvent", on_delete=models.CASCADE, related_name="evaluation")
    score = models.FloatField()
    level = models.CharField(max_length=15, choices=RiskLevel.choices)
    ml_score = models.FloatField(null=True, blank=True)
    rules_score = models.FloatField(default=0)
    triggered_rules = models.JSONField(default=list)
    reasons = models.JSONField(default=list)
    model_version = models.CharField(max_length=30, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["level"])]

    def __str__(self):
        return f"{self.level} ({self.score:.2f})"
