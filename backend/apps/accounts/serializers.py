"""
FICHIER : apps/accounts/serializers.py

RÔLE
    Les « serializers » transforment les objets Python/base de données en JSON (et
    inversement) et valident les données reçues.
      - UserSerializer       : ce qu'on renvoie au sujet d'un utilisateur (jamais le mot de passe)
      - UserUpdateSerializer : les seuls champs qu'un administrateur peut modifier (rôle, actif)
      - LoginSerializer      : connexion par e-mail + mot de passe ; renvoie les jetons JWT,
                               le profil de l'utilisateur, et refuse les comptes bloqués

UTILISÉ PAR : apps/accounts/views.py
"""
import re

from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.detection.models import ProgressiveLockout

from .models import User


class UserSerializer(serializers.ModelSerializer):
    # Champ calculé : le compte est-il bloqué en ce moment ?
    is_blocked = serializers.SerializerMethodField()
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    profile_type_label = serializers.CharField(source="get_profile_type_display", read_only=True)
    events_count = serializers.SerializerMethodField()
    risky_count = serializers.SerializerMethodField()
    two_factor = serializers.SerializerMethodField()
    locks = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "blocked_until", "is_blocked",
                  "home_city", "home_country", "home_lat", "home_lon", "work_profile", "profile_type", "created_at", "last_login",
                  "role_label", "profile_type_label", "events_count", "risky_count",
                  "two_factor_enabled", "two_factor_required", "two_factor", "locks"]
        read_only_fields = fields  # lecture seule : on ne modifie rien par ce serializer

    def get_is_blocked(self, obj):
        return obj.is_blocked()

    def get_two_factor(self, obj):
        return {"enabled": obj.two_factor_enabled, "required": obj.two_factor_required}

    def get_locks(self, obj):
        return [
            {
                "source": lock.source_hash[:10],
                "level": lock.level,
                "locked_until": lock.locked_until,
            }
            for lock in ProgressiveLockout.objects.filter(
                user=obj, locked_until__gt=timezone.now(),
            ).order_by("locked_until")
        ]

    def get_events_count(self, obj):
        if hasattr(obj, "events_count"):
            return obj.events_count
        return obj.login_events.count()

    def get_risky_count(self, obj):
        annotated = getattr(obj, "risky_count", None)
        if annotated is not None:
            return annotated
        from apps.detection.models import RiskLevel

        return obj.login_events.filter(
            evaluation__level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE, RiskLevel.CRITIQUE]
        ).count()


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["email", "full_name", "role", "home_city", "home_country", "home_lat", "home_lon",
                  "work_profile", "profile_type", "password", "is_active", "two_factor_required"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "home_city", "home_country", "home_lat", "home_lon", "work_profile"]


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["role", "is_active", "full_name", "home_city", "home_country", "home_lat", "home_lon",
                  "work_profile", "profile_type", "password", "two_factor_required"]

    def validate_password(self, value):
        validate_password(value, user=self.instance)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class LoginSerializer(TokenObtainPairSerializer):
    """Connexion : l'identifiant est l'e-mail (USERNAME_FIELD du modèle User)."""
    device = serializers.DictField(required=False, write_only=True)

    def validate_device(self, value):
        fingerprint = value.get("fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-fA-F0-9]{32,64}", fingerprint):
            raise serializers.ValidationError("Empreinte d'appareil invalide.")
        normalized = {"fingerprint": fingerprint.lower()}
        for field in ("device_type", "os", "browser"):
            field_value = value.get(field, "")
            if not isinstance(field_value, str) or len(field_value) > 50:
                raise serializers.ValidationError(f"Champ d'appareil invalide : {field}.")
            normalized[field] = field_value
        return normalized

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role  # le rôle est glissé dans le jeton (pratique pour le frontend)
        return token

    def validate(self, attrs):
        self.device_data = attrs.pop("device", None)
        # Vérifie l'e-mail et le mot de passe ; lève une erreur 401 si invalides.
        data = super().validate(attrs)
        if self.user.is_blocked():
            raise AuthenticationFailed("Compte temporairement bloqué. Contactez un administrateur.")
        data["user"] = UserSerializer(self.user).data  # profil renvoyé avec les jetons
        return data