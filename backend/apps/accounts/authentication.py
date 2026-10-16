"""
FICHIER : apps/accounts/authentication.py

RÔLE
    Vérifie le jeton JWT à chaque requête, comme le fait la classe standard, MAIS refuse
    en plus les comptes bloqués. Ainsi, quand un administrateur bloque un compte, l'effet
    est immédiat : même avec un jeton encore valide, l'utilisateur ne peut plus rien faire
    (sans cela, il garderait l'accès jusqu'à l'expiration de son jeton, soit 15 minutes).

UTILISÉ PAR : config/settings.py (REST_FRAMEWORK -> DEFAULT_AUTHENTICATION_CLASSES)
"""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class BlockAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user.is_blocked():  # blocked_until est dans le futur
            raise AuthenticationFailed("Compte temporairement bloqué. Contactez un administrateur.")
        return user