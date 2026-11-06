"""
FICHIER : apps/events/serializers.py

RÔLE
    JSON des événements de connexion (avec leur évaluation du risque) et validation du
    formulaire du simulateur de connexion.
"""
import hashlib
import hmac

from django.conf import settings
from rest_framework import serializers

from apps.accounts.models import User
from apps.detection.models import DetectionConfig, RiskEvaluation

from .models import Device, LoginEvent, Notification


class EventUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name"]


class EventDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["id", "device_type", "os", "browser"]


class EvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskEvaluation
        fields = ["score", "level", "ml_score", "rules_score", "triggered_rules", "reasons",
                  "model_version", "computed_at"]
        read_only_fields = fields


class LoginEventSerializer(serializers.ModelSerializer):
    user = EventUserSerializer(read_only=True)
    device = EventDeviceSerializer(read_only=True)
    device_label = serializers.SerializerMethodField()
    evaluation = EvaluationSerializer(read_only=True, allow_null=True)
    score = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    triggered_rules = serializers.SerializerMethodField()
    alert = serializers.SerializerMethodField()
    home = serializers.SerializerMethodField()

    class Meta:
        model = LoginEvent
        fields = ["id", "user", "timestamp", "ip_hash", "country", "city", "latitude", "longitude",
                  "device", "device_label", "location_source", "success", "failure_reason", "source", "label", "attack_type",
                  "evaluation", "score", "level", "triggered_rules", "alert", "home"]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) == "RESPONSABLE":
            config = DetectionConfig.objects.filter(pk=1).only("pseudonymize_for_responsable").first()
            if config is None or config.pseudonymize_for_responsable:
                token = hmac.new(
                    settings.IP_HASH_SECRET.encode(), str(instance.user_id).encode(), hashlib.sha256,
                ).hexdigest()[:10]
                data["user"]["email"] = f"Utilisateur-{token}"
                data["user"]["full_name"] = f"Utilisateur-{token}"
                data["home"] = {"city": "", "country": "", "latitude": None, "longitude": None}
        return data

    def get_device_label(self, obj) -> str:
        d = obj.device
        return f"{d.device_type} · {d.os} · {d.browser}" if d else "Appareil inconnu"

    def get_score(self, obj):
        return obj.evaluation.score if hasattr(obj, "evaluation") else None

    def get_level(self, obj):
        return obj.evaluation.level if hasattr(obj, "evaluation") else None

    def get_triggered_rules(self, obj):
        return obj.evaluation.triggered_rules if hasattr(obj, "evaluation") else []

    def get_alert(self, obj):
        alert = getattr(getattr(obj, "evaluation", None), "alert", None)
        if alert is None:
            return None
        return {"id": alert.id, "severity": alert.severity, "status": alert.status}

    def get_home(self, obj):
        user = obj.user
        return {"city": user.home_city, "country": user.home_country,
                "latitude": user.home_lat, "longitude": user.home_lon}


class SimulateSerializer(serializers.Serializer):
    """Paramètres du simulateur : on rejoue une tentative de connexion pour démontrer la détection."""
    user = serializers.IntegerField(help_text="Identifiant du compte ciblé")
    city = serializers.CharField(help_text="« domicile » ou une ville proposée par /api/events/places/")
    success = serializers.BooleanField(default=True)
    failures = serializers.IntegerField(min_value=0, max_value=40, default=0,
                                        help_text="Nombre d'échecs juste avant la tentative (force brute)")
    hour = serializers.IntegerField(min_value=0, max_value=23, required=False,
                                    help_text="Heure UTC de la tentative (par défaut : maintenant)")
    device = serializers.ChoiceField(choices=["known", "new"], default="known")
    ip_label = serializers.CharField(required=False, allow_blank=True, max_length=60,
                                     help_text="Même valeur = même source (pseudonymisée) ; vide = source aléatoire")


class NotificationSerializer(serializers.ModelSerializer):
    event = serializers.IntegerField(source="event_id", read_only=True)
    response_label = serializers.CharField(source="get_response_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "message", "created_at", "read_at",
                  "event", "needs_response", "response", "response_label"]
        read_only_fields = fields
