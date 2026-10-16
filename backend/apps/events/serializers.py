"""
FICHIER : apps/events/serializers.py

RÔLE
    JSON des événements de connexion (avec leur évaluation du risque) et validation du
    formulaire du simulateur de connexion.
"""
from rest_framework import serializers

from apps.detection.models import RiskEvaluation

from .models import LoginEvent


class EvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskEvaluation
        fields = ["score", "level", "ml_score", "rules_score", "triggered_rules", "reasons",
                  "model_version", "computed_at"]
        read_only_fields = fields


class LoginEventSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    device_label = serializers.SerializerMethodField()
    evaluation = EvaluationSerializer(read_only=True, allow_null=True)

    class Meta:
        model = LoginEvent
        fields = ["id", "user", "user_email", "timestamp", "ip_hash", "country", "city", "latitude", "longitude",
                  "device_label", "success", "failure_reason", "source", "label", "attack_type", "evaluation"]
        read_only_fields = fields

    def get_device_label(self, obj) -> str:
        d = obj.device
        return f"{d.device_type} · {d.os} · {d.browser}" if d else "Appareil inconnu"


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
