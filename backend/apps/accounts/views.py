"""
FICHIER : apps/accounts/views.py

RÔLE
    Les points d'entrée (endpoints) de l'API liés aux comptes :
      POST /api/auth/login/             connexion (e-mail + mot de passe) -> jetons JWT
      POST /api/auth/refresh/           renouvelle le jeton d'accès (voir urls.py)
      POST /api/auth/logout/            déconnexion : invalide le jeton de renouvellement
      GET  /api/me/                     profil de l'utilisateur connecté
      GET  /api/health/                 état de l'application et de la base (public)
      GET  /api/users/                  liste des comptes (administrateur)
      GET  /api/users/{id}/             détail d'un compte (administrateur)
      PATCH /api/users/{id}/            changer le rôle / activer-désactiver (administrateur)
      POST /api/users/{id}/block/       bloquer temporairement un compte (administrateur)
      POST /api/users/{id}/unblock/     débloquer un compte (administrateur)

    Chaque action administrative est enregistrée dans le journal d'audit.

UTILISÉ PAR : apps/accounts/urls.py
"""
from datetime import timedelta

from django.db import connection
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.services import log_action

from .models import User
from .permissions import IsAdminRole
from .serializers import LoginSerializer, UserSerializer, UserUpdateSerializer


class LoginView(TokenObtainPairView):
    """Connexion publique (pas de jeton nécessaire pour se connecter)."""
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]


class MeView(RetrieveAPIView):
    """Profil de la personne connectée (utile au frontend pour connaître son rôle)."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """Déconnexion : le jeton de renouvellement est mis sur liste noire (inutilisable ensuite)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "Le jeton de renouvellement est requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"detail": "Jeton invalide ou déjà révoqué."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HealthView(APIView):
    """Vérifie que l'API répond et que la base de données est joignable (accès public)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database = "ok"
        except Exception:
            database = "erreur"
        code = status.HTTP_200_OK if database == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({"status": "ok" if database == "ok" else "degrade", "database": database}, status=code)


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Gestion des comptes, réservée aux administrateurs."""
    queryset = User.objects.order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["role", "is_active"]   # ex. /api/users/?role=ADMIN
    search_fields = ["email", "full_name"]     # ex. /api/users/?search=fotso
    http_method_names = ["get", "patch", "post", "head", "options"]

    def partial_update(self, request, *args, **kwargs):
        """PATCH : modifier le rôle et/ou l'état actif d'un compte."""
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas modifier votre propre compte ici."},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {"role": user.role, "is_active": user.is_active}
        serializer.save()
        log_action(request.user, "MODIFIER_COMPTE", user.email, {"avant": before, "apres": serializer.data})
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        """Bloque un compte pour N minutes (corps JSON : {"minutes": 60}). Effet immédiat."""
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas bloquer votre propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            minutes = int(request.data.get("minutes", 60))
        except (TypeError, ValueError):
            return Response({"detail": "« minutes » doit être un nombre entier."}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= minutes <= 60 * 24 * 30:  # entre 1 minute et 30 jours
            return Response({"detail": "La durée doit être comprise entre 1 minute et 30 jours."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.blocked_until = timezone.now() + timedelta(minutes=minutes)
        user.save(update_fields=["blocked_until"])
        log_action(request.user, "BLOQUER_COMPTE", user.email, {"minutes": minutes})
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        """Débloque un compte immédiatement."""
        user = self.get_object()
        user.blocked_until = None
        user.save(update_fields=["blocked_until"])
        log_action(request.user, "DEBLOQUER_COMPTE", user.email)
        return Response(UserSerializer(user).data)