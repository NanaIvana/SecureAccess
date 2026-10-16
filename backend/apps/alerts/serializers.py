"""
FICHIER : apps/alerts/serializers.py

RÔLE
    JSON des alertes : version liste (légère) et version détail (événement complet, motifs
    et historique récent de l'utilisateur), plus la validation du traitement d'une alerte.
"""
from rest_framework import serializers

from apps.events.models import LoginEvent
from apps.events.serializers import LoginEventSerializer

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    level = serializers.CharField(source="evaluation.level", read_only=True)
    score = serializers.FloatField(source="evaluation.score", read_only=True)
    reasons = serializers.JSONField(source="evaluation.reasons", read_only=True)
    event_id = serializers.IntegerField(source="evaluation.event_id", read_only=True)
    timestamp = serializers.DateTimeField(source="evaluation.event.timestamp", read_only=True)
    user_id = serializers.IntegerField(source="evaluation.event.user_id", read_only=True)
    user_email = serializers.CharField(source="evaluation.event.user.email", read_only=True)
    country = serializers.CharField(source="evaluation.event.country", read_only=True)
    city = serializers.CharField(source="evaluation.event.city", read_only=True)
    success = serializers.BooleanField(source="evaluation.event.success", read_only=True)
    handled_by_email = serializers.CharField(source="handled_by.email", read_only=True, default=None, allow_null=True)

    class Meta:
        model = Alert
        fields = ["id", "severity", "status", "created_at", "handled_at", "handled_by_email", "comment",
                  "level", "score", "reasons", "event_id", "timestamp", "user_id", "user_email",
                  "country", "city", "success"]
        read_only_fields = fields


class AlertDetailSerializer(AlertSerializer):
    event = LoginEventSerializer(source="evaluation.event", read_only=True)
    triggered_rules = serializers.JSONField(source="evaluation.triggered_rules", read_only=True)
    recent_events = serializers.SerializerMethodField()

    class Meta(AlertSerializer.Meta):
        fields = AlertSerializer.Meta.fields + ["event", "triggered_rules", "recent_events"]
        read_only_fields = fields

    def get_recent_events(self, obj) -> list:
        """Les 10 dernières connexions de l'utilisateur avant cette alerte (contexte pour l'administrateur)."""
        ev = obj.evaluation.event
        qs = (LoginEvent.objects.filter(user_id=ev.user_id, timestamp__lte=ev.timestamp)
              .select_related("evaluation").order_by("-timestamp")[:10])
        return [{"id": e.id, "timestamp": e.timestamp, "country": e.country, "city": e.city, "success": e.success,
                 "level": e.evaluation.level if hasattr(e, "evaluation") else None} for e in qs]


class AlertUpdateSerializer(serializers.ModelSerializer):
    """Seuls le statut et le commentaire peuvent être modifiés."""
    class Meta:
        model = Alert
        fields = ["status", "comment"]
