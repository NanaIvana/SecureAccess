"""
FICHIER : apps/accounts/permissions.py

RÔLE
    Définit qui a le droit d'utiliser quelle partie de l'API, selon le rôle de l'utilisateur
    connecté (champ `role` du modèle User).
      - IsAdminRole          : réservé aux administrateurs (alertes, historique, comptes, audit)
      - IsAdminOrResponsable : administrateurs ET responsables d'institution (tableau de bord)

    Le contrôle est fait côté serveur à chaque requête : l'interface React ne fait que
    masquer des menus, elle ne protège rien par elle-même.

UTILISÉ PAR : les vues de accounts, audit (et plus tard alerts, events, dashboard)
"""
from rest_framework.permissions import BasePermission

from .models import Role


class IsAdminRole(BasePermission):
    """Autorise uniquement les utilisateurs connectés ayant le rôle ADMIN."""
    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == Role.ADMIN)


class IsAdminOrResponsable(BasePermission):
    """Autorise les rôles ADMIN et RESPONSABLE (lecture du tableau de bord)."""
    message = "Accès réservé aux administrateurs et aux responsables."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in (Role.ADMIN, Role.RESPONSABLE))