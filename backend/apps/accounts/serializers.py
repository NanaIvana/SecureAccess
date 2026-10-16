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
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    # Champ calculé : le compte est-il bloqué en ce moment ?
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "blocked_until", "is_blocked",
                  "home_city", "home_country", "work_profile", "created_at"]
        read_only_fields = fields  # lecture seule : on ne modifie rien par ce serializer

    def get_is_blocked(self, obj):
        return obj.is_blocked()


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["role", "is_active"]  # seuls champs modifiables par un administrateur


class LoginSerializer(TokenObtainPairSerializer):
    """Connexion : l'identifiant est l'e-mail (USERNAME_FIELD du modèle User)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role  # le rôle est glissé dans le jeton (pratique pour le frontend)
        return token

    def validate(self, attrs):
        # Vérifie l'e-mail et le mot de passe ; lève une erreur 401 si invalides.
        data = super().validate(attrs)
        if self.user.is_blocked():
            raise AuthenticationFailed("Compte temporairement bloqué. Contactez un administrateur.")
        data["user"] = UserSerializer(self.user).data  # profil renvoyé avec les jetons
        return data