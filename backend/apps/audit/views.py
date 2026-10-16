"""
FICHIER : apps/audit/views.py

RÔLE
    Expose le journal d'audit en lecture seule, réservé aux administrateurs :
      GET /api/audit/               liste paginée, la plus récente d'abord
      GET /api/audit/?action=BLOQUER_COMPTE   filtrer par type d'action
    Le journal n'est jamais modifiable via l'API (traçabilité).

UTILISÉ PAR : apps/audit/urls.py
"""
from rest_framework import serializers, viewsets

from apps.accounts.permissions import IsAdminRole

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    # E-mail de l'auteur de l'action (vide si le compte a été supprimé depuis).
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None, allow_null=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_email", "action", "target", "details", "created_at"]
        read_only_fields = fields


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["action"]