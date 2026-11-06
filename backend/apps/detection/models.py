from django.conf import settings
from django.db import models
from django.utils import timezone


class RiskLevel(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    SUSPECT = "SUSPECT", "Suspect"
    HAUT_RISQUE = "HAUT_RISQUE", "Haut risque"
    CRITIQUE = "CRITIQUE", "Critique"


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


class DetectionRule(models.Model):
    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    points = models.SmallIntegerField(default=20)
    threshold = models.FloatField(null=True, blank=True)
    threshold_label = models.CharField(max_length=100, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_extension = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.name


class DetectionConfig(models.Model):
    ml_points = models.PositiveSmallIntegerField(default=40)
    suspect_threshold = models.FloatField(default=0.30)
    high_risk_threshold = models.FloatField(default=0.60)
    critical_threshold = models.FloatField(default=0.85)
    notify_users = models.BooleanField(default=True)
    step_up_high_risk = models.BooleanField(default=True)
    refuse_critical = models.BooleanField(default=True)
    auto_block_critical = models.BooleanField(default=True)
    auto_block_minutes = models.PositiveSmallIntegerField(default=15)
    lockout_failures = models.PositiveSmallIntegerField(default=5)
    lockout_window_minutes = models.PositiveSmallIntegerField(default=10)
    lockout_minutes = models.PositiveSmallIntegerField(default=5)
    log_retention_days = models.PositiveSmallIntegerField(default=365)
    sensitive_offset = models.FloatField(default=0.10)
    pseudonymize_for_responsable = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Paramètres de détection"


class DetectionListEntry(models.Model):
    class ListType(models.TextChoices):
        CONFIANCE = "CONFIANCE", "Confiance"
        BLOCAGE = "BLOCAGE", "Blocage"

    class Kind(models.TextChoices):
        IP = "IP", "Adresse IP"
        PAYS = "PAYS", "Pays"
        APPAREIL = "APPAREIL", "Appareil"

    list_type = models.CharField(max_length=12, choices=ListType.choices)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=150)
    comment = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="detection_list_entries",
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["list_type", "kind", "value"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.get_list_type_display()}: {self.label}"


class ProgressiveLockout(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progressive_lockouts",
    )
    source_hash = models.CharField(max_length=64)
    window_started_at = models.DateTimeField(default=timezone.now)
    failure_count = models.PositiveSmallIntegerField(default=0)
    level = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "source_hash"], name="unique_user_source_lockout"),
        ]
        indexes = [
            models.Index(fields=["user", "locked_until"]),
            models.Index(fields=["last_failure_at"]),
        ]

    def __str__(self):
        return f"Source lockout for user {self.user_id}, level {self.level}"


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
