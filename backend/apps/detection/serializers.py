from rest_framework import serializers

from .models import DetectionConfig, DetectionRule


class DetectionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectionRule
        fields = (
            "id", "key", "name", "description", "points", "threshold",
            "threshold_label", "is_enabled", "is_extension",
        )
        read_only_fields = ("id", "key", "name", "description", "threshold_label", "is_extension")

    def validate_points(self, value):
        if not -100 <= value <= 100:
            raise serializers.ValidationError("Les points doivent être compris entre -100 et 100.")
        return value

    def validate_threshold(self, value):
        if value is not None and (value < 0 or value > 1_000_000):
            raise serializers.ValidationError("Le seuil doit être compris entre 0 et 1 000 000.")
        return value


class DetectionConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectionConfig
        fields = (
            "ml_points", "suspect_threshold", "high_risk_threshold", "critical_threshold",
            "notify_users", "step_up_high_risk", "refuse_critical", "auto_block_critical",
            "auto_block_minutes", "lockout_failures", "lockout_window_minutes", "lockout_minutes",
            "log_retention_days", "sensitive_offset", "pseudonymize_for_responsable", "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate(self, attrs):
        thresholds = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in ("suspect_threshold", "high_risk_threshold", "critical_threshold")
        }
        suspect, high, critical = (thresholds[key] for key in (
            "suspect_threshold", "high_risk_threshold", "critical_threshold",
        ))
        if not 0 < suspect < high < critical <= 1:
            raise serializers.ValidationError(
                "Les seuils doivent être croissants : suspect < risque élevé < critique (entre 0 et 1)."
            )
        limits = {
            "ml_points": (0, 100),
            "auto_block_minutes": (1, 1440),
            "lockout_failures": (0, 100),
            "lockout_window_minutes": (1, 1440),
            "lockout_minutes": (1, 1440),
            "log_retention_days": (30, 3650),
            "sensitive_offset": (0, 0.5),
        }
        for field, (minimum, maximum) in limits.items():
            value = attrs.get(field, getattr(self.instance, field, None))
            if value is not None and not minimum <= value <= maximum:
                raise serializers.ValidationError({
                    field: f"La valeur doit être comprise entre {minimum} et {maximum}."
                })
        return attrs


class TrainingSerializer(serializers.Serializer):
    n_estimators = serializers.IntegerField(min_value=10, max_value=500, default=150)
    max_depth = serializers.IntegerField(min_value=2, max_value=40, default=12)
    activate = serializers.BooleanField(default=True)
    rescore = serializers.BooleanField(default=True)
