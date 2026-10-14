from django.conf import settings
from django.db import models
from django.utils import timezone


class Severity(models.TextChoices):
    MOYENNE = "MOYENNE", "Moyenne"
    CRITIQUE = "CRITIQUE", "Critique"


class AlertStatus(models.TextChoices):
    NOUVELLE = "NOUVELLE", "Nouvelle"
    EN_COURS = "EN_COURS", "En cours"
    TRAITEE = "TRAITEE", "Traitée"
    FAUSSE_ALERTE = "FAUSSE_ALERTE", "Fausse alerte"


class Alert(models.Model):
    evaluation = models.OneToOneField("detection.RiskEvaluation", on_delete=models.CASCADE, related_name="alert")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=15, choices=AlertStatus.choices, default=AlertStatus.NOUVELLE)
    created_at = models.DateTimeField(default=timezone.now)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="handled_alerts"
    )
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "severity"])]

    def __str__(self):
        return f"Alerte {self.severity} ({self.status})"
